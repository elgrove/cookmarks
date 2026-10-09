"""Report dietary, season, and seasonal-word compound keywords without changing data.

    cd backend && uv run python -m scripts.audit_keyword_candidates

The report is deterministic and read-only. It is evidence for a later decision about
possible categories; this command never assigns a category.
"""

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.recipe import Keyword, recipe_keywords

DIETARY_TERMS = frozenset(
    {
        "dairy-free",
        "gluten-free",
        "halal",
        "keto",
        "kosher",
        "low-carb",
        "nut-free",
        "pescatarian",
        "plant-based",
        "vegan",
        "vegetarian",
    }
)
SEASON_TERMS = frozenset({"spring", "summer", "autumn", "winter", "seasonal"})
SEASON_WORD_RE = re.compile(r"\b(?:spring|summer|autumn|winter)\b", re.IGNORECASE)


def audit_rows(
    session: Session,
) -> tuple[list[tuple[str, int]], list[tuple[str, int]], list[tuple[str, int]]]:
    rows = session.execute(
        select(Keyword.name, func.count(recipe_keywords.c.recipe_id))
        .outerjoin(recipe_keywords, recipe_keywords.c.keyword_id == Keyword.id)
        .group_by(Keyword.id, Keyword.name)
        .order_by(func.lower(Keyword.name), Keyword.name)
    ).all()
    dietary: list[tuple[str, int]] = []
    seasons: list[tuple[str, int]] = []
    compounds: list[tuple[str, int]] = []
    for name, recipe_count in rows:
        folded = name.casefold()
        item = (name, recipe_count)
        if folded in DIETARY_TERMS:
            dietary.append(item)
        if folded in SEASON_TERMS:
            seasons.append(item)
        elif SEASON_WORD_RE.search(name):
            compounds.append(item)
    return dietary, seasons, compounds


def _section(title: str, rows: list[tuple[str, int]]) -> list[str]:
    lines = [title]
    lines.extend(f"{name}\t{count}" for name, count in rows)
    if not rows:
        lines.append("(none)")
    return lines


def build_report(session: Session) -> str:
    dietary, seasons, compounds = audit_rows(session)
    lines = ["keyword\trecipe_uses"]
    lines.extend(_section("\nDietary exact terms", dietary))
    lines.extend(_section("\nSeason exact terms", seasons))
    lines.extend(_section("\nSeasonal-word compounds (review as false-positive risks)", compounds))
    return "\n".join(lines)


def main() -> None:
    with SessionLocal() as session:
        print(build_report(session))


if __name__ == "__main__":
    main()
