"""remove recipe fact provenance

Revision ID: e4b1c2d3a4f5
Revises: c9f172a4e5b6
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e4b1c2d3a4f5"
down_revision: Union[str, Sequence[str], None] = "c9f172a4e5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("recipe_facets") as batch_op:
        batch_op.drop_column("evidence")
        batch_op.drop_column("source")
    with op.batch_alter_table("recipe_cuisines") as batch_op:
        batch_op.drop_column("evidence")
        batch_op.drop_column("source")


def downgrade() -> None:
    with op.batch_alter_table("recipe_cuisines") as batch_op:
        batch_op.add_column(sa.Column("evidence", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "source",
                sa.Enum("explicit", "inferred", name="recipecuisinesource"),
                nullable=False,
                server_default="inferred",
            )
        )
    with op.batch_alter_table("recipe_cuisines") as batch_op:
        batch_op.alter_column("source", server_default=None)
    with op.batch_alter_table("recipe_facets") as batch_op:
        batch_op.add_column(sa.Column("evidence", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "source",
                sa.Enum("explicit", "inferred", name="recipefactsource"),
                nullable=False,
                server_default="inferred",
            )
        )
    with op.batch_alter_table("recipe_facets") as batch_op:
        batch_op.alter_column("source", server_default=None)
