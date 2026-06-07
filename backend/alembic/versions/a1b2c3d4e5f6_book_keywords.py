"""book keywords (book↔keyword association) + merge config/keyword-index heads

Revision ID: a1b2c3d4e5f6
Revises: c4867b517317, b9d0832aaea4
Create Date: 2026-06-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
# Doubles as a merge: the keyword-index branch and the config branch had diverged
# from the initial schema into two heads; this brings them back to one.
down_revision: Union[str, Sequence[str], None] = ('c4867b517317', 'b9d0832aaea4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'book_keywords',
        sa.Column('book_id', sa.Uuid(), nullable=False),
        sa.Column('keyword_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['book_id'], ['books.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['keyword_id'], ['keywords.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('book_id', 'keyword_id'),
    )
    # Mirrors recipe_keywords: a standing index on keyword_id so shared-keyword joins
    # and group-by on keyword_id don't make SQLite build a transient index per call.
    op.create_index(
        'ix_book_keywords_keyword_id', 'book_keywords', ['keyword_id'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_book_keywords_keyword_id', table_name='book_keywords')
    op.drop_table('book_keywords')
