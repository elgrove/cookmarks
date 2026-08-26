"""Assistant eval: score candidate models on tool use and answer quality.

The extraction eval scores a pipeline against gold recipes. This one scores a
*conversation*: for each prompt, the agent runs with all its real tools against a
throwaway copy of the app database, and the transcript is checked against
expectations declared in ``eval.toml``.

Every check is deterministic — which tools were called, how many searches were tried,
whether the recipes it linked are ones a tool actually returned. No LLM judge, so a
score is reproducible and free. The transcript of each run is written under ``runs/``
so the answers can be read by eye, which is what "response quality" ultimately means.

The database is a copy: the tools can create lists and toggle favourites, and a model
that does so during an eval must not touch real data.
"""

import json
import logging
import re
import sqlite3
import time
import tomllib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic_ai.messages import ModelMessage, ToolCallPart, ToolReturnPart
from pydantic_ai.usage import UsageLimits
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models.user import User
from app.services.assistant import AssistantDeps, build_agent
from evals.config import DEFAULT_CONFIG_PATH, EVALS_DIR, RUNS_DIR, git_sha
from evals.environment import make_engine, resolve_api_key, set_provider
from evals.models import CandidateModel
from evals.report import _table

logger = logging.getLogger(__name__)

ASSISTANT_DB_PATH = EVALS_DIR / "assistant.sqlite3"
ASSISTANT_LEDGER_PATH = EVALS_DIR / "assistant.jsonl"

# The app DB the eval library is copied from, captured before anything rebinds it.
_SOURCE_DB_PATH = settings.db_path

# A runaway tool loop is the expensive failure mode; cap the requests per prompt.
REQUEST_LIMIT = 12

SEARCH_TOOLS = {"search_recipes", "semantic_search_recipes"}

_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
_LINK_RE = re.compile(r"/(recipes|books)/(" + _UUID_RE.pattern + ")", re.I)


class PromptSpec(BaseModel):
    """One eval prompt and what a good answer to it must satisfy."""

    id: str
    prompt: str
    expect_tools: list[str] = []
    min_searches: int = 0
    min_recipe_links: int = 0
    must_mention: list[str] = []


class AssistantRecord(BaseModel):
    """A flat row in ``assistant.jsonl`` — one per (run, prompt, model)."""

    run_id: str
    timestamp: str
    git_sha: str | None
    prompt_id: str
    model_id: str
    provider: str
    model: str
    score: float
    checks_passed: int
    checks_total: int
    failed: list[str]
    tool_calls: list[str]
    answer_chars: int
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    duration_s: float
    error: str | None = None


@dataclass
class Transcript:
    """What one agent run actually did, reduced to what the checks read."""

    answer: str
    tool_calls: list[tuple[str, dict]] = field(default_factory=list)
    returned_ids: set[str] = field(default_factory=set)

    @property
    def tool_names(self) -> list[str]:
        return [name for name, _ in self.tool_calls]


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""

    def __post_init__(self) -> None:
        # The detail explains a failure; on a pass it would just be misleading.
        if self.passed:
            self.detail = ""


def _collect_ids(value: Any, into: set[str]) -> None:
    if isinstance(value, str):
        into.update(m.group(0).lower() for m in _UUID_RE.finditer(value))
    elif isinstance(value, dict):
        for item in value.values():
            _collect_ids(item, into)
    elif isinstance(value, list):
        for item in value:
            _collect_ids(item, into)


def read_transcript(messages: list[ModelMessage], answer: str) -> Transcript:
    """Reduce a finished run to the tool calls it made and the ids its tools returned."""
    transcript = Transcript(answer=answer)
    for message in messages:
        for part in message.parts:
            if isinstance(part, ToolCallPart):
                args = part.args_as_dict() if part.args is not None else {}
                transcript.tool_calls.append((part.tool_name, args))
            elif isinstance(part, ToolReturnPart):
                _collect_ids(part.content, transcript.returned_ids)
    return transcript


def linked_ids(answer: str) -> list[tuple[str, str]]:
    """Every app link the answer wrote, as (kind, id) — the claims to be checked."""
    return [(m.group(1).lower(), m.group(2).lower()) for m in _LINK_RE.finditer(answer)]


def check_prompt(spec: PromptSpec, transcript: Transcript) -> list[Check]:
    """Score one run. Grounding is checked for every prompt; the rest come from the spec."""
    called = set(transcript.tool_names)
    checks = [
        Check(f"calls:{tool}", tool in called, "not called")
        for tool in spec.expect_tools
    ]

    searches = sum(1 for name in transcript.tool_names if name in SEARCH_TOOLS)
    if spec.min_searches:
        checks.append(
            Check(f"searches>={spec.min_searches}", searches >= spec.min_searches, f"{searches}")
        )

    links = linked_ids(transcript.answer)
    recipe_links = {rid for kind, rid in links if kind == "recipes"}
    if spec.min_recipe_links:
        checks.append(
            Check(
                f"links>={spec.min_recipe_links}",
                len(recipe_links) >= spec.min_recipe_links,
                f"{len(recipe_links)}",
            )
        )

    # The hallucination check: an id in the answer must be one a tool handed back.
    invented = sorted({rid for _, rid in links} - transcript.returned_ids)
    checks.append(
        Check("grounded", not invented, f"{len(invented)} invented: {invented[:3]}")
    )

    haystack = transcript.answer.casefold()
    checks.extend(
        Check(f"mentions:{term}", term.casefold() in haystack, "absent")
        for term in spec.must_mention
    )
    return checks


def score(checks: list[Check]) -> float:
    return sum(c.passed for c in checks) / len(checks) if checks else 0.0


def load_assistant_config(path: Path = DEFAULT_CONFIG_PATH) -> tuple[list[CandidateModel], list[PromptSpec]]:
    data = tomllib.loads(path.read_text()).get("assistant")
    if not data:
        raise KeyError(f"No [assistant] section in {path}")
    return (
        [CandidateModel.parse(m) for m in data["models"]],
        [PromptSpec(**p) for p in data["prompts"]],
    )


def build_library_copy() -> tuple[sessionmaker[Session], uuid.UUID]:
    """A throwaway copy of the app database, so the agent searches a real library while
    anything its acting tools write is discarded with the copy."""
    if not _SOURCE_DB_PATH.exists():
        raise RuntimeError(f"No app database at {_SOURCE_DB_PATH} to copy the library from")
    ASSISTANT_DB_PATH.unlink(missing_ok=True)
    # .backup rather than a file copy: the source may be live, with a half-written WAL.
    source = sqlite3.connect(str(_SOURCE_DB_PATH))
    target = sqlite3.connect(str(ASSISTANT_DB_PATH))
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()

    factory = sessionmaker(
        bind=make_engine(ASSISTANT_DB_PATH), autoflush=False, expire_on_commit=False
    )
    with factory() as session:
        user = session.scalar(select(User).order_by(User.created_at))
        if user is None:
            user = User(username="eval", password_hash="unusable", is_admin=True)
            session.add(user)
            session.commit()
        return factory, user.id


def run_prompt(
    factory: sessionmaker[Session], user_id: uuid.UUID, spec: PromptSpec
) -> tuple[Transcript, dict]:
    """One prompt against the currently-configured model. Returns the transcript and
    the run's cost/latency."""
    with factory() as session:
        agent = build_agent(session)
        if agent is None:
            raise RuntimeError("no usable AI provider for this candidate")
        started = time.monotonic()
        result = agent.run_sync(
            spec.prompt,
            deps=AssistantDeps(session=session, user_id=user_id),
            usage_limits=UsageLimits(request_limit=REQUEST_LIMIT),
        )
        duration = time.monotonic() - started

    usage = result.usage
    meta = {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cost_usd": float(usage.cost) if usage.cost is not None else None,
        "duration_s": duration,
    }
    return read_transcript(result.all_messages(), result.output), meta


def _safe(name: str) -> str:
    return name.replace("/", "_").replace(":", "_")


def _write_artefact(
    run_dir: Path, spec: PromptSpec, candidate: CandidateModel, transcript: Transcript,
    checks: list[Check], meta: dict,
) -> None:
    out = run_dir / "assistant" / spec.id
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{_safe(candidate.id)}.json").write_text(
        json.dumps(
            {
                "prompt": spec.prompt,
                "model": candidate.id,
                "answer": transcript.answer,
                "tool_calls": [{"tool": n, "args": a} for n, a in transcript.tool_calls],
                "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in checks],
                "score": score(checks),
                **meta,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def _append_ledger(records: list[AssistantRecord]) -> None:
    with ASSISTANT_LEDGER_PATH.open("a", encoding="utf-8") as fh:
        for record in records:
            fh.write(record.model_dump_json() + "\n")


def load_ledger(path: Path = ASSISTANT_LEDGER_PATH) -> list[AssistantRecord]:
    if not path.exists():
        return []
    return [
        AssistantRecord(**json.loads(line))
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def leaderboard(records: list[AssistantRecord]) -> str:
    if not records:
        return "No assistant eval runs recorded yet."
    latest = max(r.run_id for r in records)
    current = [r for r in records if r.run_id == latest]

    sections = []
    for prompt_id in sorted({r.prompt_id for r in current}):
        rows = sorted(
            (r for r in current if r.prompt_id == prompt_id),
            key=lambda r: r.score,
            reverse=True,
        )
        sections.append(
            f"{prompt_id}\n"
            + _table(
                ["Model", "Score", "Checks", "Tools", "Failed", "Cost", "Time"],
                [
                    [
                        r.model_id,
                        f"{r.score:.2f}",
                        f"{r.checks_passed}/{r.checks_total}",
                        str(len(r.tool_calls)),
                        ", ".join(r.failed) or (r.error or "—"),
                        f"${r.cost_usd:.4f}" if r.cost_usd is not None else "—",
                        f"{r.duration_s:.0f}s",
                    ]
                    for r in rows
                ],
            )
        )
    return f"Assistant leaderboard (run {latest})\n\n" + "\n\n".join(sections)


def run_assistant_eval(
    config_path: Path = DEFAULT_CONFIG_PATH,
    model_ids: list[str] | None = None,
    prompt_ids: list[str] | None = None,
) -> list[AssistantRecord]:
    models, prompts = load_assistant_config(config_path)
    if model_ids:
        models = [m for m in models if m.id in model_ids]
    if prompt_ids:
        prompts = [p for p in prompts if p.id in prompt_ids]

    factory, user_id = build_library_copy()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    timestamp = datetime.now(UTC).isoformat()
    sha = git_sha()
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    records: list[AssistantRecord] = []
    for candidate in models:
        try:
            key = resolve_api_key(candidate.provider)
        except RuntimeError as exc:
            logger.warning(f"Skipping {candidate.id}: {exc}")
            continue
        set_provider(factory, candidate.provider, key, {"assistant": candidate.model})
        for spec in prompts:
            logger.info(f"Running {spec.id} / {candidate.id}")
            try:
                transcript, meta = run_prompt(factory, user_id, spec)
            except Exception as exc:
                logger.warning(f"{spec.id} / {candidate.id} failed: {exc}")
                records.append(
                    AssistantRecord(
                        run_id=run_id, timestamp=timestamp, git_sha=sha, prompt_id=spec.id,
                        model_id=candidate.id, provider=candidate.provider, model=candidate.model,
                        score=0.0, checks_passed=0, checks_total=0, failed=[], tool_calls=[],
                        answer_chars=0, input_tokens=None, output_tokens=None, cost_usd=None,
                        duration_s=0.0, error=str(exc)[:200],
                    )
                )
                continue

            checks = check_prompt(spec, transcript)
            _write_artefact(run_dir, spec, candidate, transcript, checks, meta)
            records.append(
                AssistantRecord(
                    run_id=run_id, timestamp=timestamp, git_sha=sha, prompt_id=spec.id,
                    model_id=candidate.id, provider=candidate.provider, model=candidate.model,
                    score=score(checks),
                    checks_passed=sum(c.passed for c in checks),
                    checks_total=len(checks),
                    failed=[c.name for c in checks if not c.passed],
                    tool_calls=transcript.tool_names,
                    answer_chars=len(transcript.answer),
                    **meta,
                )
            )
            print(
                f"  {spec.id:16s} {candidate.id:34s} "
                f"score={records[-1].score:.2f} "
                f"({records[-1].checks_passed}/{records[-1].checks_total}) "
                f"tools={len(transcript.tool_calls)} {meta['duration_s']:.0f}s"
            )

    _append_ledger(records)
    return records
