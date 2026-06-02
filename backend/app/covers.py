from pathlib import Path

from app.config import settings
from app.models.book import Book


def cover_path(book: Book) -> Path:
    """Absolute path to a book's cover under the configured library root."""
    return settings.calibre_library_path / book.path / "cover.jpg"


def has_cover(book: Book) -> bool:
    return cover_path(book).is_file()


def epub_path(book: Book) -> Path:
    """Absolute path to a book's EPUB under the configured library root.

    Calibre stores one EPUB per book directory; the first match is returned.
    Raises FileNotFoundError if the directory holds no EPUB.
    """
    book_dir = settings.calibre_library_path / book.path
    epubs = sorted(book_dir.glob("*.epub"))
    if not epubs:
        raise FileNotFoundError(f"No EPUB found in {book_dir}")
    return epubs[0]
