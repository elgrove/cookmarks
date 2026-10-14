"""The FTS5 search index behind recipe search.

This module owns a single FTS5 virtual table, ``recipe_search``, holding one
concatenated document per recipe: name, book title and author, ingredient lines,
canonical ingredients and keywords. It replaces per-term ``%term%`` LIKE scans across
``recipes``, ``books`` and ``recipe_ingredients`` — at 29k recipes and 300k ingredient
rows those cost 0.5-1s per query, and every facet request repeated the whole scan.

The table lives outside the ORM and Alembic's metadata (like the vec0
``recipe_embeddings`` table): it is a derived index, not a source of truth. It is kept
current by **SQLite triggers**, not application code, so every write path stays in
sync automatically — re-extraction, book retitle, keyword rename,
canonical-ingredient assignment, recipe deletion. ``index_statements`` is the single
definition shared by the Alembic migration, the app's test fixtures and the reindex
script, so the shape can never drift between them.

Matching is **prefix**, not substring: a term ``anchov`` finds ``anchovy`` but
``chovy`` does not. That is the deliberate trade for index speed — see ``match_query``.
"""

from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

# The searchable document for one recipe, assembled from its own row plus its book,
# ingredients, canonical ingredients and keywords. Built from the *folded* name/title/
# author columns so accent-stripping matches the rest of the app; FTS5's
# remove_diacritics 2 then covers the raw ingredient and keyword text.
_DOCUMENT = (
    "coalesce({name_folded}, '') || ' ' || "
    "coalesce((SELECT b.title_folded || ' ' || b.author_folded FROM books b "
    "WHERE b.id = {book_id}), '') || ' ' || "
    "coalesce((SELECT group_concat(ri.text, ' ') FROM recipe_ingredients ri "
    "WHERE ri.recipe_id = {recipe_id}), '') || ' ' || "
    "coalesce((SELECT group_concat(ci.name_folded, ' ') FROM recipe_ingredients ri "
    "JOIN canonical_ingredients ci ON ci.id = ri.canonical_ingredient_id "
    "WHERE ri.recipe_id = {recipe_id}), '') || ' ' || "
    "coalesce((SELECT group_concat(k.name, ' ') FROM recipe_keywords rk "
    "JOIN keywords k ON k.id = rk.keyword_id WHERE rk.recipe_id = {recipe_id}), '')"
)

_TABLE_DDL = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS recipe_search USING fts5("
    "recipe_id UNINDEXED, doc, tokenize='unicode61 remove_diacritics 2')"
)


def _document(recipe_id: str, book_id: str, name_folded: str) -> str:
    return _DOCUMENT.format(recipe_id=recipe_id, book_id=book_id, name_folded=name_folded)


def _refresh_one(recipe_id: str) -> str:
    """A trigger body that rebuilds one recipe's row (delete then re-insert)."""
    document = _document("r.id", "r.book_id", "r.name_folded")
    return (
        f"DELETE FROM recipe_search WHERE recipe_id = {recipe_id}; "
        f"INSERT INTO recipe_search(recipe_id, doc) "
        f"SELECT r.id, {document} FROM recipes r WHERE r.id = {recipe_id};"
    )


def _refresh_set(selection: str) -> str:
    """A trigger body that rebuilds every recipe named by ``selection`` — a subquery,
    or a comma-separated list such as ``old.recipe_id, new.recipe_id``."""
    document = _document("r.id", "r.book_id", "r.name_folded")
    return (
        f"DELETE FROM recipe_search WHERE recipe_id IN ({selection}); "
        f"INSERT INTO recipe_search(recipe_id, doc) SELECT r.id, {document} FROM recipes r "
        f"WHERE r.id IN ({selection});"
    )


def _trigger_specs() -> dict[str, tuple[str, str]]:
    """One trigger per way the document can change, so the index never needs an
    application hook. Keyed by trigger name (used for the DDL and the drops) with the
    ``(AFTER clause, body)`` pair as value."""
    return {
        "recipe_search_recipe_insert": ("AFTER INSERT ON recipes", _refresh_one("new.id")),
        "recipe_search_recipe_update": (
            "AFTER UPDATE OF name, book_id ON recipes",
            _refresh_one("new.id"),
        ),
        "recipe_search_recipe_delete": (
            "AFTER DELETE ON recipes",
            "DELETE FROM recipe_search WHERE recipe_id = old.id;",
        ),
        "recipe_search_book_update": (
            "AFTER UPDATE OF title, author ON books",
            _refresh_set("SELECT id FROM recipes WHERE book_id = new.id"),
        ),
        "recipe_search_ingredient_insert": (
            "AFTER INSERT ON recipe_ingredients",
            _refresh_one("new.recipe_id"),
        ),
        "recipe_search_ingredient_update": (
            # Refresh both sides: a line's recipe_id is not expected to change, but if
            # it ever is re-pointed the old recipe must not keep the stale text.
            "AFTER UPDATE ON recipe_ingredients",
            _refresh_set("old.recipe_id, new.recipe_id"),
        ),
        "recipe_search_ingredient_delete": (
            "AFTER DELETE ON recipe_ingredients",
            _refresh_one("old.recipe_id"),
        ),
        "recipe_search_keyword_link_insert": (
            "AFTER INSERT ON recipe_keywords",
            _refresh_one("new.recipe_id"),
        ),
        "recipe_search_keyword_link_delete": (
            "AFTER DELETE ON recipe_keywords",
            _refresh_one("old.recipe_id"),
        ),
        "recipe_search_keyword_update": (
            "AFTER UPDATE OF name ON keywords",
            _refresh_set("SELECT recipe_id FROM recipe_keywords WHERE keyword_id = new.id"),
        ),
        "recipe_search_canonical_update": (
            "AFTER UPDATE OF name ON canonical_ingredients",
            _refresh_set(
                "SELECT recipe_id FROM recipe_ingredients WHERE canonical_ingredient_id = new.id"
            ),
        ),
    }


def index_statements() -> list[str]:
    """The full DDL: the FTS5 table then its sync triggers."""
    triggers = [
        f"CREATE TRIGGER IF NOT EXISTS {name} {clause} BEGIN {body} END;"
        for name, (clause, body) in _trigger_specs().items()
    ]
    return [_TABLE_DDL, *triggers]


def drop_statements() -> list[str]:
    """Tear the index down — the migration's downgrade."""
    drops = [f"DROP TRIGGER IF EXISTS {name}" for name in _trigger_specs()]
    return [*drops, "DROP TABLE IF EXISTS recipe_search"]


def backfill_statement() -> str:
    """One row per recipe, built from the current data in a single pass — for the
    migration and the reindex script, not for per-write use. **Insert-only**: it does
    not clear existing rows, so callers must start from an empty index (the migration
    creates a fresh table; ``reindex_all`` deletes first)."""
    document = _document("r.id", "r.book_id", "r.name_folded")
    return f"INSERT INTO recipe_search(recipe_id, doc) SELECT r.id, {document} FROM recipes r"


def ensure_search_index(session: Session) -> None:
    """Create the table and triggers if they are missing. Idempotent; safe to call on
    every connection/fixture setup."""
    for statement in index_statements():
        session.execute(text(statement))
    session.commit()


def reindex_all(session: Session) -> int:
    """Drop and rebuild the whole index from source data — the reindex script's job,
    and the recovery path if the index ever drifts."""
    ensure_search_index(session)
    session.execute(text("DELETE FROM recipe_search"))
    session.execute(text(backfill_statement()))
    session.commit()
    return int(session.scalar(text("SELECT count(*) FROM recipe_search")) or 0)


def match_query(terms: Sequence[str]) -> str:
    """Turn already-folded terms into an FTS5 MATCH expression.

    Each term is quoted (so punctuation can't be read as FTS syntax) and suffixed
    with ``*`` for prefix matching, then AND-ed: every term must appear. A term that
    arrived as a quoted phrase keeps its spaces and matches as a phrase prefix.
    """
    parts = []
    for term in terms:
        if not term:
            continue
        escaped = term.replace('"', '""')
        parts.append(f'"{escaped}"*')
    return " AND ".join(parts)
