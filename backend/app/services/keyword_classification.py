"""AI classification for the shared keyword vocabulary.

Classification is vocabulary-level: each exact keyword name is examined once and gets
one optional browsing category. ``classified_at`` distinguishes a deliberate null result
from work that is still pending.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import KeywordCategory, ModelRole
from app.models.recipe import Keyword
from app.services.ai import AIResponseError, KeywordClassification, ResolvedTask, Usage
from app.services.ai.registry import resolve_task

logger = logging.getLogger(__name__)

KEYWORD_CLASSIFICATION_BATCH_SIZE = 100


def _empty_counts() -> dict[str, int]:
    return {category.value: 0 for category in KeywordCategory}


@dataclass
class KeywordClassificationResult:
    pending: int = 0
    examined: int = 0
    classified_by_category: dict[str, int] = field(default_factory=_empty_counts)
    no_category: int = 0
    failed_batches: int = 0
    usage: Usage = field(default_factory=Usage)
    provider_name: str | None = None
    model_name: str | None = None

    @property
    def classified(self) -> int:
        return sum(self.classified_by_category.values())

    def add(self, other: "KeywordClassificationResult") -> None:
        self.examined += other.examined
        self.no_category += other.no_category
        self.failed_batches += other.failed_batches
        self.usage = self.usage + other.usage
        for category, count in other.classified_by_category.items():
            self.classified_by_category[category] += count


def _validate_results(
    candidates: list[Keyword], results: list[KeywordClassification], usage: Usage
) -> dict[str, KeywordCategory | None]:
    expected = {keyword.name for keyword in candidates}
    names = [result.name for result in results]
    repeated = sorted({name for name in names if names.count(name) > 1})
    if repeated:
        raise AIResponseError(
            f"Keyword classification repeated candidate(s): {', '.join(repeated)}", usage
        )
    unknown = sorted(set(names) - expected)
    if unknown:
        raise AIResponseError(
            f"Keyword classification returned unknown candidate(s): {', '.join(unknown)}", usage
        )
    missing = sorted(expected - set(names))
    if missing:
        raise AIResponseError(
            f"Keyword classification omitted candidate(s): {', '.join(missing)}", usage
        )
    if len(results) != len(candidates):
        raise AIResponseError("Keyword classification did not cover candidates exactly once", usage)

    validated: dict[str, KeywordCategory | None] = {}
    for result in results:
        try:
            category = KeywordCategory(result.category) if result.category is not None else None
        except ValueError as exc:
            raise AIResponseError(
                f"Keyword classification returned invalid category {result.category!r}", usage
            ) from exc
        validated[result.name] = category
    return validated


def _classify_batch(
    session: Session, keywords: list[Keyword], resolved: ResolvedTask
) -> KeywordClassificationResult:
    names = [keyword.name for keyword in keywords]
    classifications, usage = resolved.provider.classify_keywords(names, resolved.model)
    validated = _validate_results(keywords, classifications, usage)
    now = datetime.now(UTC)
    result = KeywordClassificationResult(
        examined=len(keywords),
        usage=usage,
        provider_name=resolved.provider.name,
        model_name=resolved.model,
    )
    for keyword in keywords:
        category = validated[keyword.name]
        keyword.category = category
        keyword.classified_at = now
        if category is None:
            result.no_category += 1
        else:
            result.classified_by_category[category.value] += 1
    session.flush()
    return result


def classify_keyword_rows(session: Session, keywords: list[Keyword]) -> KeywordClassificationResult:
    """Classify one explicit, bounded set in one provider call and commit it.

    Extraction uses this for only the rows that it created. Existing or already
    classified rows are ignored so a re-extraction never reclassifies the vocabulary.
    """
    pending = list(
        {keyword.id: keyword for keyword in keywords if keyword.classified_at is None}.values()
    )
    result = KeywordClassificationResult(pending=len(pending))
    if not pending:
        return result
    resolved = resolve_task(session, ModelRole.KEYWORD_CLASSIFICATION)
    if resolved is None:
        raise RuntimeError("No usable AI provider is configured for keyword_classification")
    batch = _classify_batch(session, pending, resolved)
    session.commit()
    result.provider_name = resolved.provider.name
    result.model_name = resolved.model
    result.add(batch)
    return result


def classify_pending_keywords(
    session: Session, *, batch_size: int = KEYWORD_CLASSIFICATION_BATCH_SIZE
) -> KeywordClassificationResult:
    """Classify the pending vocabulary in fixed batches, committing each valid batch.

    A provider or validation failure leaves that whole batch pending and the sweep moves
    on. Candidate ids are snapshotted first so a failed first batch cannot be selected
    repeatedly during the same run.
    """
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    pending_ids = list(
        session.scalars(
            select(Keyword.id)
            .where(Keyword.classified_at.is_(None))
            .order_by(Keyword.name, Keyword.id)
        )
    )
    result = KeywordClassificationResult(pending=len(pending_ids))
    if not pending_ids:
        return result
    resolved = resolve_task(session, ModelRole.KEYWORD_CLASSIFICATION)
    if resolved is None:
        raise RuntimeError("No usable AI provider is configured for keyword_classification")
    result.provider_name = resolved.provider.name
    result.model_name = resolved.model

    for offset in range(0, len(pending_ids), batch_size):
        ids = pending_ids[offset : offset + batch_size]
        keywords = list(
            session.scalars(select(Keyword).where(Keyword.id.in_(ids)).order_by(Keyword.name))
        )
        result.examined += len(keywords)
        try:
            batch = _classify_batch(session, keywords, resolved)
        except AIResponseError as exc:
            session.rollback()
            result.failed_batches += 1
            result.usage = result.usage + exc.usage
            logger.warning("Keyword-classification batch left pending: %s", exc)
            continue
        except Exception:
            session.rollback()
            result.failed_batches += 1
            logger.exception("Keyword-classification batch left pending")
            continue
        session.commit()
        # examined was counted before the call so failed batches are included.
        batch.examined = 0
        result.add(batch)
    return result


def pending_keyword_count(session: Session) -> int:
    return (
        session.scalar(
            select(func.count()).select_from(Keyword).where(Keyword.classified_at.is_(None))
        )
        or 0
    )
