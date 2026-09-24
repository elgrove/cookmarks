import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

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


def test_migration_merges_case_variants_and_preserves_links_and_state(tmp_path: Path) -> None:
    database_path = tmp_path / "keyword-case.sqlite3"
    _upgrade(database_path, "e6f7a8b9c0d1")
    connection = sqlite3.connect(database_path)
    rows = [
        ("1" * 32, " Spring   Onion ", None, None),
        ("2" * 32, "spring onion", "key_ingredient", "2026-01-02"),
        ("3" * 32, "SPRING ONION", None, None),
    ]
    connection.executemany(
        """INSERT INTO keywords
           (id, name, category, classified_at, created_at, updated_at)
           VALUES (?, ?, ?, ?, '2026-01-01', '2026-01-01')""",
        rows,
    )
    connection.executemany(
        "INSERT INTO recipe_keywords (recipe_id, keyword_id) VALUES (?, ?)",
        [("a" * 32, "1" * 32), ("a" * 32, "2" * 32), ("b" * 32, "3" * 32)],
    )
    connection.executemany(
        "INSERT INTO book_keywords (book_id, keyword_id) VALUES (?, ?)",
        [("c" * 32, "1" * 32), ("d" * 32, "3" * 32)],
    )
    connection.commit()
    connection.close()

    _upgrade(database_path, "head")
    connection = sqlite3.connect(database_path)
    keywords = connection.execute(
        "SELECT id, name, category, classified_at FROM keywords"
    ).fetchall()
    recipe_links = connection.execute(
        "SELECT recipe_id, keyword_id FROM recipe_keywords ORDER BY recipe_id"
    ).fetchall()
    book_links = connection.execute(
        "SELECT book_id, keyword_id FROM book_keywords ORDER BY book_id"
    ).fetchall()
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """INSERT INTO keywords (id, name, created_at, updated_at)
               VALUES (?, ?, '2026-01-01', '2026-01-01')""",
            ("4" * 32, "Mixed Case"),
        )
    connection.close()

    assert keywords == [("2" * 32, "spring onion", "key_ingredient", "2026-01-02")]
    assert recipe_links == [("a" * 32, "2" * 32), ("b" * 32, "2" * 32)]
    assert book_links == [("c" * 32, "2" * 32), ("d" * 32, "2" * 32)]
