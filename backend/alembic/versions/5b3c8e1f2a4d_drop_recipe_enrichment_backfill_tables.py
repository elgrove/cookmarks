"""drop recipe enrichment backfill tables

Revision ID: 5b3c8e1f2a4d
Revises: 4a4ea6582b6d
Create Date: 2026-09-13 00:00:00.000000

The batch engine is removed (MY-184); drop its temporary batch tracking
tables. This is data-destructive with no restore beyond re-running the
backfill — downgrade recreates the schema only. The task_runs.task_type
column is left untouched so historical pilot/backfill runs still read.
"""

from typing import Sequence

from alembic import op

revision: str = "5b3c8e1f2a4d"
down_revision: str | Sequence[str] | None = "4a4ea6582b6d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("recipe_enrichment_batch_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_recipe_enrichment_batch_items_request_key"))
        batch_op.drop_index(batch_op.f("ix_recipe_enrichment_batch_items_recipe_id"))
        batch_op.drop_index(batch_op.f("ix_recipe_enrichment_batch_items_batch_id"))

    op.drop_table("recipe_enrichment_batch_items")
    with op.batch_alter_table("recipe_enrichment_batches", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_recipe_enrichment_batches_task_run_id"))
        batch_op.drop_index(batch_op.f("ix_recipe_enrichment_batches_job_key"))
        batch_op.drop_index(batch_op.f("ix_recipe_enrichment_batches_display_name"))

    op.drop_table("recipe_enrichment_batches")


def downgrade() -> None:
    op.create_table(
        "recipe_enrichment_batches",
        sa.Column("task_run_id", sa.Uuid(), nullable=False),
        sa.Column("job_key", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=300), nullable=False),
        sa.Column("provider_batch_id", sa.String(length=200), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "preparing",
                "submitted",
                "succeeded",
                "failed",
                "cancelled",
                "applied",
                name="enrichmentbatchstatus",
            ),
            nullable=False,
        ),
        sa.Column("stage", sa.String(length=20), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("input_file_id", sa.String(length=200), nullable=True),
        sa.Column("result_file_id", sa.String(length=200), nullable=True),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("submitted_keys", sa.JSON(), nullable=False),
        sa.Column("prompt_version", sa.String(length=40), nullable=True),
        sa.Column("schema_version", sa.String(length=40), nullable=True),
        sa.Column("taxonomy_version", sa.String(length=40), nullable=True),
        sa.Column("provider", sa.String(length=80), nullable=True),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("duplicate_ids", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_run_id"], ["task_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_batch_id"),
    )
    with op.batch_alter_table("recipe_enrichment_batches", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_recipe_enrichment_batches_display_name"),
            ["display_name"],
            unique=True,
        )
        batch_op.create_index(
            batch_op.f("ix_recipe_enrichment_batches_job_key"), ["job_key"], unique=True
        )
        batch_op.create_index(
            batch_op.f("ix_recipe_enrichment_batches_task_run_id"),
            ["task_run_id"],
            unique=False,
        )

    op.create_table(
        "recipe_enrichment_batch_items",
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("recipe_id", sa.Uuid(), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("request_key", sa.String(length=100), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "succeeded",
                "failed",
                "stale",
                "applied",
                name="enrichmentbatchitemstatus",
            ),
            nullable=False,
        ),
        sa.Column("provider_error", sa.Text(), nullable=True),
        sa.Column("provider_code", sa.String(length=100), nullable=True),
        sa.Column("usage", sa.JSON(), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stage1_ingredients", sa.JSON(), nullable=False),
        sa.Column("stage1_response", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["recipe_enrichment_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id", "request_key", name="uq_batch_item_request_key"),
    )
    with op.batch_alter_table("recipe_enrichment_batch_items", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_recipe_enrichment_batch_items_batch_id"),
            ["batch_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_recipe_enrichment_batch_items_recipe_id"),
            ["recipe_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_recipe_enrichment_batch_items_request_key"),
            ["request_key"],
            unique=False,
        )
