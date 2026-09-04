import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import sqlite_vec

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_alembic_check_ignores_application_owned_vec0_table(tmp_path: Path) -> None:
    database_path = tmp_path / "alembic.sqlite3"
    environment = {**os.environ, "COOKMARKS_DB_PATH": str(database_path)}

    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr

    connection = sqlite3.connect(database_path)
    connection.enable_load_extension(True)
    sqlite_vec.load(connection)
    connection.execute(
        """
        CREATE VIRTUAL TABLE recipe_embeddings USING vec0(
            recipe_id TEXT PRIMARY KEY,
            embedding float[3072]
        )
        """
    )
    connection.commit()
    connection.close()

    check = subprocess.run(
        [sys.executable, "-m", "alembic", "check"],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )
    output = check.stdout + check.stderr
    assert "no such module: vec0" not in output
    assert "recipe_embeddings" not in output
    if check.returncode:
        expected_drift = (
            "FAILED: New upgrade operations detected: "
            "[[('modify_type', None, 'config', 'assistant_provider', "
            "{'existing_nullable': True, 'existing_server_default': False, "
            "'existing_comment': None}, VARCHAR(length=20), "
            "Enum('ANTHROPIC', 'GEMINI', 'OPENROUTER', 'STUB', name='aiprovider'))], "
            "[('modify_type', None, 'task_runs', 'task_type', {'existing_nullable': False, "
            "'existing_server_default': False, 'existing_comment': None}, VARCHAR(length=13), "
            "Enum('extraction', 'book_keywords', 'keyword_dedup', 'calibre_sync', 'book_ingest', "
            "'recipe_enrichment_pilot', name='tasktype'))]]"
        )
        assert [line for line in output.splitlines() if line.startswith("FAILED:")] == [
            expected_drift
        ]
