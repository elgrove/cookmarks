from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
import sqlite_vec
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import current_user
from app.api.recipes import _clear_keyword_cache, _clear_search_order_cache
from app.config import settings
from app.db import get_session
from app.main import app
from app.models import Base, Book, Keyword, Recipe, RecipeIngredient, User
from app.services.auth import hash_password
from app.services.embeddings import _clear_query_embed_cache
from app.tasks.recipe_enrichment import recipe_enrichment_pilot_task

# Where the two seeded books live inside a Calibre library root.
SEEDED_BOOK_PATHS = ("Author One/With Recipes (1)", "Author Two/No Recipes Yet (2)")


@pytest.fixture
def seeded_epubs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A temp Calibre root giving both seeded books an EPUB — what the endpoints that
    gate on a readable EPUB (extraction) need before they will do anything."""
    root = tmp_path / "library"
    for book_path in SEEDED_BOOK_PATHS:
        directory = root / book_path
        directory.mkdir(parents=True)
        (directory / "book.epub").write_bytes(b"PK\x03\x04 not a real epub, just bytes")
    monkeypatch.setattr(settings, "calibre_library_path", root)
    return root


@pytest.fixture(autouse=True)
def dispatched(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    """Stub the Celery dispatch so tests never reach a real broker. Records the
    (book_id, run_id) of each enqueued task; request it by name to assert a trigger
    dispatched exactly once. The end-to-end extraction tests call the task function
    directly (not `.delay`), so they're unaffected."""
    from app.tasks.extraction import extract_recipes_from_book_task

    calls: list[tuple[Any, ...]] = []

    def _record(*args: Any, **_kwargs: Any) -> None:
        calls.append(args)

    monkeypatch.setattr(extract_recipes_from_book_task, "delay", _record)
    return calls


@pytest.fixture(autouse=True)
def resume_dispatched(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    """Stub the resume dispatch so tests never reach a real broker. Records the
    (run_id, human_response) of each enqueued resume; request it by name to assert a
    resume dispatched exactly once."""
    from app.tasks.extraction import resume_extraction_task

    calls: list[tuple[Any, ...]] = []

    def _record(*args: Any, **_kwargs: Any) -> None:
        calls.append(args)

    monkeypatch.setattr(resume_extraction_task, "delay", _record)
    return calls


@pytest.fixture(autouse=True)
def tasks_dispatched(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    """Stub the book-keyword backfill dispatch so tests never reach a real broker.
    Records the (run_id, regenerate) of each enqueued task; request it by name to assert
    a task dispatched exactly once."""
    from app.tasks.book_keywords import backfill_book_keywords_task

    calls: list[tuple[Any, ...]] = []

    def _record(*args: Any, **_kwargs: Any) -> None:
        calls.append(args)

    monkeypatch.setattr(backfill_book_keywords_task, "delay", _record)
    return calls


@pytest.fixture(autouse=True)
def dedup_dispatched(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    """Stub the keyword-dedup dispatch so tests never reach a real broker. Records the
    (run_id,) of each enqueued task; request it by name to assert a trigger dispatched
    exactly once."""
    from app.tasks.keyword_dedup import dedup_keywords_task

    calls: list[tuple[Any, ...]] = []

    def _record(*args: Any, **_kwargs: Any) -> None:
        calls.append(args)

    monkeypatch.setattr(dedup_keywords_task, "delay", _record)
    return calls


@pytest.fixture(autouse=True)
def calibre_dispatched(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    """Stub the Calibre-sync dispatch so tests never reach a real broker. Records the
    (run_id,) of each enqueued task; request it by name to assert a trigger dispatched
    exactly once."""
    from app.tasks.calibre_sync import calibre_sync_task

    calls: list[tuple[Any, ...]] = []

    def _record(*args: Any, **_kwargs: Any) -> None:
        calls.append(args)

    monkeypatch.setattr(calibre_sync_task, "delay", _record)
    return calls


@pytest.fixture(autouse=True)
def ingest_dispatched(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    """Stub the book-ingest dispatch so tests never reach a real broker. Records the
    (run_id,) of each enqueued task; request it by name to assert a confirm dispatched
    exactly once."""
    from app.tasks.ingest import ingest_book_task

    calls: list[tuple[Any, ...]] = []

    def _record(*args: Any, **_kwargs: Any) -> None:
        calls.append(args)

    monkeypatch.setattr(ingest_book_task, "delay", _record)
    return calls


@pytest.fixture(autouse=True)
def enrichment_pilot_dispatched(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    """Keep the admin pilot trigger off Redis while API tests record its dispatch."""
    calls: list[tuple[Any, ...]] = []

    def _record(*args: Any, **_kwargs: Any) -> None:
        calls.append(args)

    monkeypatch.setattr(recipe_enrichment_pilot_task, "delay", _record)
    return calls


@pytest.fixture(autouse=True)
def _reset_caches() -> Iterator[None]:
    # These caches are module-global; clear them so each test's fresh DB (with fresh
    # recipe ids / its own keyword set) never reads a previous test's cached values.
    _clear_search_order_cache()
    _clear_keyword_cache()
    _clear_query_embed_cache()
    yield
    _clear_search_order_cache()
    _clear_keyword_cache()
    _clear_query_embed_cache()


# scrypt is deliberately slow; derive the seeded account's hash once for the whole
# run rather than per test.
TESTER_PASSWORD = "test-secret"
TESTER_HASH = hash_password(TESTER_PASSWORD)


def _seed(session: Session) -> None:
    # The account every `client` request runs as (see the dependency override below),
    # so the existing suite exercises the real routes without logging in.
    session.add(User(username="tester", password_hash=TESTER_HASH, is_admin=True))
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
    # Recipe 0 carries keywords and an ingredient so the search/filter paths
    # (keyword chip, ingredient substring) and the book-detail keyword join all
    # have something to match.
    pasta = Keyword(name="Pasta")
    quick = Keyword(name="Quick")
    italian = Keyword(name="Italian")
    session.add_all([pasta, quick, italian])
    # The extracted book carries its own book-level keywords, one shared with a
    # recipe ("Pasta") to exercise the single shared vocabulary.
    with_recipes.keywords = [italian, pasta]
    for i in range(3):
        recipe = Recipe(
            book_id=with_recipes.id,
            order=i,
            name=f"Recipe {i}",
            instructions=[],
        )
        # Recipe 0 carries full content + keywords so the search/filter paths
        # (ingredient substring, keyword chip) and the detail reading view are
        # all exercised.
        if i == 0:
            recipe.keywords = [pasta, quick]
            recipe.description = "A quick weeknight pasta."
            recipe.yields = "Serves 2"
            recipe.ingredients = [
                RecipeIngredient(position=0, text="200g pasta"),
                RecipeIngredient(position=1, text="100g anchovy"),
                RecipeIngredient(position=2, text="2 tbsp olive oil"),
            ]
            recipe.instructions = ["Boil the pasta.", "Toss with the oil and serve."]
            recipe.image = "OPS/images/recipe-0.jpg"
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

    # Requests run as the seeded admin. The auth tests clear this override to exercise
    # the real cookie path; everything else stays oblivious to accounts.
    def _seeded_user() -> User:
        user = session.scalar(select(User).where(User.username == "tester"))
        assert user is not None
        return user

    app.dependency_overrides[get_session] = _use_test_session
    app.dependency_overrides[current_user] = _seeded_user
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def act_as(session: Session, client: TestClient) -> Callable[[str], User]:
    """Run subsequent requests as another account, by username — for the per-user tests."""

    def _act_as(username: str) -> User:
        user = session.scalar(select(User).where(User.username == username))
        assert user is not None, f"no such user: {username}"
        app.dependency_overrides[current_user] = lambda: user
        return user

    return _act_as
