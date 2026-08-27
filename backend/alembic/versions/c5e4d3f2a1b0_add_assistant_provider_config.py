from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c5e4d3f2a1b0"
down_revision: Union[str, Sequence[str], None] = "bf82b8e02704"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("config", schema=None) as batch_op:
        batch_op.add_column(sa.Column("assistant_provider", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("assistant_api_key", sa.String(length=200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("config", schema=None) as batch_op:
        batch_op.drop_column("assistant_api_key")
        batch_op.drop_column("assistant_provider")
