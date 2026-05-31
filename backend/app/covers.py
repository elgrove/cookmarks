from pathlib import Path

from app.config import settings
from app.models.book import Book


def cover_path(book: Book) -> Path:
    """Absolute path to a book's cover under the configured library root."""
    return settings.calibre_library_path / book.path / "cover.jpg"


def has_cover(book: Book) -> bool:
    return cover_path(book).is_file()
