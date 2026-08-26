import zipfile
from pathlib import Path

from app.config import settings
from app.models.book import Book

_IMAGE_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def epub_path(book: Book) -> Path | None:
    """First *.epub in the book's Calibre directory, or None if there isn't one."""
    matches = sorted((settings.calibre_library_path / book.path).glob("*.epub"))
    return matches[0] if matches else None


def has_epub(book: Book) -> bool:
    return epub_path(book) is not None


def pdf_path(book: Book) -> Path | None:
    """First *.pdf in the book's Calibre directory, or None if there isn't one."""
    matches = sorted((settings.calibre_library_path / book.path).glob("*.pdf"))
    return matches[0] if matches else None


def has_pdf(book: Book) -> bool:
    return pdf_path(book) is not None


def read_epub_image(book: Book, member: str) -> tuple[bytes, str] | None:
    """Read the image stored at `member` inside a book's EPUB, returning its bytes
    and media type, or None when the EPUB or the member is missing.

    Two traversal guards: the EPUB file is confined to the library root (as the cover
    and epub endpoints do), and `member` is only ever looked up against the archive's
    own entries and read into memory — never joined onto a filesystem path — so a
    crafted name cannot escape the archive."""
    epub = epub_path(book)
    if epub is None:
        return None
    epub = epub.resolve()
    library = settings.calibre_library_path.resolve()
    if not epub.is_relative_to(library) or not epub.is_file():
        return None
    try:
        with zipfile.ZipFile(epub, "r") as archive:
            data = archive.read(member)
    except (KeyError, zipfile.BadZipFile, OSError):
        return None
    media_type = _IMAGE_MEDIA_TYPES.get(Path(member).suffix.lower(), "application/octet-stream")
    return data, media_type
