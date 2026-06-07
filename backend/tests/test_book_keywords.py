"""Book-level keywords: the read surfaces (library + detail) and the AI generation
service that assigns them from the shared keyword vocabulary."""

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.book import Book
from app.models.enums import AIProvider
from app.models.recipe import Keyword
from app.services.ai import get_config
from app.services.book_keywords import generate_book_keywords


def _with_recipes(session: Session) -> Book:
    return session.scalars(select(Book).where(Book.title == "With Recipes")).one()


def test_books_endpoint_exposes_book_keywords(client: TestClient) -> None:
    books = client.get("/api/books").json()
    extracted = next(b for b in books if b["title"] == "With Recipes")
    pending = next(b for b in books if b["title"] == "No Recipes Yet")

    # Sorted, and the shared "Pasta" tag appears here as well as on a recipe.
    assert extracted["keywords"] == ["Italian", "Pasta"]
    assert pending["keywords"] == []


def test_book_detail_exposes_book_keywords(client: TestClient) -> None:
    book_id = next(
        b["id"] for b in client.get("/api/books").json() if b["title"] == "With Recipes"
    )
    detail = client.get(f"/api/books/{book_id}").json()
    assert detail["keywords"] == ["Italian", "Pasta"]


def test_generate_assigns_keywords_from_shared_vocabulary(session: Session) -> None:
    config = get_config(session)
    config.ai_provider = AIProvider.STUB
    session.commit()

    book = _with_recipes(session)
    # A tag the stub will emit already exists (shared with the wider vocabulary);
    # generation must reuse the row, not create a duplicate.
    session.add(Keyword(name="Cookbook"))
    session.commit()

    names = generate_book_keywords(session, book)
    session.commit()

    assert names  # the stub yields a deterministic, non-empty set
    assert "Cookbook" in names
    # The book's keywords are replaced wholesale by the freshly generated set.
    assert {k.name for k in book.keywords} == set(names)
    # Shared vocabulary: exactly one "Cookbook" row, reused rather than duplicated.
    assert session.scalar(select(func.count()).select_from(Keyword).where(Keyword.name == "Cookbook")) == 1


def test_generate_is_a_noop_without_a_provider(session: Session) -> None:
    book = _with_recipes(session)
    before = sorted(k.name for k in book.keywords)

    assert generate_book_keywords(session, book) == []
    # An unconfigured provider leaves the existing tags untouched.
    assert sorted(k.name for k in book.keywords) == before
