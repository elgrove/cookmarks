"""add_user_book_grid_density

Revision ID: 8e916b37b495
Revises: ddf03f696722
Create Date: 2026-08-29 17:21:19.818204

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8e916b37b495'
down_revision: Union[str, Sequence[str], None] = 'ddf03f696722'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('book_grid_density', sa.String(length=20), server_default='standard', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('book_grid_density')
