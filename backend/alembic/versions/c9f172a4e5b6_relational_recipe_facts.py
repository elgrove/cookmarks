"""relational recipe facts

Revision ID: c9f172a4e5b6
Revises: 8e916b37b495, 7f82d8a85c3e
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9f172a4e5b6"
down_revision: Union[str, Sequence[str], None] = ("8e916b37b495", "7f82d8a85c3e")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "ingredients",
        sa.Column("name", sa.String(300), nullable=False, unique=True),
        sa.Column("name_folded", sa.String(300), nullable=False, unique=True),
        *_audit_columns(),
    )
    op.create_index("ix_ingredients_name_folded", "ingredients", ["name_folded"], unique=True)
    op.create_table(
        "ingredient_aliases",
        sa.Column("ingredient_id", sa.Uuid(), sa.ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(300), nullable=False, unique=True),
        sa.Column("name_folded", sa.String(300), nullable=False, unique=True),
        *_audit_columns(),
    )
    op.create_index("ix_ingredient_aliases_ingredient_id", "ingredient_aliases", ["ingredient_id"])
    op.create_index("ix_ingredient_aliases_name_folded", "ingredient_aliases", ["name_folded"], unique=True)
    op.create_table(
        "ingredient_lines",
        sa.Column("recipe_id", sa.Uuid(), sa.ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("kind", sa.Enum("ingredient", "heading", "note", name="ingredientlinekind")),
        *_audit_columns(),
        sa.UniqueConstraint("recipe_id", "position"),
    )
    op.create_index("ix_ingredient_lines_recipe_id", "ingredient_lines", ["recipe_id"])
    op.create_table(
        "ingredient_occurrences",
        sa.Column("line_id", sa.Uuid(), sa.ForeignKey("ingredient_lines.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ingredient_id", sa.Uuid(), sa.ForeignKey("ingredients.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Text()), sa.Column("unit", sa.Text()), sa.Column("preparation", sa.Text()),
        sa.Column("optional", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("alternative_group", sa.Integer()),
        sa.Column("is_key", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("parse_method", sa.Enum("deterministic", "ai", name="ingredientparsemethod"), nullable=False),
        sa.Column("resolution_method", sa.Enum("canonical_name", "alias", "ai_existing", "ai_created", name="ingredientresolutionmethod"), nullable=False),
        *_audit_columns(), sa.UniqueConstraint("line_id", "position"),
    )
    op.create_index("ix_ingredient_occurrences_line_id", "ingredient_occurrences", ["line_id"])
    op.create_index("ix_ingredient_occurrences_ingredient_id", "ingredient_occurrences", ["ingredient_id"])
    op.create_table(
        "recipe_facet_values",
        sa.Column("kind", sa.Enum("method", "course", name="recipefacetkind"), nullable=False),
        sa.Column("value_id", sa.String(100), nullable=False), sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("vocabulary_version", sa.String(40), nullable=False), *_audit_columns(),
        sa.UniqueConstraint("kind", "value_id"),
    )
    op.create_table(
        "recipe_facets",
        sa.Column("recipe_id", sa.Uuid(), sa.ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facet_value_id", sa.Uuid(), sa.ForeignKey("recipe_facet_values.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source", sa.Enum("explicit", "inferred", name="recipefactsource"), nullable=False), sa.Column("evidence", sa.Text()),
        *_audit_columns(), sa.UniqueConstraint("recipe_id", "facet_value_id"),
    )
    op.create_index("ix_recipe_facets_recipe_id", "recipe_facets", ["recipe_id"])
    op.create_index("ix_recipe_facets_facet_value_id", "recipe_facets", ["facet_value_id"])
    op.create_table(
        "recipe_cuisines",
        sa.Column("recipe_id", sa.Uuid(), sa.ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cuisine_id", sa.String(200), nullable=False),
        sa.Column("source", sa.Enum("explicit", "inferred", name="recipecuisinesource"), nullable=False), sa.Column("evidence", sa.Text()),
        *_audit_columns(), sa.UniqueConstraint("recipe_id", "cuisine_id"),
    )
    op.create_index("ix_recipe_cuisines_recipe_id", "recipe_cuisines", ["recipe_id"])
    op.create_index("ix_recipe_cuisines_cuisine_id", "recipe_cuisines", ["cuisine_id"])
    op.create_table(
        "recipe_enrichment_states",
        sa.Column("recipe_id", sa.Uuid(), sa.ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("status", sa.Enum("pending", "running", "complete", "failed", name="recipeenrichmentstatus"), nullable=False),
        sa.Column("source_fingerprint", sa.String(64)), sa.Column("schema_version", sa.String(40)),
        sa.Column("prompt_version", sa.String(40)), sa.Column("taxonomy_version", sa.String(40)),
        sa.Column("provider", sa.String(80)), sa.Column("model", sa.String(200)), sa.Column("last_error", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("task_run_id", sa.Uuid(), sa.ForeignKey("task_runs.id", ondelete="SET NULL")), *_audit_columns(),
    )
    op.create_index("ix_recipe_enrichment_states_recipe_id", "recipe_enrichment_states", ["recipe_id"], unique=True)

    connection = op.get_bind()
    recipes = connection.execute(sa.text("SELECT id, ingredients FROM recipes")).mappings()
    line_rows = []
    state_rows = []
    now = datetime.now(UTC)
    for recipe in recipes:
        recipe_id = recipe["id"]
        ingredients = recipe["ingredients"]
        if isinstance(ingredients, str):
            ingredients = json.loads(ingredients)
        for position, text in enumerate(ingredients or []):
            line_rows.append({
                "id": uuid.uuid5(uuid.NAMESPACE_URL, f"cookmarks:ingredient-line:{recipe_id}:{position}").hex,
                "recipe_id": recipe_id, "position": position, "text": text,
                "created_at": now, "updated_at": now,
            })
        state_rows.append({
            "id": uuid.uuid5(uuid.NAMESPACE_URL, f"cookmarks:enrichment:{recipe_id}").hex,
            "recipe_id": recipe_id, "status": "pending", "created_at": now, "updated_at": now,
        })
    lines = sa.table("ingredient_lines", sa.column("id"), sa.column("recipe_id"), sa.column("position"), sa.column("text"), sa.column("created_at"), sa.column("updated_at"))
    states = sa.table("recipe_enrichment_states", sa.column("id"), sa.column("recipe_id"), sa.column("status"), sa.column("created_at"), sa.column("updated_at"))
    if line_rows:
        op.bulk_insert(lines, line_rows)
    if state_rows:
        op.bulk_insert(states, state_rows)
    with op.batch_alter_table("recipes") as batch_op:
        batch_op.drop_column("ingredients")


def downgrade() -> None:
    with op.batch_alter_table("recipes") as batch_op:
        batch_op.add_column(sa.Column("ingredients", sa.JSON(), nullable=True))
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id FROM recipes")).mappings()
    for row in rows:
        texts = [item[0] for item in connection.execute(sa.text("SELECT text FROM ingredient_lines WHERE recipe_id = :id ORDER BY position"), {"id": row["id"]})]
        connection.execute(sa.text("UPDATE recipes SET ingredients = :ingredients WHERE id = :id"), {"id": row["id"], "ingredients": json.dumps(texts)})
    with op.batch_alter_table("recipes") as batch_op:
        batch_op.alter_column("ingredients", nullable=False)
    op.drop_index("ix_recipe_enrichment_states_recipe_id", table_name="recipe_enrichment_states")
    op.drop_table("recipe_enrichment_states")
    op.drop_index("ix_recipe_cuisines_cuisine_id", table_name="recipe_cuisines")
    op.drop_index("ix_recipe_cuisines_recipe_id", table_name="recipe_cuisines")
    op.drop_table("recipe_cuisines")
    op.drop_index("ix_recipe_facets_facet_value_id", table_name="recipe_facets")
    op.drop_index("ix_recipe_facets_recipe_id", table_name="recipe_facets")
    op.drop_table("recipe_facets")
    op.drop_table("recipe_facet_values")
    op.drop_index("ix_ingredient_occurrences_ingredient_id", table_name="ingredient_occurrences")
    op.drop_index("ix_ingredient_occurrences_line_id", table_name="ingredient_occurrences")
    op.drop_table("ingredient_occurrences")
    op.drop_index("ix_ingredient_lines_recipe_id", table_name="ingredient_lines")
    op.drop_table("ingredient_lines")
    op.drop_index("ix_ingredient_aliases_name_folded", table_name="ingredient_aliases")
    op.drop_index("ix_ingredient_aliases_ingredient_id", table_name="ingredient_aliases")
    op.drop_table("ingredient_aliases")
    op.drop_index("ix_ingredients_name_folded", table_name="ingredients")
    op.drop_table("ingredients")
