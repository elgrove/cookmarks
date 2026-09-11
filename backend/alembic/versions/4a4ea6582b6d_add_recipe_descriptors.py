"""add recipe descriptors

Revision ID: 4a4ea6582b6d
Revises: 2b291e248bea
Create Date: 2026-09-11 20:50:00.000000

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "4a4ea6582b6d"
down_revision: str | Sequence[str] | None = "2b291e248bea"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("recipes") as batch_op:
        batch_op.add_column(sa.Column("alternate_name", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("summary", sa.String(length=500), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("recipes") as batch_op:
        batch_op.drop_column("summary")
        batch_op.drop_column("alternate_name")
