"""Load and resolve the eval configuration (``eval.toml``)."""

import subprocess
import tomllib
from pathlib import Path

from pydantic import BaseModel

from evals.models import BookSpec, CandidateModel, TaskSpec

EVALS_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = EVALS_DIR / "eval.toml"

# Append-only ledger of every (run, model, book) result, and the per-run artefact dir.
LEDGER_PATH = EVALS_DIR / "index.jsonl"
RUNS_DIR = EVALS_DIR / "runs"


def git_sha() -> str | None:
    """The commit a run was made at, so a ledger row is attributable to code."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=EVALS_DIR,
            check=False,
        )
    except OSError:
        return None
    return out.stdout.strip() or None


class Weights(BaseModel):
    name: float
    ingredients: float
    instructions: float
    yields: float
    image: float


class EvalConfig(BaseModel):
    base_dir: Path
    tasks: list[TaskSpec]
    books: list[BookSpec]
    fuzzy_threshold: float
    weights: Weights

    def task(self, role: str) -> TaskSpec:
        for t in self.tasks:
            if t.role == role:
                return t
        raise KeyError(f"No task '{role}' in eval config; have {[t.role for t in self.tasks]}")

    def book(self, slug: str) -> BookSpec:
        for b in self.books:
            if b.slug == slug:
                return b
        raise KeyError(f"No book '{slug}' in eval config; have {[b.slug for b in self.books]}")

    def gold_path(self, book: BookSpec) -> Path:
        return self.base_dir / book.gold


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> EvalConfig:
    data = tomllib.loads(path.read_text())
    tasks = [
        TaskSpec(
            role=role,
            books=spec["books"],
            models=[CandidateModel.parse(m) for m in spec["models"]],
        )
        for role, spec in data["tasks"].items()
    ]
    return EvalConfig(
        base_dir=path.parent,
        tasks=tasks,
        books=[BookSpec(**b) for b in data["books"]],
        fuzzy_threshold=data["matching"]["fuzzy_threshold"],
        weights=Weights(**data["weights"]),
    )
