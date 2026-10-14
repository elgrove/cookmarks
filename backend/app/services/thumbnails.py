"""On-disk thumbnail pipeline for book covers and recipe images.

Fixed display sizes, WebP output, generated once per source and cached on disk.
The endpoints in ``app/api/books.py`` and ``app/api/recipes.py`` serve these
derivatives; the originals are still served unchanged from their own endpoints.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import os
import tempfile
from pathlib import Path

from PIL import Image

from app.config import settings
from app.covers import cover_path
from app.epub import epub_path, read_epub_image
from app.models.book import Book

COVER_THUMBNAIL_WIDTH = 320
RECIPE_THUMBNAIL_MAX_WIDTH = 640
WEBP_QUALITY = 82


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _resize(image: Image.Image, max_width: int) -> Image.Image:
    width, height = image.size
    if width <= max_width:
        return image
    new_height = round(height * max_width / width)
    return image.resize((max_width, new_height), Image.Resampling.LANCZOS)


def _to_webp(image: Image.Image) -> bytes:
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        image = image.convert("RGBA")
    else:
        image = image.convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="WEBP", quality=WEBP_QUALITY, method=6)
    return buffer.getvalue()


def _prune_siblings(directory: Path, prefix: str, keep: Path) -> None:
    """Drop older cached derivatives for the same source/key so the cache does not grow."""
    if not directory.is_dir():
        return
    for candidate in directory.iterdir():
        if candidate == keep:
            continue
        if candidate.name.startswith(prefix) and candidate.suffix == ".webp":
            candidate.unlink(missing_ok=True)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def cover_thumbnail(book: Book) -> bytes:
    """Bytes for a book's cover thumbnail (WebP)."""
    source = cover_path(book)
    if not source.is_file():
        raise FileNotFoundError("cover not found")
    source = source.resolve()
    library = settings.calibre_library_path.resolve()
    if not source.is_relative_to(library):
        raise FileNotFoundError("cover not found")
    directory = settings.thumbnail_cache_path / "covers"
    _ensure_dir(directory)
    mtime = source.stat().st_mtime_ns
    cache = directory / f"{book.id}-w{COVER_THUMBNAIL_WIDTH}-{mtime}.webp"
    if cache.is_file():
        return cache.read_bytes()
    try:
        with Image.open(source) as opened:
            image = opened.copy()
    except Exception:
        raise FileNotFoundError("cover not readable") from None
    data = _to_webp(_resize(image, COVER_THUMBNAIL_WIDTH))
    _atomic_write_bytes(cache, data)
    _prune_siblings(directory, f"{book.id}-w{COVER_THUMBNAIL_WIDTH}-", cache)
    return data


def recipe_image_thumbnail(book: Book, member: str, recipe_id) -> bytes | None:
    """Bytes for a recipe's image thumbnail (WebP), or None when the source is missing."""
    epub = epub_path(book)
    if epub is None:
        return None
    epub = epub.resolve()
    library = settings.calibre_library_path.resolve()
    if not epub.is_relative_to(library) or not epub.is_file():
        return None
    result = read_epub_image(book, member)
    if result is None:
        return None
    data_bytes, _media_type = result
    directory = settings.thumbnail_cache_path / "recipes"
    _ensure_dir(directory)
    mtime = epub.stat().st_mtime_ns
    member_hash = hashlib.sha1(member.encode("utf-8")).hexdigest()[:10]
    cache = directory / f"{recipe_id}-w{RECIPE_THUMBNAIL_MAX_WIDTH}-{mtime}-{member_hash}.webp"
    if cache.is_file():
        return cache.read_bytes()
    try:
        with Image.open(io.BytesIO(data_bytes)) as opened:
            image = opened.copy()
    except Exception:
        return None
    data = _to_webp(_resize(image, RECIPE_THUMBNAIL_MAX_WIDTH))
    _atomic_write_bytes(cache, data)
    _prune_siblings(directory, f"{recipe_id}-w{RECIPE_THUMBNAIL_MAX_WIDTH}-", cache)
    return data
