import fcntl
import json
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pymupdf

from app.config import settings
from app.epub import pdf_path
from app.models.book import Book
from app.services.ai import AIProvider, AIResponseError, ModelRole, Usage

CACHE_VERSION = 1


def page_count(path: Path) -> int:
    with pymupdf.open(path) as document:
        return len(document)


def render_page(document: pymupdf.Document, index: int, dpi: int) -> bytes:
    page = document[index]
    pixmap = page.get_pixmap(dpi=dpi, alpha=False)
    return pixmap.tobytes("jpeg", jpg_quality=90)


def ocr_cache_path(book: Book) -> Path:
    library = settings.calibre_library_path.resolve()
    path = (library / book.path / "cookmarks-ocr.json").resolve()
    if not path.is_relative_to(library):
        raise ValueError(f"Book path escapes the Calibre library: {book.path}")
    return path


def _source_identity(path: Path) -> dict[str, int]:
    stat = path.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _empty_cache(dpi: int, model: str, source: dict[str, int]) -> dict[str, Any]:
    return {
        "version": CACHE_VERSION,
        "dpi": dpi,
        "model": model,
        "source": source,
        "pages": {},
    }


def _load_cache(path: Path, dpi: int, model: str, source: dict[str, int]) -> dict[str, Any]:
    try:
        cache = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return _empty_cache(dpi, model, source)
    pages = cache.get("pages")
    if (
        cache.get("version") != CACHE_VERSION
        or cache.get("dpi") != dpi
        or cache.get("model") != model
        or cache.get("source") != source
        or not isinstance(pages, dict)
        or any(not isinstance(key, str) or not key.isdigit() for key in pages)
        or any(not isinstance(value, str) for value in pages.values())
    ):
        return _empty_cache(dpi, model, source)
    return cache


def _write_cache(path: Path, cache: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(cache, ensure_ascii=False, indent=2))
    temporary.replace(path)


@contextmanager
def _cache_lock(path: Path) -> Iterator[None]:
    lock_path = path.with_suffix(".json.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _page_bounds(total: int, pages: tuple[int, int] | None) -> tuple[int, int]:
    start, end = pages or (1, total)
    if start < 1 or end < start or end > total:
        raise ValueError(f"Invalid PDF page range {start}-{end} for {total} pages")
    return start, end


def ocr_book(
    book: Book,
    provider: AIProvider,
    *,
    pages: tuple[int, int] | None = None,
    force: bool = False,
    model: str | None = None,
    on_page: Callable[[int, Usage], None] | None = None,
) -> list[str]:
    source = pdf_path(book)
    if source is None:
        raise ValueError(f"Book {book.id} has no PDF")
    if not provider.supports_vision:
        raise NotImplementedError(f"{provider.name} cannot read images")

    resolved_model = model or provider.model_for(ModelRole.OCR)
    total = page_count(source)
    start, end = _page_bounds(total, pages)
    cache_path = ocr_cache_path(book)
    source_identity = _source_identity(source)

    def read(index: int) -> tuple[int, str, Usage]:
        with pymupdf.open(source) as document:
            image = render_page(document, index, settings.ocr_dpi)
        text, usage = provider.read_page(image, "image/jpeg", model=resolved_model)
        return index, text, usage

    with _cache_lock(cache_path):
        cache = (
            _empty_cache(settings.ocr_dpi, resolved_model, source_identity)
            if force
            else _load_cache(cache_path, settings.ocr_dpi, resolved_model, source_identity)
        )
        cached_pages: dict[str, str] = cache["pages"]
        requested = list(range(start - 1, end))
        missing = [index for index in requested if str(index) not in cached_pages]

        with ThreadPoolExecutor(max_workers=settings.ocr_page_concurrency) as executor:
            futures = {executor.submit(read, index): index for index in missing}
            errors: list[Exception] = []
            for future in as_completed(futures):
                page_index = futures[future]
                try:
                    index, text, usage = future.result()
                except AIResponseError as exc:
                    if on_page is not None:
                        on_page(page_index + 1, exc.usage)
                    errors.append(exc)
                    continue
                except Exception as exc:
                    errors.append(exc)
                    continue
                cached_pages[str(index)] = text
                _write_cache(cache_path, cache)
                if on_page is not None:
                    on_page(index + 1, usage)
            if errors:
                raise errors[0]

        return [cached_pages[str(index)] for index in requested]
