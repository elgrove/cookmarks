import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, require_admin
from app.api.lists import favourite_list_id
from app.config import settings
from app.covers import cover_path, has_cover
from app.db import SessionDep
from app.epub import epub_path, has_epub
from app.models.book import Book
from app.models.calibre_exclusion import CalibreExclusion
from app.models.recipe import Recipe
from app.models.recipe_list import RecipeListItem
from app.schemas.book import BookDetail, BookFilter, BookSummary, RecipeIndexEntry
from app.schemas.recipe import RecipeRow
from app.services.calibre import delete_books
from app.services.views import seen_count, seen_counts

router = APIRouter(tags=["books"])


@router.get("/books", response_model=list[BookSummary])
def list_books(session: SessionDep, user: CurrentUser) -> list[BookSummary]:
    # One grouped query, not N+1. count(Recipe.id) (not *) so books with no
    # recipes correctly count 0 across the outer join.
    rows = session.execute(
        select(Book, func.count(Recipe.id))
        .outerjoin(Recipe, Recipe.book_id == Book.id)
        .group_by(Book.id)
        .order_by(Book.created_at.desc())
        # selectinload avoids an N+1 on each book's keywords for the card chips.
        .options(selectinload(Book.keywords))
    ).all()
    seen = seen_counts(session, user.id)
    return [
        BookSummary(
            id=book.id,
            title=book.title,
            author=book.author,
            recipe_count=recipe_count,
            seen_count=seen.get(book.id, 0),
            has_cover=has_cover(book),
            pubdate=book.pubdate,
            keywords=sorted(k.name for k in book.keywords),
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
def get_book(book_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> BookDetail:
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
        seen_count=seen_count(session, user.id, book_id),
        has_cover=has_cover(book),
        has_epub=has_epub(book),
        added=book.calibre_added_at,
        keywords=sorted(k.name for k in book.keywords),
        recipes=[
            RecipeRow(id=r.id, name=r.name, keywords=sorted(k.name for k in r.keywords))
            for r in recipes
        ],
    )


@router.delete(
    "/books/{book_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
def delete_book(book_id: uuid.UUID, session: SessionDep, exclude: bool = False) -> Response:
    """Delete a book and everything under it (recipes, runs, list membership, embeddings).
    With `exclude=true` the book's Calibre id is added to the exclusion list so the next
    sync skips it — without that, a book still in the library is re-created on the next
    sync (recipes gone)."""
    book = session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="book not found")
    if exclude:
        # merge, not add: deleting the same Calibre book twice must not clash on the PK.
        session.merge(CalibreExclusion(calibre_id=book.calibre_id, title=book.title))
    delete_books(session, [book])
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


@router.get("/books/{book_id}/recipe-index", response_model=list[RecipeIndexEntry])
def book_recipe_index(
    book_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> list[RecipeIndexEntry]:
    """Every recipe in the book (id · name · favourite state), in book order — the in-book
    EPUB reader matches headings against this to offer a save-to-favourites button."""
    if session.get(Book, book_id) is None:
        raise HTTPException(status_code=404, detail="book not found")
    fav_list_id = favourite_list_id(session, user.id)
    fav_ids: set[uuid.UUID] = set()
    if fav_list_id is not None:
        fav_ids = set(
            session.scalars(
                select(RecipeListItem.recipe_id)
                .join(Recipe, Recipe.id == RecipeListItem.recipe_id)
                .where(RecipeListItem.recipe_list_id == fav_list_id, Recipe.book_id == book_id)
            ).all()
        )
    rows = session.execute(
        select(Recipe.id, Recipe.name).where(Recipe.book_id == book_id).order_by(Recipe.order)
    ).all()
    return [
        RecipeIndexEntry(id=rid, name=name, is_favourite=rid in fav_ids) for rid, name in rows
    ]
