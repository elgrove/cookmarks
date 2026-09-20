import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_REVISION = "a189cf7d2e4b"


def _upgrade(database_path: Path, revision: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        cwd=BACKEND_ROOT,
        env={**os.environ, "COOKMARKS_DB_PATH": str(database_path)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_migration_adds_pending_state_without_changing_keyword_data(tmp_path: Path) -> None:
    database_path = tmp_path / "keywords.sqlite3"
    _upgrade(database_path, PREVIOUS_REVISION)
    connection = sqlite3.connect(database_path)
    connection.execute(
        "INSERT INTO keywords (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
        ("0" * 32, "spring onion", "2026-01-01", "2026-01-01"),
    )
    connection.commit()
    connection.close()

    _upgrade(database_path, "head")
    connection = sqlite3.connect(database_path)
    row = connection.execute(
        "SELECT name, category, classified_at FROM keywords WHERE id = ?", ("0" * 32,)
    ).fetchone()
    indexes = {item[1] for item in connection.execute("PRAGMA index_list(keywords)")}
    connection.close()

    assert row == ("spring onion", None, None)
    assert "ix_keywords_classified_at" in indexes
