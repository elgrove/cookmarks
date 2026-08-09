import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import CurrentUser, require_admin
from app.api.lists import favourite_list_id
from app.api.reading_queue import is_queued
from app.config import settings
from app.covers import cover_path, has_cover
from app.db import SessionDep
from app.epub import epub_path, has_epub
from app.models.book import Book
from app.models.book_reading import BookReading
from app.models.calibre_exclusion import CalibreExclusion
from app.models.recipe import Recipe
from app.models.recipe_list import RecipeListItem
from app.schemas.book import (
    BookDetail,
    BookFilter,
    BookReadState,
    BookSummary,
    ReadingState,
    ReadingUpdate,
    RecipeIndexEntry,
)
from app.schemas.recipe import RecipeNeighbour, RecipeRow
from app.services.calibre import delete_books
from app.services.reading import (
    finish_reading,
    forget_reading,
    fraction,
    get_reading,
    progress_of,
    reading_positions,
    recipe_count,
    resume_recipe,
    touch_reading,
)
from app.services.views import clear_book_views, mark_book_seen

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
    positions = reading_positions(session, user.id)
    return [
        BookSummary(
            id=book.id,
            title=book.title,
            author=book.author,
            recipe_count=recipe_count,
            progress=(
                fraction(*positions[book.id], recipe_count) if book.id in positions else None
            ),
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
    reading = get_reading(session, user.id, book_id)
    resume = resume_recipe(session, reading, book_id)
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
        keywords=sorted(k.name for k in book.keywords),
        recipes=[
            RecipeRow(
                id=r.id,
                name=r.name,
                keywords=sorted(k.name for k in r.keywords),
            )
            for r in recipes
        ],
        queued=is_queued(session, user.id, book_id),
        reading=_reading_state(session, reading, total),
        resume_recipe=RecipeNeighbour(id=resume.id, name=resume.name) if resume else None,
    )


def _reading_state(
    session: Session, reading: BookReading | None, total: int
) -> ReadingState | None:
    if reading is None:
        return None
    anchor = (
        session.get(Recipe, reading.anchor_recipe_id) if reading.anchor_recipe_id else None
    )
    return ReadingState(
        mode=reading.mode,
        fraction=progress_of(session, reading, total),
        anchor=RecipeNeighbour(id=anchor.id, name=anchor.name) if anchor else None,
        location=reading.location,
        finished=reading.finished,
    )


@router.put("/books/{book_id}/reading", response_model=ReadingState)
def save_reading_position(
    book_id: uuid.UUID, body: ReadingUpdate, session: SessionDep, user: CurrentUser
) -> ReadingState:
    """Record where a reader has got to — the act that puts a book in progress, and every
    move through it after. Both modes report here, so they share one position."""
    if session.get(Book, book_id) is None:
        raise HTTPException(status_code=404, detail="book not found")
    if body.recipe_id is not None:
        recipe = session.get(Recipe, body.recipe_id)
        if recipe is None or recipe.book_id != book_id:
            raise HTTPException(status_code=404, detail="recipe not in this book")
    reading = touch_reading(
        session,
        user.id,
        book_id,
        body.mode,
        recipe_id=body.recipe_id,
        location=body.location,
    )
    state = _reading_state(session, reading, recipe_count(session, book_id))
    assert state is not None
    return state


def _read_state(session: Session, user_id: uuid.UUID, book_id: uuid.UUID) -> BookReadState:
    total = recipe_count(session, book_id)
    return BookReadState(
        recipe_count=total,
        reading=_reading_state(session, get_reading(session, user_id, book_id), total),
    )


@router.post("/books/{book_id}/seen", response_model=BookReadState)
def mark_book_read(book_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> BookReadState:
    """Mark every recipe in the book as read — for a book worked through on paper,
    where opening all of it one page at a time would be the only alternative."""
    if session.get(Book, book_id) is None:
        raise HTTPException(status_code=404, detail="book not found")
    mark_book_seen(session, user.id, book_id)
    # A book declared read is finished reading too, so it leaves the continue strip.
    finish_reading(session, user.id, book_id)
    return _read_state(session, user.id, book_id)


@router.delete("/books/{book_id}/seen", response_model=BookReadState)
def reset_book_progress(
    book_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> BookReadState:
    """Forget the caller's reading of this book, returning it to 0%."""
    if session.get(Book, book_id) is None:
        raise HTTPException(status_code=404, detail="book not found")
    clear_book_views(session, user.id, book_id)
    forget_reading(session, user.id, book_id)
    return _read_state(session, user.id, book_id)


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
