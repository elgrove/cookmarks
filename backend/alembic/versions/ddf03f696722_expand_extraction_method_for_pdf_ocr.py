"""expand extraction method for PDF OCR

Revision ID: ddf03f696722
Revises: c5e4d3f2a1b0
Create Date: 2026-08-27 22:26:48.258569

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ddf03f696722"
down_revision: str | Sequence[str] | None = "c5e4d3f2a1b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("task_runs", schema=None) as batch_op:
        batch_op.alter_column(
            "extraction_method",
            existing_type=sa.VARCHAR(length=5),
            type_=sa.Enum("file", "block", "pdf_ocr", name="extractionmethod"),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("task_runs", schema=None) as batch_op:
        batch_op.alter_column(
            "extraction_method",
            existing_type=sa.Enum(
                "file", "block", "pdf_ocr", name="extractionmethod"
            ),
            type_=sa.VARCHAR(length=5),
            existing_nullable=True,
        )
