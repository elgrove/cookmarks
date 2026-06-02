from pathlib import Path

from app.config import settings
from app.models.book import Book


def epub_path(book: Book) -> Path | None:
    """First *.epub in the book's Calibre directory, or None if there isn't one."""
    matches = sorted((settings.calibre_library_path / book.path).glob("*.epub"))
    return matches[0] if matches else None


def has_epub(book: Book) -> bool:
    return epub_path(book) is not None
