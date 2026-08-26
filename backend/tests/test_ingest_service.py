"""The ingest service: what it accepts onto disk, and what it does to the library.

Every Calibre call goes through `run_cli`, so these tests replace that one seam and
never shell out — except the two that check the seam itself, which run a real
subprocess to pin the rule that success is exit code and nothing else.
"""

import json
import sqlite3
import uuid
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models import Base, Book
from app.services.ingest import (
    CalibreCLIError,
    DuplicateBookError,
    FileTooLargeError,
    UnsupportedFormatError,
    _filename_from_response,
    remove_from_library,
    run_cli,
    run_ingest,
    stage_file,
    staged_path,
)

EPUB_BYTES = b"PK\x03\x04" + b"\x00" * 64
PDF_BYTES = b"%PDF-1.7" + b"\x00" * 64


class FakeCalibre:
    """Stands in for every Calibre binary, recording what it was asked to do."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.added_id = 42
        self.tags: list[str] = ["Cooking"]
        self.epub_has_cover = True
        self.echo_filename_as_title = False
        self.title = "The Curry Guy"
        self.author = "Dan Toombs"
        self.fail_on: str | None = None
        self.calibre_id_at_remove: int | None = None
        self.book_probe: sessionmaker[Session] | None = None
        self.book_id: uuid.UUID | None = None

    def __call__(self, args: list[str], *, timeout: int = 0) -> str:
        self.calls.append(args)
        binary = args[0]
        if self.fail_on is not None and self.fail_on in args:
            raise CalibreCLIError(f"{binary} failed: refused")
        if binary == "ebook-meta":
            if "--get-cover" in args:
                if self.epub_has_cover:
                    Path(args[args.index("--get-cover") + 1]).write_bytes(b"jpeg")
                return ""
            title = Path(args[1]).stem if self.echo_filename_as_title else self.title
            return f"Title               : {title}\nAuthor(s)           : {self.author}\n"
        if binary == "fetch-ebook-metadata":
            raise AssertionError("ingestion must not reach the network")
        if binary == "ebook-convert":
            Path(args[2]).write_bytes(EPUB_BYTES)
            return "Output saved"
        if binary == "calibredb":
            return self._calibredb(args)
        raise AssertionError(f"unexpected binary {binary}")

    def _calibredb(self, args: list[str]) -> str:
        sub = args[3]
        if sub == "add":
            return f"Added book ids: {self.added_id}"
        if sub == "list":
            return json.dumps([{"id": self.added_id, "tags": self.tags}])
        if sub == "remove":
            self._probe_book()
            return ""
        if sub == "set_metadata":
            return ""
        raise AssertionError(f"unexpected calibredb {sub}")

    def _probe_book(self) -> None:
        """Read the book's calibre_id at the moment of removal, so a test can prove the
        repoint was committed before the old entry went."""
        if self.book_probe is None or self.book_id is None:
            return
        with self.book_probe() as session:
            book = session.get(Book, self.book_id)
            self.calibre_id_at_remove = book.calibre_id if book else None

    def commands(self, sub: str) -> list[list[str]]:
        return [c for c in self.calls if c[0] == "calibredb" and c[3] == sub]

    def command(self, sub: str) -> list[str]:
        found = self.commands(sub)
        assert found, f"expected a calibredb {sub} call, got {[c[3] for c in self.calls]}"
        return found[-1]


@pytest.fixture
def library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty Calibre library — just enough metadata.db for the duplicate check."""
    root = tmp_path / "library"
    root.mkdir()
    conn = sqlite3.connect(root / "metadata.db")
    conn.execute("CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT, path TEXT)")
    conn.commit()
    conn.close()
    monkeypatch.setattr(settings, "calibre_library_path", root)
    monkeypatch.setattr(settings, "ingest_staging_path", tmp_path / "staging")
    return root


def _add_library_book(root: Path, calibre_id: int, title: str, path: str) -> None:
    conn = sqlite3.connect(root / "metadata.db")
    conn.execute("INSERT INTO books VALUES (?, ?, ?)", (calibre_id, title, path))
    conn.commit()
    conn.close()


@pytest.fixture
def calibre(monkeypatch: pytest.MonkeyPatch) -> FakeCalibre:
    fake = FakeCalibre()
    monkeypatch.setattr("app.services.ingest.run_cli", fake)
    return fake


@pytest.fixture
def ingest_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[sessionmaker[Session]]:
    """A throwaway DB for the replace path, which repoints a Book through SessionLocal."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'ingest.sqlite3'}", connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn: Any, _record: Any) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr("app.services.ingest.SessionLocal", factory)
    yield factory
    engine.dispose()


def _stage_epub(name: str = "The_Curry_Guy.epub") -> str:
    return stage_file(name, BytesIO(EPUB_BYTES)).staging_id


# --- Staging: what gets onto disk at all.


def test_rejects_a_format_the_library_cannot_hold(library: Path, calibre: FakeCalibre) -> None:
    with pytest.raises(UnsupportedFormatError):
        stage_file("notes.docx", BytesIO(b"PK\x03\x04"))


def test_a_pdf_stages_and_keeps_its_extension(library: Path, calibre: FakeCalibre) -> None:
    staged = stage_file("Scanned Cookbook.pdf", BytesIO(PDF_BYTES))

    assert staged.format == "pdf"
    assert (library.parent / "staging" / f"{staged.staging_id}.pdf").is_file()


def test_rejects_a_pdf_whose_bytes_belie_its_name(library: Path, calibre: FakeCalibre) -> None:
    with pytest.raises(UnsupportedFormatError):
        stage_file("scan.pdf", BytesIO(b"not a pdf at all"))
    assert list((library.parent / "staging").iterdir()) == []


def test_rejects_a_file_whose_bytes_belie_its_name(library: Path, calibre: FakeCalibre) -> None:
    with pytest.raises(UnsupportedFormatError):
        stage_file("book.epub", BytesIO(b"just some text"))
    assert list((library.parent / "staging").iterdir()) == []


def test_rejects_a_file_over_the_cap(
    library: Path, calibre: FakeCalibre, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ingest_max_bytes", 8)
    with pytest.raises(FileTooLargeError):
        stage_file("big.epub", BytesIO(EPUB_BYTES))
    # The partial write is cleaned up, not left for the sweep.
    assert list((library.parent / "staging").iterdir()) == []


def test_prefills_title_and_author_from_the_file(library: Path, calibre: FakeCalibre) -> None:
    staged = stage_file("whatever.epub", BytesIO(EPUB_BYTES))

    assert (staged.title, staged.author) == ("The Curry Guy", "Dan Toombs")
    assert staged.format == "epub"


def test_falls_back_to_a_tidied_filename_when_the_file_knows_nothing(
    library: Path, calibre: FakeCalibre
) -> None:
    calibre.title = "Unknown"
    calibre.author = "Unknown"

    staged = stage_file("The_Curry_Guy.epub", BytesIO(EPUB_BYTES))

    assert (staged.title, staged.author) == ("The Curry Guy", "")


def test_the_staging_id_is_never_offered_as_a_title(library: Path, calibre: FakeCalibre) -> None:
    # A file with no embedded title makes ebook-meta echo the filename stem, and ours is
    # the staging uuid — the user's own filename is the only useful answer.
    calibre.echo_filename_as_title = True

    staged = stage_file("The_Curry_Guy.txt", BytesIO(b"just some text"))

    assert staged.title == "The Curry Guy"
    assert staged.staging_id not in staged.title


def test_download_filename_prefers_content_disposition() -> None:
    response = httpx.Response(
        200, headers={"content-disposition": 'attachment; filename="Real Name.epub"'}
    )
    assert _filename_from_response(response, "https://example.com/dl?id=9") == "Real Name.epub"


def test_download_filename_falls_back_to_the_url_path() -> None:
    response = httpx.Response(200)
    assert _filename_from_response(response, "https://example.com/books/curry.epub") == "curry.epub"


# --- Ingestion: what reaches the library.


def test_duplicate_title_is_refused_before_anything_is_added(
    library: Path, calibre: FakeCalibre
) -> None:
    _add_library_book(library, 7, "The Curry Guy", "Dan Toombs/The Curry Guy (7)")
    staging_id = _stage_epub()

    with pytest.raises(DuplicateBookError) as caught:
        run_ingest(staging_id, "the  curry guy", "Dan Toombs")

    assert caught.value.calibre_id == 7
    assert calibre.commands("add") == []


def test_ingest_adds_the_book_and_forces_the_confirmed_title_and_food_tag(
    library: Path, calibre: FakeCalibre
) -> None:
    staging_id = _stage_epub()

    outcome = run_ingest(staging_id, "The Curry Guy", "Dan Toombs")

    assert outcome.calibre_id == 42
    assert (outcome.cover, outcome.converted) == (True, False)
    fields = calibre.commands("set_metadata")[-1]
    assert "tags:Cooking,Food" in fields
    assert "title:The Curry Guy" in fields
    assert "authors:Dan Toombs" in fields
    assert any(f.startswith("cover:") for f in fields)


def test_ingestion_never_goes_near_the_network(library: Path, calibre: FakeCalibre) -> None:
    # Everything the app shows — publisher, ISBN, pubdate, description — is embedded in
    # the file and read by `calibredb add`. An online lookup cost ~30s, missed often, and
    # sometimes described a different edition, so there is no lookup left to make.
    staging_id = _stage_epub()

    run_ingest(staging_id, "The Curry Guy", "Dan Toombs")

    assert [c[0] for c in calibre.calls if c[0] == "fetch-ebook-metadata"] == []


def test_the_book_keeps_its_own_cover(library: Path, calibre: FakeCalibre) -> None:
    staging_id = _stage_epub()

    outcome = run_ingest(staging_id, "The Curry Guy", "Dan Toombs")

    assert outcome.calibre_id == 42
    assert outcome.cover is True


def test_a_book_with_no_cover_anywhere_is_still_added(library: Path, calibre: FakeCalibre) -> None:
    calibre.epub_has_cover = False
    staging_id = _stage_epub()

    outcome = run_ingest(staging_id, "The Curry Guy", "Dan Toombs")

    assert (outcome.calibre_id, outcome.cover) == (42, False)


def test_a_finished_ingest_leaves_nothing_in_staging(library: Path, calibre: FakeCalibre) -> None:
    staging_id = _stage_epub()

    run_ingest(staging_id, "The Curry Guy", "Dan Toombs")

    # The book, the OPF and both candidate covers all share the staging id — a stray
    # cover file would sit there until the 24h sweep.
    assert list((library.parent / "staging").glob(f"{staging_id}*")) == []


def test_a_non_epub_is_converted_first(library: Path, calibre: FakeCalibre) -> None:
    staging_id = stage_file("curry.mobi", BytesIO(b"\x00" * 60 + b"BOOKMOBI")).staging_id

    outcome = run_ingest(staging_id, "The Curry Guy", "Dan Toombs")

    assert outcome.converted is True
    assert any(call[0] == "ebook-convert" for call in calibre.calls)
    # Only the EPUB goes to Calibre — the original is discarded.
    assert calibre.command("add")[-1].endswith(".epub")


def test_a_pdf_goes_into_the_library_unconverted(library: Path, calibre: FakeCalibre) -> None:
    staging_id = stage_file("Scanned Cookbook.pdf", BytesIO(PDF_BYTES)).staging_id

    outcome = run_ingest(staging_id, "Scanned Cookbook", "A Chef")

    # A fixed-layout cookbook does not survive ebook-convert, so it is never called.
    assert outcome.converted is False
    assert outcome.format == "pdf"
    assert not any(call[0] == "ebook-convert" for call in calibre.calls)
    assert calibre.command("add")[-1].endswith(".pdf")


def test_a_staged_pdf_resolves_to_itself(library: Path, calibre: FakeCalibre) -> None:
    # staged_path prefers a .epub sibling; a PDF is never converted, so it has none.
    staging_id = stage_file("Scanned Cookbook.pdf", BytesIO(PDF_BYTES)).staging_id

    assert staged_path(staging_id).suffix == ".pdf"


def test_failure_after_the_add_takes_the_new_entry_back_out(
    library: Path, calibre: FakeCalibre
) -> None:
    calibre.fail_on = "set_metadata"
    staging_id = _stage_epub()

    with pytest.raises(CalibreCLIError):
        run_ingest(staging_id, "The Curry Guy", "Dan Toombs")

    assert calibre.command("remove")[-1] == "42"


def test_replace_repoints_the_book_before_removing_the_old_entry(
    library: Path, calibre: FakeCalibre, ingest_db: sessionmaker[Session]
) -> None:
    _add_library_book(library, 7, "Curry Guy (old scan)", "Dan Toombs/Curry Guy (7)")
    with ingest_db() as session:
        book = Book(calibre_id=7, title="The Curry Guy", author="Dan Toombs", path="x")
        session.add(book)
        session.commit()
        book_id = book.id
    calibre.book_probe, calibre.book_id = ingest_db, book_id
    staging_id = _stage_epub()

    outcome = run_ingest(staging_id, "The Curry Guy", "Dan Toombs", replace_book_id=book_id)

    assert outcome.replaced_calibre_id == 7
    assert calibre.command("remove")[-1] == "7"
    # Add before remove: the book already pointed at the new entry when the old one went,
    # so no crash window leaves a Book naming a calibre_id the next sync would cascade on.
    assert calibre.calibre_id_at_remove == 42
    with ingest_db() as session:
        replaced_book = session.get(Book, book_id)
        assert replaced_book is not None and replaced_book.calibre_id == 42


def test_removal_clears_a_directory_calibre_leaves_behind(
    library: Path, calibre: FakeCalibre
) -> None:
    # calibredb deletes the row synchronously and the files in a thread it doesn't wait
    # for, so a fast exit can leave the directory standing. We finish the job.
    book_dir = library / "Dan Toombs" / "The Curry Guy (7)"
    book_dir.mkdir(parents=True)
    (book_dir / "book.epub").write_bytes(EPUB_BYTES)
    _add_library_book(library, 7, "The Curry Guy", "Dan Toombs/The Curry Guy (7)")

    remove_from_library(7)

    assert not book_dir.exists()


# --- The seam itself, against real subprocesses.


def test_stderr_noise_with_a_zero_exit_is_success() -> None:
    # Every Calibre binary chatters about GPUs on a headless host and still works.
    assert "out" in run_cli(["sh", "-c", "echo noise >&2; echo out"])


def test_a_non_zero_exit_is_a_failure_whatever_it_printed() -> None:
    with pytest.raises(CalibreCLIError):
        run_cli(["sh", "-c", "echo fine; exit 3"])
