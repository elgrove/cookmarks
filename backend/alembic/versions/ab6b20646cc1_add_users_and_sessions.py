"""add users and sessions

Revision ID: ab6b20646cc1
Revises: b76837b88109
Create Date: 2026-08-04 23:34:57.224933

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ab6b20646cc1'
down_revision: Union[str, Sequence[str], None] = 'b76837b88109'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('users',
    sa.Column('username', sa.String(length=100), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('is_admin', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('username')
    )
    op.create_table('user_sessions',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_sessions_token_hash'), ['token_hash'], unique=True)
        batch_op.create_index(batch_op.f('ix_user_sessions_user_id'), ['user_id'], unique=False)

    # Nullable: no user exists yet at migration time. The first user created adopts
    # every orphan list, which is what carries an existing deployment's Favourites over.
    with op.batch_alter_table('recipe_lists', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Uuid(), nullable=True))
        batch_op.create_index(batch_op.f('ix_recipe_lists_user_id'), ['user_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_recipe_lists_user_id_users', 'users', ['user_id'], ['id'], ondelete='CASCADE'
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('recipe_lists', schema=None) as batch_op:
        batch_op.drop_constraint('fk_recipe_lists_user_id_users', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_recipe_lists_user_id'))
        batch_op.drop_column('user_id')

    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_sessions_user_id'))
        batch_op.drop_index(batch_op.f('ix_user_sessions_token_hash'))

    op.drop_table('user_sessions')
    op.drop_table('users')
