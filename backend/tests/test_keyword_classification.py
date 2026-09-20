import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import ClassVar

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import KeywordCategory, ModelRole
from app.models.recipe import Keyword
from app.services.ai import AIProvider, AIResponseError, ResolvedTask, Usage
from app.services.keyword_classification import (
    classify_keyword_rows,
    classify_pending_keywords,
)
from scripts.audit_keyword_candidates import build_report


class ReplyProvider(AIProvider):
    name = "REPLY"
    models: ClassVar[dict[ModelRole, str]] = {
        ModelRole.KEYWORD_CLASSIFICATION: "reply-model"
    }

    def __init__(self, replies: list[object]) -> None:
        super().__init__("")
        self.replies = list(replies)
        self.calls = 0

    def _complete(
        self,
        prompt: str,
        model: str,
        *,
        schema: dict | None = None,
        temp: float = 0,
        system: str | None = None,
    ) -> tuple[str, Usage]:
        del prompt, model, schema, temp, system
        self.calls += 1
        reply = self.replies.pop(0)
        return json.dumps(reply), Usage(
            cost_usd=Decimal("0.01"), input_tokens=10, output_tokens=4
        )


def _resolve(monkeypatch: pytest.MonkeyPatch, provider: ReplyProvider) -> None:
    monkeypatch.setattr(
        "app.services.keyword_classification.resolve_task",
        lambda _session, _role: ResolvedTask(provider, "reply-model"),
    )


def _clear_pending(session: Session) -> None:
    for keyword in session.scalars(select(Keyword)):
        keyword.classified_at = datetime.now(UTC)
    session.commit()


def test_keyword_model_represents_all_three_classification_states(session: Session) -> None:
    pending = Keyword(name="pending")
    categorised = Keyword(
        name="categorised",
        category=KeywordCategory.METHOD,
        classified_at=datetime.now(UTC),
    )
    no_category = Keyword(name="examined", classified_at=datetime.now(UTC))
    session.add_all([pending, categorised, no_category])
    session.commit()

    assert pending.category is None and pending.classified_at is None
    assert categorised.category == KeywordCategory.METHOD
    assert categorised.classified_at is not None
    assert no_category.category is None and no_category.classified_at is not None


def test_provider_parses_categories_and_null_without_calling_for_empty_input() -> None:
    provider = ReplyProvider(
        [[{"name": "thai", "category": "cuisine_region"}, {"name": "quick", "category": None}]]
    )

    results, usage = provider.classify_keywords(["thai", "quick"])

    assert [(item.name, item.category) for item in results] == [
        ("thai", "cuisine_region"),
        ("quick", None),
    ]
    assert usage.input_tokens == 10
    assert provider.classify_keywords([])[0] == []
    assert provider.calls == 1


@pytest.mark.parametrize(
    "reply",
    [
        [{"name": "thai"}],
        [{"name": "thai", "category": "cuisine_region", "reason": "country"}],
    ],
)
def test_provider_rejects_missing_or_extra_result_fields(reply: object) -> None:
    provider = ReplyProvider([reply])

    with pytest.raises(AIResponseError, match="exactly 'name' and 'category'"):
        provider.classify_keywords(["thai"])


@pytest.mark.parametrize(
    ("reply", "message"),
    [
        ([{"name": "thai", "category": "season"}], "invalid category"),
        ([], "omitted candidate"),
        (
            [
                {"name": "thai", "category": "cuisine_region"},
                {"name": "thai", "category": "cuisine_region"},
            ],
            "repeated candidate",
        ),
        ([{"name": "unknown", "category": None}], "unknown candidate"),
    ],
)
def test_invalid_batch_is_rejected_without_writes(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    reply: object,
    message: str,
) -> None:
    _clear_pending(session)
    keyword = Keyword(name="thai")
    session.add(keyword)
    session.commit()
    provider = ReplyProvider([reply])
    _resolve(monkeypatch, provider)

    with pytest.raises(AIResponseError, match=message):
        classify_keyword_rows(session, [keyword])
    session.rollback()
    session.refresh(keyword)
    assert keyword.category is None
    assert keyword.classified_at is None


def test_pending_sweep_uses_batch_boundaries_and_accumulates_usage(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_pending(session)
    keywords = [Keyword(name=name) for name in ["bake", "dinner", "pasta"]]
    session.add_all(keywords)
    session.commit()
    provider = ReplyProvider(
        [
            [
                {"name": "bake", "category": "method"},
                {"name": "dinner", "category": "course"},
            ],
            [{"name": "pasta", "category": None}],
        ]
    )
    _resolve(monkeypatch, provider)

    result = classify_pending_keywords(session, batch_size=2)

    assert provider.calls == 2
    assert result.pending == 3
    assert result.examined == 3
    assert result.classified_by_category["method"] == 1
    assert result.classified_by_category["course"] == 1
    assert result.no_category == 1
    assert result.failed_batches == 0
    assert result.usage.cost_usd == Decimal("0.02")
    assert result.usage.input_tokens == 20
    assert result.usage.output_tokens == 8
    assert all(keyword.classified_at is not None for keyword in keywords)


def test_failed_batch_stays_pending_while_later_batch_commits(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_pending(session)
    keywords = [Keyword(name="first"), Keyword(name="second")]
    session.add_all(keywords)
    session.commit()
    provider = ReplyProvider(
        [
            [{"name": "wrong", "category": None}],
            [{"name": "second", "category": "course"}],
        ]
    )
    _resolve(monkeypatch, provider)

    result = classify_pending_keywords(session, batch_size=1)

    session.refresh(keywords[0])
    session.refresh(keywords[1])
    assert result.examined == 2
    assert result.failed_batches == 1
    assert result.usage.input_tokens == 20
    assert keywords[0].classified_at is None
    assert keywords[1].category == KeywordCategory.COURSE
    assert keywords[1].classified_at is not None


def test_audit_reports_exact_terms_and_seasonal_compound_risks(session: Session) -> None:
    session.add_all(
        [
            Keyword(name="vegetarian"),
            Keyword(name="summer"),
            Keyword(name="spring onion"),
            Keyword(name="winter squash"),
        ]
    )
    session.commit()

    report = build_report(session)

    dietary = report.split("Season exact terms", 1)[0]
    seasons, compounds = report.split("Season exact terms", 1)[1].split(
        "Seasonal-word compounds", 1
    )
    assert "vegetarian\t0" in dietary
    assert "summer\t0" in seasons
    assert "spring onion\t0" not in seasons
    assert "spring onion\t0" in compounds
    assert "winter squash\t0" in compounds
