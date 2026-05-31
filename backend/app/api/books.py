import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from app.config import settings
from app.covers import cover_path, has_cover
from app.db import SessionDep
from app.models.book import Book
from app.models.recipe import Recipe
from app.schemas.book import BookSummary

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
