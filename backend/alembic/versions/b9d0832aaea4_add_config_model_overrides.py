"""add config model_overrides

Revision ID: b9d0832aaea4
Revises: bcc69efeffc5
Create Date: 2026-06-02 22:13:48.126251

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b9d0832aaea4'
down_revision: Union[str, Sequence[str], None] = 'bcc69efeffc5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nullable: existing Config rows keep provider defaults (no overrides) until set.
    with op.batch_alter_table('config', schema=None) as batch_op:
        batch_op.add_column(sa.Column('model_overrides', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('config', schema=None) as batch_op:
        batch_op.drop_column('model_overrides')
