"""reading mode

Revision ID: b5c9d1e2f3a4
Revises: aa47490e5991
Create Date: 2026-08-08 21:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5c9d1e2f3a4'
down_revision: Union[str, Sequence[str], None] = 'aa47490e5991'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('book_readings', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'mode',
                sa.Enum('book', 'recipes', name='readingmode'),
                nullable=False,
                server_default='book',
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('book_readings', schema=None) as batch_op:
        batch_op.drop_column('mode')
