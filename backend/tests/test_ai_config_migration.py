"""The AI-configuration data migration (a189cf7d2e4b).

Builds a database at the previous head, writes a legacy Config row, upgrades, and
asserts the seeded provider rows, migrated keys and explicit assignments. Runs
Alembic in a subprocess against a scratch database, following test_alembic_env.py.
"""

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PREV_REVISION = "5b3c8e1f2a4d"


def _run_alembic(database_path: Path, revision: str) -> None:
    environment = {**os.environ, "COOKMARKS_DB_PATH": str(database_path)}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _upgrade_from_legacy(tmp_path: Path, name: str, legacy: dict) -> sqlite3.Connection:
    database_path = tmp_path / name
    _run_alembic(database_path, PREV_REVISION)

    connection = sqlite3.connect(database_path)
    columns = ", ".join(legacy.keys())
    placeholders = ", ".join(f":{key}" for key in legacy)
    connection.execute(f"INSERT INTO config ({columns}) VALUES ({placeholders})", legacy)
    connection.commit()
    connection.close()

    _run_alembic(database_path, "head")
    return sqlite3.connect(database_path)


def _providers(connection: sqlite3.Connection) -> dict:
    return {
        row[0]: {"api_key": row[1], "display_order": row[2], "model_ids": json.loads(row[3])}
        for row in connection.execute(
            "SELECT provider, api_key, display_order, model_ids FROM ai_provider_configs"
        )
    }


def _assignments(connection: sqlite3.Connection) -> list:
    return connection.execute(
        "SELECT role, position, provider, model_id FROM ai_task_assignments"
        " ORDER BY role, position"
    ).fetchall()


def test_migration_preserves_shared_keys_and_reproduces_choices(tmp_path: Path) -> None:
    """Production-shaped legacy config: Gemini everywhere except Anthropic stage 2,
    with a couple of model overrides. Keys survive; assignments reproduce each choice."""
    connection = _upgrade_from_legacy(
        tmp_path,
        "migrated.sqlite3",
        {
            "id": 1,
            "ai_provider": "GEMINI",
            "api_key": "gemini-key",
            "assistant_provider": "GEMINI",
            "assistant_api_key": "gemini-key",
            "enrichment_stage1_provider": "GEMINI",
            "enrichment_stage1_api_key": "gemini-key",
            "enrichment_stage2_provider": "ANTHROPIC",
            "enrichment_stage2_api_key": "anthropic-key",
            "extraction_rate_limit_per_minute": 120,
            "model_overrides": json.dumps(
                {"assistant": "custom-assistant", "book_keywords": "kw-model"}
            ),
        },
    )

    providers = _providers(connection)
    assert providers["GEMINI"]["api_key"] == "gemini-key"
    assert providers["ANTHROPIC"]["api_key"] == "anthropic-key"
    assert providers["OPENROUTER"]["api_key"] is None
    # The legacy extraction provider goes first so unassigned tasks keep resolving to it.
    assert providers["GEMINI"]["display_order"] == 0
    assert sorted(row["display_order"] for row in providers.values()) == [0, 1, 2]
    # Seeds hold every recommendation; override models are appended, not dropped.
    assert "gemini-2.5-flash" in providers["GEMINI"]["model_ids"]
    assert "gemini-2.5-flash-lite" in providers["GEMINI"]["model_ids"]
    assert "custom-assistant" in providers["GEMINI"]["model_ids"]
    assert "kw-model" in providers["GEMINI"]["model_ids"]
    assert "claude-sonnet-5" in providers["ANTHROPIC"]["model_ids"]

    by_role: dict[str, list[tuple]] = {}
    for role, position, provider, model in _assignments(connection):
        by_role.setdefault(role, []).append((position, provider, model))
    assert by_role["assistant"] == [(0, "GEMINI", "custom-assistant")]
    assert by_role["recipe_ingredients"] == [
        (0, "GEMINI", "gemini-2.5-flash-lite"),
        (1, "ANTHROPIC", "claude-haiku-4-5-20251001"),
    ]
    assert by_role["recipe_semantics"] == [(0, "ANTHROPIC", "claude-haiku-4-5-20251001")]
    assert by_role["book_keywords"] == [(0, "GEMINI", "kw-model")]

    # Legacy columns are gone; the non-AI setting survives.
    columns = {row[1] for row in connection.execute("PRAGMA table_info(config)")}
    assert columns == {"id", "extraction_rate_limit_per_minute"}
    assert connection.execute("SELECT extraction_rate_limit_per_minute FROM config").fetchone() == (
        120,
    )
    connection.close()


def test_migration_leaves_conflicting_keys_unset(tmp_path: Path) -> None:
    """Two different non-empty keys for one provider: migrate neither, so the
    administrator must enter the right one rather than inherit a silent pick."""
    connection = _upgrade_from_legacy(
        tmp_path,
        "conflict.sqlite3",
        {
            "id": 1,
            "ai_provider": "GEMINI",
            "api_key": "first-key",
            "assistant_provider": "GEMINI",
            "assistant_api_key": "second-key",
            "enrichment_stage1_provider": None,
            "enrichment_stage1_api_key": None,
            "enrichment_stage2_provider": None,
            "enrichment_stage2_api_key": None,
            "extraction_rate_limit_per_minute": 256,
            "model_overrides": None,
        },
    )

    providers = _providers(connection)
    assert providers["GEMINI"]["api_key"] is None
    # Choices are still reproduced (pointing at the keyless provider, which the
    # resolver treats as ineligible until a key is entered).
    roles = {(role, position) for role, position, _, _ in _assignments(connection)}
    assert ("assistant", 0) in roles
    assert ("recipe_ingredients", 0) in roles
    connection.close()


def test_migration_without_a_legacy_row_seeds_empty_providers(tmp_path: Path) -> None:
    """A database that never wrote its Config row (lazy singleton) still gets one
    provider row per catalogued provider, keyless and in catalogue order."""
    database_path = tmp_path / "fresh.sqlite3"
    _run_alembic(database_path, "head")

    connection = sqlite3.connect(database_path)
    providers = _providers(connection)
    assert [providers[name]["display_order"] for name in ("ANTHROPIC", "GEMINI", "OPENROUTER")] == [
        0,
        1,
        2,
    ]
    assert all(row["api_key"] is None for row in providers.values())
    assert all(row["model_ids"] for row in providers.values())
    assert _assignments(connection) == []
    connection.close()
