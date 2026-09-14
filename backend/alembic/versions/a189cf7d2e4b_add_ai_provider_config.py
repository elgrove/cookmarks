"""add AI provider config and task assignments

Revision ID: a189cf7d2e4b
Revises: 5b3c8e1f2a4d

Replaces the group-based provider fields on Config (extraction / assistant /
enrichment-stage-1 / enrichment-stage-2 provider + key) and the global
`model_overrides` map with two tables:

* `ai_provider_configs` — one row per provider: write-only API key, saved display
  order, and the usable model-ID list (seeded from each provider class's current
  `models` recommendations).
* `ai_task_assignments` — explicit (role, provider, model) rows, with an ordered
  sequence for the recipe-ingredient role (primary + fallbacks).

Key migration rule: the distinct non-empty legacy keys for a provider are preserved
only when they agree. When one provider has different non-empty keys across the
legacy fields, no key is migrated and the administrator must enter one, rather
than the migration silently choosing a secret.

Explicit assignments reproduce the legacy choices: model overrides become rows
under the provider that owned the role, the assistant / ingredient-primary /
ingredient-fallback / semantics selections become rows (falling back to the
provider's current recommendation where no override exists), and the legacy
extraction provider goes first in display order so unassigned tasks keep
resolving to it.

Downgrade restores the legacy columns empty and drops the new tables: API keys
are not copied back, so a downgrade needs the keys re-entered.
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a189cf7d2e4b"
down_revision: Union[str, Sequence[str], None] = "5b3c8e1f2a4d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The providers surfaced in the settings UI, in catalogue order.
PROVIDERS = ("ANTHROPIC", "GEMINI", "OPENROUTER")

# Seed model lists: the union of each provider class's current `models`
# recommendations (app/services/ai/anthropic.py, gemini.py, openrouter.py).
SEED_MODELS: dict[str, list[str]] = {
    "ANTHROPIC": ["claude-haiku-4-5-20251001", "claude-sonnet-5"],
    "GEMINI": ["gemini-2.5-flash", "gemini-2.5-flash-lite"],
    "OPENROUTER": [
        "anthropic/claude-haiku-4.5",
        "google/gemini-2.5-flash",
        "google/gemini-2.5-flash-lite",
        "openai/gpt-oss-120b",
    ],
}

# Per-role recommendations from the same provider classes, used only where the
# legacy config selected a provider without a model override for the role.
RECOMMENDATIONS: dict[str, dict[str, str]] = {
    "ANTHROPIC": {
        "image_match": "claude-sonnet-5",
        "many_recipes_per_file": "claude-sonnet-5",
        "one_recipe_per_file": "claude-sonnet-5",
        "blocks_of_files": "claude-sonnet-5",
        "book_keywords": "claude-sonnet-5",
        "keyword_dedup": "claude-sonnet-5",
        "ingredient_dedup": "claude-sonnet-5",
        "assistant": "claude-sonnet-5",
        "recipe_enrichment": "claude-sonnet-5",
        "recipe_ingredients": "claude-haiku-4-5-20251001",
        "recipe_ingredients_fallback": "claude-haiku-4-5-20251001",
        "recipe_semantics": "claude-haiku-4-5-20251001",
    },
    "GEMINI": {
        "image_match": "gemini-2.5-flash",
        "ocr": "gemini-2.5-flash",
        "many_recipes_per_file": "gemini-2.5-flash-lite",
        "one_recipe_per_file": "gemini-2.5-flash-lite",
        "blocks_of_files": "gemini-2.5-flash",
        "book_keywords": "gemini-2.5-flash",
        "keyword_dedup": "gemini-2.5-flash",
        "ingredient_dedup": "gemini-2.5-flash",
        "assistant": "gemini-2.5-flash",
        "recipe_enrichment": "gemini-2.5-flash",
        "recipe_ingredients": "gemini-2.5-flash-lite",
        "recipe_ingredients_fallback": "gemini-2.5-flash",
        "recipe_semantics": "gemini-2.5-flash",
    },
    "OPENROUTER": {
        "image_match": "google/gemini-2.5-flash",
        "many_recipes_per_file": "google/gemini-2.5-flash",
        "one_recipe_per_file": "openai/gpt-oss-120b",
        "blocks_of_files": "google/gemini-2.5-flash",
        "book_keywords": "google/gemini-2.5-flash",
        "keyword_dedup": "google/gemini-2.5-flash",
        "ingredient_dedup": "google/gemini-2.5-flash",
        "assistant": "google/gemini-2.5-flash",
        "recipe_enrichment": "google/gemini-2.5-flash",
        "recipe_ingredients": "google/gemini-2.5-flash-lite",
        "recipe_ingredients_fallback": "anthropic/claude-haiku-4.5",
        "recipe_semantics": "anthropic/claude-haiku-4.5",
    },
}

# Which legacy provider owned each overridden role. The assistant, ingredient and
# semantics roles had their own provider fields; every other role resolved through
# the shared extraction provider.
_OVERRIDE_OWNERS = {
    "assistant": "assistant_provider",
    "recipe_ingredients": "stage1_provider",
    "recipe_ingredients_fallback": "stage2_provider",
    "recipe_semantics": "stage2_provider",
}

# Every task role the assignment table can hold (Gemini's recommendation map covers
# them all, so it doubles as the role registry here).
ALL_ROLES = tuple(RECOMMENDATIONS["GEMINI"])
_ASSISTANT_ROLE = "assistant"
_INGREDIENTS_ROLE = "recipe_ingredients"
_FALLBACK_ROLE = "recipe_ingredients_fallback"
_SEMANTICS_ROLE = "recipe_semantics"

_LEGACY_COLUMNS = (
    "ai_provider",
    "api_key",
    "assistant_provider",
    "assistant_api_key",
    "enrichment_stage1_provider",
    "enrichment_stage1_api_key",
    "enrichment_stage2_provider",
    "enrichment_stage2_api_key",
    "model_overrides",
)


def _legacy_config(connection: sa.Connection) -> dict | None:
    row = connection.execute(
        sa.text(
            "SELECT ai_provider, api_key, assistant_provider, assistant_api_key,"
            " enrichment_stage1_provider, enrichment_stage1_api_key,"
            " enrichment_stage2_provider, enrichment_stage2_api_key,"
            " model_overrides FROM config WHERE id = 1"
        )
    ).first()
    if row is None:
        return None
    return {
        "ai_provider": row[0],
        "api_key": row[1],
        "assistant_provider": row[2],
        "assistant_api_key": row[3],
        "stage1_provider": row[4],
        "stage1_api_key": row[5],
        "stage2_provider": row[6],
        "stage2_api_key": row[7],
        "overrides": json.loads(row[8]) if row[8] else {},
    }


def _migrated_key(legacy: dict, provider: str) -> str | None:
    """The legacy key for `provider`, or None when none was set or several fields
    disagree — a disagreement needs an administrator decision, not a silent pick."""
    keys = {
        key
        for field, key in (
            ("ai_provider", legacy["api_key"]),
            ("assistant_provider", legacy["assistant_api_key"]),
            ("stage1_provider", legacy["stage1_api_key"]),
            ("stage2_provider", legacy["stage2_api_key"]),
        )
        if legacy[field] == provider and key
    }
    return next(iter(keys)) if len(keys) == 1 else None


def _known_provider(value: str | None) -> str | None:
    return value if value in PROVIDERS else None


def upgrade() -> None:
    provider_enum = sa.Enum(*PROVIDERS, "STUB", name="aiprovider")
    role_enum = sa.Enum(
        "image_match",
        "ocr",
        "many_recipes_per_file",
        "one_recipe_per_file",
        "blocks_of_files",
        "book_keywords",
        "keyword_dedup",
        "ingredient_dedup",
        "assistant",
        "recipe_enrichment",
        "recipe_ingredients",
        "recipe_ingredients_fallback",
        "recipe_semantics",
        name="modelrole",
    )
    op.create_table(
        "ai_provider_configs",
        sa.Column("provider", provider_enum, primary_key=True),
        sa.Column("api_key", sa.String(length=200), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("model_ids", sa.JSON(), nullable=False),
    )
    op.create_table(
        "ai_task_assignments",
        sa.Column("role", role_enum, primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("provider", provider_enum, nullable=False),
        sa.Column("model_id", sa.String(length=200), nullable=False),
    )

    connection = op.get_bind()
    legacy = _legacy_config(connection)

    model_ids = {provider: list(SEED_MODELS[provider]) for provider in PROVIDERS}
    assignments: list[tuple[str, int, str, str]] = []

    def _assign(role: str, position: int, provider: str, model: str) -> None:
        assignments.append((role, position, provider, model))
        if model not in model_ids[provider]:
            # An override may name a model outside the recommendations; keep the
            # assignment's model inside the provider's usable list.
            model_ids[provider].append(model)

    if legacy is not None:
        extraction = _known_provider(legacy["ai_provider"])
        assistant = _known_provider(legacy["assistant_provider"])
        stage1 = _known_provider(legacy["stage1_provider"])
        stage2 = _known_provider(legacy["stage2_provider"])
        overrides = {
            role: model
            for role, model in legacy["overrides"].items()
            if isinstance(model, str) and model.strip()
        }

        if assistant is not None:
            _assign(
                _ASSISTANT_ROLE,
                0,
                assistant,
                overrides.get(_ASSISTANT_ROLE)
                or RECOMMENDATIONS[assistant][_ASSISTANT_ROLE],
            )
        primary = stage1 or extraction
        if primary is not None:
            _assign(
                _INGREDIENTS_ROLE,
                0,
                primary,
                overrides.get(_INGREDIENTS_ROLE)
                or RECOMMENDATIONS[primary][_INGREDIENTS_ROLE],
            )
            if stage2 is not None:
                _assign(
                    _INGREDIENTS_ROLE,
                    1,
                    stage2,
                    overrides.get(_FALLBACK_ROLE)
                    or RECOMMENDATIONS[stage2][_FALLBACK_ROLE],
                )
            elif _FALLBACK_ROLE in overrides:
                # No stage-2 provider: the fallback ran on the primary provider with
                # the fallback model, so the chain records exactly that.
                _assign(_INGREDIENTS_ROLE, 1, primary, overrides[_FALLBACK_ROLE])
        elif stage2 is not None:
            _assign(
                _INGREDIENTS_ROLE,
                0,
                stage2,
                overrides.get(_INGREDIENTS_ROLE)
                or RECOMMENDATIONS[stage2][_INGREDIENTS_ROLE],
            )
        if stage2 is not None:
            _assign(
                _SEMANTICS_ROLE,
                0,
                stage2,
                overrides.get(_SEMANTICS_ROLE) or RECOMMENDATIONS[stage2][_SEMANTICS_ROLE],
            )
        elif _SEMANTICS_ROLE in overrides and primary is not None:
            # No stage-2 provider: semantics ran on the primary provider.
            _assign(_SEMANTICS_ROLE, 0, primary, overrides[_SEMANTICS_ROLE])
        owners = {
            "ai_provider": extraction,
            "assistant_provider": assistant,
            "stage1_provider": stage1,
            "stage2_provider": stage2,
        }
        covered = {_ASSISTANT_ROLE, _INGREDIENTS_ROLE, _FALLBACK_ROLE, _SEMANTICS_ROLE}
        for role, model in overrides.items():
            if role in covered or role not in ALL_ROLES:
                continue
            owner = owners.get(_OVERRIDE_OWNERS.get(role, "ai_provider"))
            if owner is not None:
                _assign(role, 0, owner, model)

        first = extraction or assistant or stage1 or stage2
        ordered = [first] if first is not None else []
        ordered.extend(p for p in PROVIDERS if p != first)
        keys = {provider: _migrated_key(legacy, provider) for provider in PROVIDERS}
    else:
        ordered = list(PROVIDERS)
        keys = dict.fromkeys(PROVIDERS)

    for order, provider in enumerate(ordered):
        connection.execute(
            sa.text(
                "INSERT INTO ai_provider_configs (provider, api_key, display_order, model_ids)"
                " VALUES (:provider, :api_key, :display_order, :model_ids)"
            ),
            {
                "provider": provider,
                "api_key": keys[provider],
                "display_order": order,
                "model_ids": json.dumps(model_ids[provider]),
            },
        )
    for role, position, provider, model in assignments:
        connection.execute(
            sa.text(
                "INSERT INTO ai_task_assignments (role, position, provider, model_id)"
                " VALUES (:role, :position, :provider, :model_id)"
            ),
            {"role": role, "position": position, "provider": provider, "model_id": model},
        )

    with op.batch_alter_table("config", schema=None) as batch_op:
        for column in _LEGACY_COLUMNS:
            batch_op.drop_column(column)


def downgrade() -> None:
    provider_enum = sa.Enum(*PROVIDERS, "STUB", name="aiprovider")
    with op.batch_alter_table("config", schema=None) as batch_op:
        batch_op.add_column(sa.Column("ai_provider", provider_enum, nullable=True))
        batch_op.add_column(sa.Column("api_key", sa.String(length=200), nullable=True))
        batch_op.add_column(
            sa.Column("assistant_provider", provider_enum, nullable=True)
        )
        batch_op.add_column(
            sa.Column("assistant_api_key", sa.String(length=200), nullable=True)
        )
        batch_op.add_column(
            sa.Column("enrichment_stage1_provider", provider_enum, nullable=True)
        )
        batch_op.add_column(
            sa.Column("enrichment_stage1_api_key", sa.String(length=200), nullable=True)
        )
        batch_op.add_column(
            sa.Column("enrichment_stage2_provider", provider_enum, nullable=True)
        )
        batch_op.add_column(
            sa.Column("enrichment_stage2_api_key", sa.String(length=200), nullable=True)
        )
        batch_op.add_column(sa.Column("model_overrides", sa.JSON(), nullable=True))
    op.drop_table("ai_task_assignments")
    op.drop_table("ai_provider_configs")
