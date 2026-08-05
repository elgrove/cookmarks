"""add recipe views

Revision ID: d810cc6f7c91
Revises: ab6b20646cc1
Create Date: 2026-08-05 20:30:27.219155

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd810cc6f7c91'
down_revision: Union[str, Sequence[str], None] = 'ab6b20646cc1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('recipe_views',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('recipe_id', sa.Uuid(), nullable=False),
    sa.Column('view_count', sa.Integer(), nullable=False),
    sa.Column('last_viewed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['recipe_id'], ['recipes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'recipe_id')
    )
    op.create_index('ix_recipe_views_recipe_id', 'recipe_views', ['recipe_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_recipe_views_recipe_id', table_name='recipe_views')
    op.drop_table('recipe_views')
