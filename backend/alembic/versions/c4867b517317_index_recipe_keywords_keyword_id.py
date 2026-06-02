"""index recipe_keywords.keyword_id

Revision ID: c4867b517317
Revises: 73f5bb9f4b28
Create Date: 2026-06-02 20:21:24.237609

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4867b517317'
down_revision: Union[str, Sequence[str], None] = '73f5bb9f4b28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # The (recipe_id, keyword_id) PK can't serve a group-by on keyword_id, so the
    # keyword facets and the /api/keywords list made SQLite build a transient index
    # per call. A standing index on keyword_id removes that.
    op.create_index(
        "ix_recipe_keywords_keyword_id", "recipe_keywords", ["keyword_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_recipe_keywords_keyword_id", table_name="recipe_keywords")
