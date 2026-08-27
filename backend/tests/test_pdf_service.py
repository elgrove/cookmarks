import json
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

import pymupdf
import pytest

from app.config import settings
from app.models.book import Book
from app.services.ai import AIResponseError, StubProvider, Usage
from app.services.pdf import ocr_book, ocr_cache_path, page_count, render_page


class CountingProvider(StubProvider):
    def __init__(self) -> None:
        super().__init__("")
        self.calls = 0

    def read_page(self, image: bytes, media_type: str, model: str | None = None):
        self.calls += 1
        return super().read_page(image, media_type, model)


class SlowCountingProvider(CountingProvider):
    def read_page(
        self, image: bytes, media_type: str, model: str | None = None
    ) -> tuple[str, Usage]:
        time.sleep(0.01)
        return super().read_page(image, media_type, model)


class FailOnceProvider(CountingProvider):
    def __init__(self) -> None:
        super().__init__()
        self.failed = False

    def read_page(
        self, image: bytes, media_type: str, model: str | None = None
    ) -> tuple[str, Usage]:
        if not self.failed:
            self.failed = True
            self.calls += 1
            raise AIResponseError(
                "incomplete page",
                Usage(cost_usd=Decimal("0.01"), input_tokens=10, output_tokens=20),
            )
        return super().read_page(image, media_type, model)


def _write_pdf(path: Path, pages: int = 4) -> None:
    document = pymupdf.open()
    for number in range(1, pages + 1):
        page = document.new_page()
        page.insert_text((72, 72), f"Cookbook page {number}")
    document.save(path)
    document.close()


@pytest.fixture
def pdf_book(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Book, Path]:
    library = tmp_path / "library"
    directory = library / "Test Author" / "Test Cookbook (99)"
    directory.mkdir(parents=True)
    source = directory / "book.pdf"
    _write_pdf(source)
    monkeypatch.setattr(settings, "calibre_library_path", library)
    monkeypatch.setattr(settings, "ocr_page_concurrency", 2)
    book = Book(
        calibre_id=99,
        title="Test Cookbook",
        author="Test Author",
        path=str(directory.relative_to(library)),
    )
    return book, source


def test_page_rendering(pdf_book: tuple[Book, Path]) -> None:
    _, source = pdf_book
    assert page_count(source) == 4
    with pymupdf.open(source) as document:
        image = render_page(document, 0, 100)
    assert image.startswith(b"\xff\xd8")


def test_ocr_cache_resumes_and_force_refreshes(pdf_book: tuple[Book, Path]) -> None:
    book, _ = pdf_book
    provider = CountingProvider()
    first = ocr_book(book, provider, pages=(2, 4))
    assert len(first) == 3
    assert provider.calls == 3
    second = ocr_book(book, provider, pages=(2, 4))
    assert second == first
    assert provider.calls == 3
    path = ocr_cache_path(book)
    cache = json.loads(path.read_text())
    del cache["pages"]["2"]
    path.write_text(json.dumps(cache))
    resumed = ocr_book(book, provider, pages=(2, 4))
    assert resumed == first
    assert provider.calls == 4
    refreshed = ocr_book(book, provider, pages=(2, 4), force=True)
    assert refreshed == first
    assert provider.calls == 7


def test_page_range_validation(pdf_book: tuple[Book, Path]) -> None:
    book, _ = pdf_book
    provider = CountingProvider()
    with pytest.raises(ValueError, match="Invalid PDF page range"):
        ocr_book(book, provider, pages=(0, 2))
    with pytest.raises(ValueError, match="Invalid PDF page range"):
        ocr_book(book, provider, pages=(3, 5))


def test_concurrent_runs_share_complete_cache(pdf_book: tuple[Book, Path]) -> None:
    book, _ = pdf_book
    provider = SlowCountingProvider()
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(ocr_book, book, provider) for _ in range(2)]
        results = [future.result() for future in futures]

    assert results[0] == results[1]
    assert provider.calls == 4


def test_cache_invalidates_when_pdf_changes(pdf_book: tuple[Book, Path]) -> None:
    book, source = pdf_book
    provider = CountingProvider()
    ocr_book(book, provider)
    replacement = source.with_name("replacement.pdf")
    _write_pdf(replacement, pages=5)
    replacement.replace(source)
    result = ocr_book(book, provider)
    assert len(result) == 5
    assert provider.calls == 9


def test_invalid_cache_page_is_regenerated(pdf_book: tuple[Book, Path]) -> None:
    book, _ = pdf_book
    provider = CountingProvider()
    ocr_book(book, provider)
    path = ocr_cache_path(book)
    cache = json.loads(path.read_text())
    cache["pages"]["0"] = 12
    path.write_text(json.dumps(cache))
    ocr_book(book, provider)
    assert provider.calls == 8


def test_failed_page_drains_results_and_records_usage(
    pdf_book: tuple[Book, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    book, _ = pdf_book
    provider = FailOnceProvider()
    recorded: list[Usage] = []
    monkeypatch.setattr(settings, "ocr_page_concurrency", 1)

    with pytest.raises(AIResponseError, match="incomplete page"):
        ocr_book(book, provider, on_page=lambda _page, usage: recorded.append(usage))

    cache = json.loads(ocr_cache_path(book).read_text())
    assert len(cache["pages"]) == 3
    assert provider.calls == 4
    assert len(recorded) == 4
    assert sum(usage.cost_usd or Decimal(0) for usage in recorded) == Decimal("0.01")

    assert len(ocr_book(book, provider)) == 4
    assert provider.calls == 5


def test_cache_path_rejects_traversal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "calibre_library_path", tmp_path / "library")
    book = Book(calibre_id=1, title="Bad", author="Bad", path="../../escape")
    with pytest.raises(ValueError, match="escapes"):
        ocr_cache_path(book)
