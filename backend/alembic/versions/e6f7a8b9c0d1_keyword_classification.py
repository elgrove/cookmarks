"""add keyword classification state

Revision ID: e6f7a8b9c0d1
Revises: a189cf7d2e4b
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, Sequence[str], None] = "a189cf7d2e4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "keywords",
        sa.Column(
            "category",
            sa.Enum(
                "cuisine_region",
                "course",
                "key_ingredient",
                "method",
                name="keywordcategory",
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "keywords",
        sa.Column("classified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_keywords_classified_at", "keywords", ["classified_at"])


def downgrade() -> None:
    op.drop_index("ix_keywords_classified_at", table_name="keywords")
    op.drop_column("keywords", "classified_at")
    op.drop_column("keywords", "category")
