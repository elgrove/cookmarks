"""The FTS5 search index (MY-214): prefix matching, and the triggers that keep it in
sync through the write paths the ORM doesn't route through application code."""

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, event, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.db import configure_sqlite_connection
from app.models import Base, Book, Keyword, Recipe
from app.models.ingredient import CanonicalIngredient, RecipeIngredient
from app.services.search_index import (
    drop_statements,
    ensure_search_index,
    match_query,
    reindex_all,
)


def _search(client: TestClient, q: str) -> dict:
    return client.get("/api/recipes", params={"q": q}).json()


def test_prefix_match_finds_longer_token(client: TestClient) -> None:
    # Prefix, not substring: "anchov" matches the ingredient "100g anchovy" by token
    # prefix, but a mid-word substring does not.
    assert _search(client, "anchov")["total"] == 1
    assert _search(client, "chovy")["total"] == 0


def test_book_retitle_reindexes_its_recipes(client: TestClient, session: Session) -> None:
    book = session.scalars(select(Book).where(Book.title == "With Recipes")).one()
    book.title = "Renamed Cookbook"
    session.commit()

    assert _search(client, "renamed")["total"] == 3
    assert _search(client, "cookbook")["total"] == 3


def test_keyword_rename_reindexes_linked_recipes(client: TestClient, session: Session) -> None:
    keyword = session.scalars(select(Keyword).where(Keyword.name == "pasta")).one()
    keyword.name = "noodles"
    session.commit()

    body = _search(client, "noodles")
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Recipe 0"


def test_canonical_ingredient_assignment_reindexes(client: TestClient, session: Session) -> None:
    # Canonical ingredients are written by the enrichment pass, not extraction — the
    # document must pick them up without a re-extraction.
    recipe = session.scalars(select(Recipe).where(Recipe.name == "Recipe 1")).one()
    salt = CanonicalIngredient(name="Flaky Salt")
    session.add(salt)
    session.flush()
    recipe.ingredients = [RecipeIngredient(position=0, text="a pinch", canonical_ingredient_id=salt.id)]
    session.commit()

    assert _search(client, "flaky")["total"] == 1


def test_deleting_a_recipe_drops_its_index_row(client: TestClient, session: Session) -> None:
    recipe = session.scalars(select(Recipe).where(Recipe.name == "Recipe 2")).one()
    recipe_id = str(recipe.id).replace("-", "")
    session.execute(delete(Recipe).where(Recipe.id == recipe.id))
    session.commit()

    # No orphan FTS row for the deleted recipe.
    orphan = session.scalar(
        text("SELECT count(*) FROM recipe_search WHERE recipe_id = :rid"), {"rid": recipe_id}
    )
    assert orphan == 0
    # And every remaining FTS row still points at a live recipe.
    indexed = session.scalar(text("SELECT count(*) FROM recipe_search"))
    recipes = session.scalar(select(func.count()).select_from(Recipe))
    assert indexed == recipes


def test_match_query_quotes_terms_and_escapes_quotes() -> None:
    assert match_query(["tomato", "curry"]) == '"tomato"* AND "curry"*'
    assert match_query(['chef"s']) == '"chef""s"*'
    assert match_query([]) == ""


def test_reindex_all_rebuilds_from_source(client: TestClient, session: Session) -> None:
    session.execute(text("DELETE FROM recipe_search"))
    session.commit()
    assert _search(client, "recipe")["total"] == 0

    assert reindex_all(session) == 3
    assert _search(client, "recipe")["total"] == 3


def test_drop_statements_remove_the_index_and_its_shadow_tables(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'index.sqlite3'}", connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def _configure(dbapi_conn: Any, _record: Any) -> None:
        configure_sqlite_connection(dbapi_conn, _record)

    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        ensure_search_index(session)
        assert session.scalar(
            text("SELECT count(*) FROM sqlite_master WHERE name = 'recipe_search'")
        )
        for statement in drop_statements():
            session.execute(text(statement))
        session.commit()
        remaining = session.scalar(
            text("SELECT count(*) FROM sqlite_master WHERE name LIKE 'recipe_search%'")
        )
        assert remaining == 0
    engine.dispose()
