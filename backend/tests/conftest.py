from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
import sqlite_vec
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.db import get_session
from app.main import app
from app.models import Base, Book, Keyword, Recipe


def _seed(session: Session) -> None:
    # Two books: one with recipes, one with none (the "pending extraction" path).
    # Distinct created_at so the default created_at DESC order is deterministic.
    with_recipes = Book(
        calibre_id=1,
        title="With Recipes",
        author="Author One",
        pubdate=date(2020, 1, 1),
        path="Author One/With Recipes (1)",
        created_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    without_recipes = Book(
        calibre_id=2,
        title="No Recipes Yet",
        author="Author Two",
        pubdate=None,
        path="Author Two/No Recipes Yet (2)",
        created_at=datetime(2021, 1, 1, tzinfo=UTC),
    )
    session.add_all([with_recipes, without_recipes])
    session.flush()
    pasta = Keyword(name="Pasta")
    quick = Keyword(name="Quick")
    session.add_all([pasta, quick])
    for i in range(3):
        recipe = Recipe(
            book_id=with_recipes.id,
            order=i,
            name=f"Recipe {i}",
            ingredients=[],
            instructions=[],
        )
        # First recipe carries keywords so the detail endpoint's keyword join is exercised.
        if i == 0:
            recipe.keywords = [pasta, quick]
        session.add(recipe)
    session.commit()


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.sqlite3'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _configure(dbapi_conn: Any, _record: Any) -> None:
        dbapi_conn.enable_load_extension(True)
        sqlite_vec.load(dbapi_conn)
        dbapi_conn.enable_load_extension(False)
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        _seed(session)
        yield session
    engine.dispose()


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    def _use_test_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = _use_test_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
