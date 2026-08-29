"""add cooking_instructions to users

Revision ID: 7f82d8a85c3e
Revises: ddf03f696722
Create Date: 2026-08-29 16:52:01.202010

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f82d8a85c3e'
down_revision: Union[str, Sequence[str], None] = 'ddf03f696722'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cooking_instructions', sa.String(length=4000), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('cooking_instructions')
