"""rename task_runs book_id index

Revision ID: 7c1b3a9e5d20
Revises: 219faab92061
Create Date: 2026-08-09 22:45:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '7c1b3a9e5d20'
down_revision: Union[str, Sequence[str], None] = '219faab92061'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """The extraction_runs -> task_runs table rename kept the old index name; bring it
    in line with the model so autogenerate stops proposing this rename forever."""
    with op.batch_alter_table('task_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_extraction_runs_book_id'))
        batch_op.create_index(batch_op.f('ix_task_runs_book_id'), ['book_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('task_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_task_runs_book_id'))
        batch_op.create_index(batch_op.f('ix_extraction_runs_book_id'), ['book_id'], unique=False)
