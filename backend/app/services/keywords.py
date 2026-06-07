"""Shared keyword vocabulary.

Recipes and books both draw their tags from the one `keywords` table; this is the
single place that interns a name into a `Keyword` row, creating it on first use so
the vocabulary stays shared (a tag on a book and the same tag on a recipe are one
row, and counts unify across the app).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.recipe import Keyword


def get_or_create_keyword(session: Session, name: str) -> Keyword:
    """Return the `Keyword` row for `name`, creating and flushing it if absent."""
    keyword = session.scalar(select(Keyword).where(Keyword.name == name))
    if keyword is None:
        keyword = Keyword(name=name)
        session.add(keyword)
        session.flush()
    return keyword
