"""Lossless, confidence-gated deterministic ingredient parsing."""

from dataclasses import dataclass
from typing import Any

from ingredient_parser import parse_ingredient

DETERMINISTIC_PARSE_MIN_CONFIDENCE = 0.90


@dataclass(frozen=True)
class DeterministicOccurrence:
    name: str
    quantity: str | None
    unit: str | None
    preparation: str | None


@dataclass(frozen=True)
class DeterministicProposal:
    line_id: str
    occurrences: list[DeterministicOccurrence]


def _confidence(value: Any) -> float:
    return float(getattr(value, "confidence", 0))


def _text(value: Any) -> str | None:
    text = getattr(value, "text", None)
    return str(text) if text else None


def parse_line(line_id: str, text: str) -> DeterministicProposal | None:
    """Return a proposal only when the library parser maps to our shape without loss.

    A source line may contain alternate names or amounts which this deliberately
    conservative adapter leaves to the structured model call.  Confidence is a routing
    signal, never persisted as recipe data.
    """
    parsed = parse_ingredient(text, separate_names=True, string_units=True)
    names = list(parsed.name or [])
    amounts = list(parsed.amount or [])
    preparation_value = parsed.preparation
    preparations = [] if preparation_value is None else [preparation_value]
    if not names or len(amounts) > 1 or len(preparations) > 1:
        return None
    values = [*names, *amounts, *preparations]
    if any(_confidence(value) < DETERMINISTIC_PARSE_MIN_CONFIDENCE for value in values):
        return None
    amount = amounts[0] if amounts else None
    preparation = preparations[0] if preparations else None
    quantity = _text(amount)
    unit = str(getattr(amount, "unit", "")) or None if amount else None
    # The parser's amount text includes its unit. It is still the faithful source-like
    # representation and avoids inventing numeric conversion data.
    return DeterministicProposal(
        line_id=line_id,
        occurrences=[
            DeterministicOccurrence(
                name=str(name.text),
                quantity=quantity,
                unit=unit,
                preparation=_text(preparation),
            )
            for name in names
        ],
    )
