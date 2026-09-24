"""Shared keyword vocabulary.

Recipes and books both draw their tags from the one `keywords` table; this is the
single place that interns a name into a `Keyword` row, creating it on first use so
the vocabulary stays shared (a tag on a book and the same tag on a recipe are one
row, and counts unify across the app).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.recipe import Keyword
from app.text import normalise_keyword


def get_or_create_keyword(
    session: Session, name: str, *, created: list[Keyword] | None = None
) -> Keyword:
    """Return the canonical lower-case row for ``name``, creating it if absent."""
    name = normalise_keyword(name)
    keyword = session.scalar(select(Keyword).where(Keyword.name == name))
    if keyword is None:
        keyword = Keyword(name=name)
        session.add(keyword)
        session.flush()
        if created is not None:
            created.append(keyword)
    return keyword


def get_or_create_keywords(
    session: Session, names: list[str], *, created: list[Keyword] | None = None
) -> list[Keyword]:
    """Return distinct canonical rows in input order.

    Several input spellings can normalise to one identity. Do not attach that row
    twice to the same recipe or book association.
    """
    keywords: list[Keyword] = []
    seen: set[object] = set()
    for name in names:
        keyword = get_or_create_keyword(session, name, created=created)
        if keyword.id in seen:
            continue
        seen.add(keyword.id)
        keywords.append(keyword)
    return keywords
