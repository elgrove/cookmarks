from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f5c2d3e4a6b7"
down_revision: Union[str, Sequence[str], None] = "e4b1c2d3a4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    provider_enum = sa.Enum("ANTHROPIC", "GEMINI", "OPENROUTER", "STUB", name="aiprovider")
    with op.batch_alter_table("config", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("enrichment_stage1_provider", provider_enum, nullable=True)
        )
        batch_op.add_column(
            sa.Column("enrichment_stage1_api_key", sa.String(length=200), nullable=True)
        )
        batch_op.add_column(
            sa.Column("enrichment_stage2_provider", provider_enum, nullable=True)
        )
        batch_op.add_column(
            sa.Column("enrichment_stage2_api_key", sa.String(length=200), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("config", schema=None) as batch_op:
        batch_op.drop_column("enrichment_stage2_api_key")
        batch_op.drop_column("enrichment_stage2_provider")
        batch_op.drop_column("enrichment_stage1_api_key")
        batch_op.drop_column("enrichment_stage1_provider")
