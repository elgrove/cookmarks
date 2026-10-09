"""normalise keyword names

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1

Keyword names are identities, not display titles. Merge names that differ only by
case or whitespace, store the surviving name in lower case, and reject future raw
SQLite writes that would reintroduce common casing or spacing variants.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, Sequence[str], None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _normalise(value: str) -> str:
    return " ".join(value.split()).casefold()


def _move_associations(
    connection: sa.Connection,
    table: str,
    owner_column: str,
    duplicate_id: str,
    canonical_id: str,
) -> None:
    connection.execute(
        sa.text(
            f"""INSERT OR IGNORE INTO {table} ({owner_column}, keyword_id)
                SELECT {owner_column}, :canonical_id
                FROM {table}
                WHERE keyword_id = :duplicate_id"""
        ),
        {"canonical_id": canonical_id, "duplicate_id": duplicate_id},
    )
    connection.execute(
        sa.text(f"DELETE FROM {table} WHERE keyword_id = :duplicate_id"),
        {"duplicate_id": duplicate_id},
    )


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """SELECT id, name, category, classified_at
               FROM keywords
               ORDER BY created_at, id"""
        )
    ).mappings()
    groups: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        groups.setdefault(_normalise(str(row["name"])), []).append(dict(row))

    for normalised, variants in groups.items():
        canonical = next(
            (row for row in variants if row["name"] == normalised),
            variants[0],
        )
        canonical_id = str(canonical["id"])
        classified = next(
            (row for row in variants if row["classified_at"] is not None),
            None,
        )
        if canonical["classified_at"] is None and classified is not None:
            connection.execute(
                sa.text(
                    """UPDATE keywords
                       SET category = :category, classified_at = :classified_at
                       WHERE id = :canonical_id"""
                ),
                {
                    "category": classified["category"],
                    "classified_at": classified["classified_at"],
                    "canonical_id": canonical_id,
                },
            )

        for duplicate in variants:
            duplicate_id = str(duplicate["id"])
            if duplicate_id == canonical_id:
                continue
            _move_associations(
                connection,
                "recipe_keywords",
                "recipe_id",
                duplicate_id,
                canonical_id,
            )
            _move_associations(
                connection,
                "book_keywords",
                "book_id",
                duplicate_id,
                canonical_id,
            )
            connection.execute(
                sa.text("DELETE FROM keywords WHERE id = :duplicate_id"),
                {"duplicate_id": duplicate_id},
            )

        connection.execute(
            sa.text("UPDATE keywords SET name = :name WHERE id = :canonical_id"),
            {"name": normalised, "canonical_id": canonical_id},
        )

    op.execute(
        """CREATE TRIGGER keywords_name_normalised_insert
           BEFORE INSERT ON keywords
           WHEN NEW.name != lower(trim(NEW.name)) OR instr(NEW.name, '  ') > 0
           BEGIN
               SELECT RAISE(ABORT, 'keyword name must be lower-case with normalised whitespace');
           END"""
    )
    op.execute(
        """CREATE TRIGGER keywords_name_normalised_update
           BEFORE UPDATE OF name ON keywords
           WHEN NEW.name != lower(trim(NEW.name)) OR instr(NEW.name, '  ') > 0
           BEGIN
               SELECT RAISE(ABORT, 'keyword name must be lower-case with normalised whitespace');
           END"""
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS keywords_name_normalised_update")
    op.execute("DROP TRIGGER IF EXISTS keywords_name_normalised_insert")
