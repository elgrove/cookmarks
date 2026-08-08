"""recipe-anchored reading progress

Revision ID: c7d8e9f0a1b2
Revises: b5c9d1e2f3a4
Create Date: 2026-08-08 21:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, Sequence[str], None] = 'b5c9d1e2f3a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Progress is measured in recipes in both modes, so the page fraction gives way to
    # the furthest recipe reached. Existing fractions can't be mapped to a recipe, so
    # in-flight readings start again from their anchor.
    with op.batch_alter_table('book_readings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('anchor_recipe_id', sa.Uuid(), nullable=True))
        batch_op.add_column(
            sa.Column('finished', sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.create_foreign_key(
            'fk_book_readings_anchor_recipe', 'recipes', ['anchor_recipe_id'], ['id'],
            ondelete='SET NULL',
        )
        batch_op.drop_column('fraction')


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('book_readings', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('fraction', sa.Float(), nullable=False, server_default='0')
        )
        batch_op.drop_constraint('fk_book_readings_anchor_recipe', type_='foreignkey')
        batch_op.drop_column('finished')
        batch_op.drop_column('anchor_recipe_id')
