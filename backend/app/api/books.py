import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.covers import cover_path, has_cover
from app.db import SessionDep
from app.epub import epub_path, has_epub
from app.models.book import Book
from app.models.recipe import Recipe
from app.schemas.book import BookDetail, BookFilter, BookSummary
from app.schemas.recipe import RecipeRow

router = APIRouter(tags=["books"])


@router.get("/books", response_model=list[BookSummary])
def list_books(session: SessionDep) -> list[BookSummary]:
    # One grouped query, not N+1. count(Recipe.id) (not *) so books with no
    # recipes correctly count 0 across the outer join.
    rows = session.execute(
        select(Book, func.count(Recipe.id))
        .outerjoin(Recipe, Recipe.book_id == Book.id)
        .group_by(Book.id)
        .order_by(Book.created_at.desc())
    ).all()
    return [
        BookSummary(
            id=book.id,
            title=book.title,
            author=book.author,
            recipe_count=recipe_count,
            has_cover=has_cover(book),
            pubdate=book.pubdate,
        )
        for book, recipe_count in rows
    ]


# Declared before /books/{book_id} so the literal path wins — otherwise the UUID
# matcher would claim "filters" and 422 on it.
@router.get("/books/filters", response_model=list[BookFilter])
def list_book_filters(session: SessionDep) -> list[BookFilter]:
    # The recipes-search controls need only id/title/author. Skipping the per-book
    # recipe COUNT (the bulk of /books' cost) makes this a plain column select; the
    # caller sorts client-side, so order here is immaterial.
    rows = session.execute(select(Book.id, Book.title, Book.author)).all()
    return [BookFilter(id=row.id, title=row.title, author=row.author) for row in rows]


@router.get("/books/{book_id}", response_model=BookDetail)
def get_book(book_id: uuid.UUID, session: SessionDep) -> BookDetail:
    book = session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="book not found")
    total = (
        session.scalar(select(func.count(Recipe.id)).where(Recipe.book_id == book_id)) or 0
    )
    # A random sample of the book's recipes; selectinload avoids an N+1 on keywords.
    recipes = (
        session.scalars(
            select(Recipe)
            .where(Recipe.book_id == book_id)
            .order_by(func.random())
            .limit(10)
            .options(selectinload(Recipe.keywords))
        )
        .all()
    )
    return BookDetail(
        id=book.id,
        title=book.title,
        author=book.author,
        isbn=book.isbn,
        pubdate=book.pubdate,
        description=book.description,
        recipe_count=total,
        has_cover=has_cover(book),
        has_epub=has_epub(book),
        added=book.calibre_added_at,
        recipes=[
            RecipeRow(id=r.id, name=r.name, keywords=sorted(k.name for k in r.keywords))
            for r in recipes
        ],
    )


@router.get("/books/{book_id}/cover")
def book_cover(book_id: uuid.UUID, session: SessionDep) -> FileResponse:
    book = session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="book not found")
    cover = cover_path(book).resolve()
    library = settings.calibre_library_path.resolve()
    # Guard against a crafted path escaping the library root before touching disk.
    if not cover.is_relative_to(library) or not cover.is_file():
        raise HTTPException(status_code=404, detail="cover not found")
    return FileResponse(cover, media_type="image/jpeg")


@router.get("/books/{book_id}/epub")
def book_epub(book_id: uuid.UUID, session: SessionDep) -> FileResponse:
    book = session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="book not found")
    epub = epub_path(book)
    if epub is None:
        raise HTTPException(status_code=404, detail="epub not found")
    epub = epub.resolve()
    library = settings.calibre_library_path.resolve()
    # Same traversal guard as the cover endpoint, before streaming bytes off disk.
    if not epub.is_relative_to(library) or not epub.is_file():
        raise HTTPException(status_code=404, detail="epub not found")
    return FileResponse(epub, media_type="application/epub+zip")
