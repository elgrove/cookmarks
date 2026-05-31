"""Seed the v2 database from the v1 (Django) production SQLite DB.

Read-only on the source; clears and repopulates the v2 app tables, so it is safe
to re-run (e.g. to re-seed after a schema change). Recipes, books, keywords,
lists/favourites, extraction runs and the sqlite-vec embeddings are all carried
across. UUIDs are preserved verbatim, so the embeddings (keyed by the hyphenated
UUID, as v1 stored them) stay valid against v2's `str(recipe.id)` lookups.

    cd backend && uv run python -m scripts.import_v1_data [--source PATH] [--no-embeddings]
"""

import argparse
import sqlite3
from pathlib import Path

import sqlite_vec

from app.config import settings
from app.models.enums import AIProvider

V1_DEFAULT = Path.home() / "docker" / "cookmarks" / "data" / "db.sqlite3"
EMBEDDING_DIM = 3072  # v1 Gemini embedding dimensions
EMBEDDING_BATCH = 1000
V1_LIBRARY_ROOT = "/books/"  # absolute prefix on v1 book paths; stripped to store paths relative

# Each entry: (v2 table, v2 columns, SELECT against the v1 schema in the same order).
# Books are copied by copy_books() (it rewrites `path` to be library-relative).
COPIES: list[tuple[str, list[str], str]] = [
    (
        "keywords",
        ["id", "created_at", "updated_at", "name"],
        "SELECT id, created_at, updated_at, name FROM core_keyword",
    ),
    (
        "recipe_lists",
        ["id", "created_at", "updated_at", "name", "is_default"],
        "SELECT id, created_at, updated_at, name, is_default FROM core_recipelist",
    ),
    (
        "extraction_runs",
        ["id", "created_at", "updated_at", "book_id", "provider_name", "model_name",
         "extraction_method", "status", "started_at", "completed_at", "total_chapters",
         "chapters_processed", "recipes_found", "images_in_separate_chapters",
         "images_can_be_matched", "cost_usd", "input_tokens", "output_tokens", "errors"],
        """SELECT id, created_at, updated_at, book_id, provider_name, model_name,
                  extraction_method, status, started_at, completed_at, total_chapters,
                  chapters_processed, recipes_found, images_in_separate_chapters,
                  images_can_be_matched, cost_usd, input_tokens, output_tokens, errors
           FROM core_extractionreport""",
    ),
    (
        "recipes",
        ["id", "created_at", "updated_at", "book_id", "extraction_run_id", "order",
         "name", "description", "ingredients", "instructions", "yields", "image"],
        """SELECT id, created_at, updated_at, book_id, extraction_report_id, "order",
                  name, description, COALESCE(ingredients, '[]'),
                  COALESCE(instructions, '[]'), yields, image
           FROM core_recipe""",
    ),
    (
        "recipe_keywords",
        ["recipe_id", "keyword_id"],
        "SELECT recipe_id, keyword_id FROM core_recipe_keywords",
    ),
]

# Reverse of insertion order, for FK-safe clearing.
DELETE_ORDER = [
    "config", "recipe_list_items", "recipe_keywords", "recipes",
    "extraction_runs", "recipe_lists", "keywords", "books",
]


def open_source(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("PRAGMA query_only=ON")
    return conn


def open_target() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def clear_target(tgt: sqlite3.Connection) -> None:
    for table in DELETE_ORDER:
        tgt.execute(f"DELETE FROM {table}")
    tgt.execute("DROP TABLE IF EXISTS recipe_embeddings")
    tgt.commit()


def copy_table(
    src: sqlite3.Connection, tgt: sqlite3.Connection, table: str, cols: list[str], select: str
) -> int:
    rows = src.execute(select).fetchall()
    placeholders = ", ".join(["?"] * len(cols))
    columns = ", ".join(f'"{c}"' for c in cols)
    verb = "INSERT OR IGNORE" if table == "recipe_keywords" else "INSERT"
    tgt.executemany(f"{verb} INTO {table} ({columns}) VALUES ({placeholders})", rows)
    tgt.commit()
    return len(rows)


def copy_books(src: sqlite3.Connection, tgt: sqlite3.Connection) -> int:
    """Copy books, rewriting `path` to be relative to the Calibre library root so the
    library location stays a runtime setting (settings.calibre_library_path) not baked-in data."""
    rows = src.execute(
        """SELECT id, created_at, updated_at, calibre_id, title, author,
                  isbn, pubdate, description, path, calibre_added_at
           FROM core_book"""
    ).fetchall()
    out = [(*row[:9], row[9].removeprefix(V1_LIBRARY_ROOT), row[10]) for row in rows]
    tgt.executemany(
        """INSERT INTO books
           (id, created_at, updated_at, calibre_id, title, author,
            isbn, pubdate, description, path, calibre_added_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        out,
    )
    tgt.commit()
    return len(out)


def copy_list_items(src: sqlite3.Connection, tgt: sqlite3.Connection) -> int:
    rows = src.execute(
        """SELECT id, created_at, updated_at, recipe_list_id, recipe_id
           FROM core_recipelistitem ORDER BY recipe_list_id, created_at DESC"""
    ).fetchall()
    position: dict[str, int] = {}
    out = []
    for rid, created, updated, list_id, recipe_id in rows:
        pos = position.get(list_id, 0)
        position[list_id] = pos + 1
        out.append((rid, created, updated, list_id, recipe_id, pos))
    tgt.executemany(
        """INSERT INTO recipe_list_items
           (id, created_at, updated_at, recipe_list_id, recipe_id, position)
           VALUES (?, ?, ?, ?, ?, ?)""",
        out,
    )
    tgt.commit()
    return len(out)


def copy_config(src: sqlite3.Connection, tgt: sqlite3.Connection) -> int:
    valid = {p.value for p in AIProvider}
    rows = src.execute("SELECT id, ai_provider, api_key FROM core_config").fetchall()
    out = [
        (cid, provider if provider in valid else None, key or None)
        for cid, provider, key in rows
    ]
    tgt.executemany(
        "INSERT INTO config (id, ai_provider, api_key) VALUES (?, ?, ?)", out
    )
    tgt.commit()
    return len(out)


def copy_embeddings(src: sqlite3.Connection, tgt: sqlite3.Connection) -> int:
    tgt.execute(
        f"""CREATE VIRTUAL TABLE recipe_embeddings USING vec0(
                recipe_id TEXT PRIMARY KEY,
                embedding FLOAT[{EMBEDDING_DIM}] distance_metric=cosine
            )"""
    )
    cursor = src.execute("SELECT recipe_id, embedding FROM recipe_embeddings")
    total = 0
    while batch := cursor.fetchmany(EMBEDDING_BATCH):
        tgt.executemany(
            "INSERT INTO recipe_embeddings (recipe_id, embedding) VALUES (?, ?)", batch
        )
        total += len(batch)
    tgt.commit()
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the v2 DB from v1 production data.")
    parser.add_argument("--source", type=Path, default=V1_DEFAULT, help="v1 SQLite DB path")
    parser.add_argument("--no-embeddings", action="store_true", help="skip the vec embeddings")
    args = parser.parse_args()

    if not args.source.exists():
        raise SystemExit(f"source DB not found: {args.source}")

    src = open_source(args.source)
    tgt = open_target()
    try:
        clear_target(tgt)
        print(f"  {'books':20} {copy_books(src, tgt)}")
        for table, cols, select in COPIES:
            n = copy_table(src, tgt, table, cols, select)
            print(f"  {table:20} {n}")
        print(f"  {'recipe_list_items':20} {copy_list_items(src, tgt)}")
        print(f"  {'config':20} {copy_config(src, tgt)}")
        if not args.no_embeddings:
            print(f"  {'recipe_embeddings':20} {copy_embeddings(src, tgt)}")
    finally:
        src.close()
        tgt.close()
    print("done")


if __name__ == "__main__":
    main()
