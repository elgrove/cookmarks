"""add calibre exclusions

Revision ID: b76837b88109
Revises: d7e1f2a3b4c5
Create Date: 2026-07-31 22:39:08.735769

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b76837b88109'
down_revision: Union[str, Sequence[str], None] = 'd7e1f2a3b4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('calibre_exclusions',
    sa.Column('calibre_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.PrimaryKeyConstraint('calibre_id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('calibre_exclusions')
