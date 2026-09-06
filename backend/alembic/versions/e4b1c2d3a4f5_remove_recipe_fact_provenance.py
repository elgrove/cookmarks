"""remove recipe fact provenance and simplify ingredient model

Revision ID: e4b1c2d3a4f5
Revises: c9f172a4e5b6
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e4b1c2d3a4f5"
down_revision: Union[str, Sequence[str], None] = "c9f172a4e5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("recipe_facets") as batch_op:
        batch_op.drop_column("evidence")
        batch_op.drop_column("source")
    with op.batch_alter_table("recipe_cuisines") as batch_op:
        batch_op.drop_column("evidence")
        batch_op.drop_column("source")

    op.drop_index("ix_ingredient_occurrences_ingredient_id", table_name="ingredient_occurrences")
    op.drop_index("ix_ingredient_occurrences_line_id", table_name="ingredient_occurrences")
    op.drop_table("ingredient_occurrences")

    op.drop_index("ix_ingredient_aliases_name_folded", table_name="ingredient_aliases")
    op.drop_index("ix_ingredient_aliases_ingredient_id", table_name="ingredient_aliases")
    op.drop_table("ingredient_aliases")

    op.drop_index("ix_ingredient_lines_recipe_id", table_name="ingredient_lines")
    op.drop_table("ingredient_lines")

    op.drop_index("ix_ingredients_name_folded", table_name="ingredients")
    op.drop_table("ingredients")

    op.create_table(
        "canonical_ingredients",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(300), nullable=False, unique=True),
        sa.Column("name_folded", sa.String(300), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_canonical_ingredients_name_folded",
        "canonical_ingredients",
        ["name_folded"],
        unique=True,
    )

    op.create_table(
        "recipe_ingredients",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "recipe_id",
            sa.Uuid(),
            sa.ForeignKey("recipes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "canonical_ingredient_id",
            sa.Uuid(),
            sa.ForeignKey("canonical_ingredients.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("is_key", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("recipe_id", "position"),
    )
    op.create_index(
        "ix_recipe_ingredients_recipe_id",
        "recipe_ingredients",
        ["recipe_id"],
    )
    op.create_index(
        "ix_recipe_ingredients_canonical_ingredient_id",
        "recipe_ingredients",
        ["canonical_ingredient_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_recipe_ingredients_canonical_ingredient_id",
        table_name="recipe_ingredients",
    )
    op.drop_index(
        "ix_recipe_ingredients_recipe_id",
        table_name="recipe_ingredients",
    )
    op.drop_table("recipe_ingredients")

    op.drop_index(
        "ix_canonical_ingredients_name_folded",
        table_name="canonical_ingredients",
    )
    op.drop_table("canonical_ingredients")

    op.create_table(
        "ingredients",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(300), nullable=False, unique=True),
        sa.Column("name_folded", sa.String(300), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ingredients_name_folded", "ingredients", ["name_folded"], unique=True)

    op.create_table(
        "ingredient_lines",
        sa.Column(
            "recipe_id",
            sa.Uuid(),
            sa.ForeignKey("recipes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("ingredient", "heading", "note", name="ingredientlinekind"),
            nullable=True,
        ),
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("recipe_id", "position"),
    )
    op.create_index("ix_ingredient_lines_recipe_id", "ingredient_lines", ["recipe_id"])

    op.create_table(
        "ingredient_aliases",
        sa.Column(
            "ingredient_id",
            sa.Uuid(),
            sa.ForeignKey("ingredients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(300), nullable=False, unique=True),
        sa.Column("name_folded", sa.String(300), nullable=False, unique=True),
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_ingredient_aliases_ingredient_id", "ingredient_aliases", ["ingredient_id"]
    )
    op.create_index(
        "ix_ingredient_aliases_name_folded",
        "ingredient_aliases",
        ["name_folded"],
        unique=True,
    )

    op.create_table(
        "ingredient_occurrences",
        sa.Column(
            "line_id",
            sa.Uuid(),
            sa.ForeignKey("ingredient_lines.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "ingredient_id",
            sa.Uuid(),
            sa.ForeignKey("ingredients.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Text()),
        sa.Column("unit", sa.Text()),
        sa.Column("preparation", sa.Text()),
        sa.Column("optional", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("alternative_group", sa.Integer()),
        sa.Column("is_key", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "parse_method",
            sa.Enum("deterministic", "ai", name="ingredientparsemethod"),
            nullable=False,
        ),
        sa.Column(
            "resolution_method",
            sa.Enum(
                "canonical_name",
                "alias",
                "ai_existing",
                "ai_created",
                name="ingredientresolutionmethod",
            ),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("line_id", "position"),
    )
    op.create_index(
        "ix_ingredient_occurrences_line_id", "ingredient_occurrences", ["line_id"]
    )
    op.create_index(
        "ix_ingredient_occurrences_ingredient_id",
        "ingredient_occurrences",
        ["ingredient_id"],
    )

    with op.batch_alter_table("recipe_cuisines") as batch_op:
        batch_op.add_column(sa.Column("evidence", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "source",
                sa.Enum("explicit", "inferred", name="recipecuisinesource"),
                nullable=False,
                server_default="inferred",
            )
        )
    with op.batch_alter_table("recipe_cuisines") as batch_op:
        batch_op.alter_column("source", server_default=None)
    with op.batch_alter_table("recipe_facets") as batch_op:
        batch_op.add_column(sa.Column("evidence", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "source",
                sa.Enum("explicit", "inferred", name="recipefactsource"),
                nullable=False,
                server_default="inferred",
            )
        )
    with op.batch_alter_table("recipe_facets") as batch_op:
        batch_op.alter_column("source", server_default=None)
