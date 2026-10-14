"""recipe search FTS5 index

Revision ID: a7c3e9f1b2d4
Revises: f7a8b9c0d1e2
Create Date: 2026-10-14 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op

from app.services.search_index import backfill_statement, drop_statements, index_statements


# revision identifiers, used by Alembic.
revision: str = "a7c3e9f1b2d4"
down_revision: Union[str, Sequence[str], None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the FTS5 search index and its sync triggers, then backfill it in one
    pass from the current data."""
    for statement in index_statements():
        op.execute(statement)
    op.execute("DELETE FROM recipe_search")
    op.execute(backfill_statement())


def downgrade() -> None:
    """Drop the triggers and the index."""
    for statement in drop_statements():
        op.execute(statement)
