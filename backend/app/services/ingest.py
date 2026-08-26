"""Book ingestion — add a cookbook to the Calibre library by driving the Calibre CLI.

Cookmarks owns its library (it is the single writer), so adding a book is a sequence of
Calibre commands rather than a GUI session: convert to EPUB unless the upload is already
a format the library holds (EPUB or PDF), `calibredb add`, tag it and force the confirmed
title and author on, then let the normal Calibre sync pull the result into the app.
Calibre stays the library engine — nothing about its catalogue is reimplemented here.

**No metadata is fetched over the network.** Everything the app displays — publisher,
ISBN, publication date, description — is embedded in the book file, and `calibredb add`
reads it. An online lookup was tried and dropped: it cost ~30s per ingest, missed often,
and when it did answer it sometimes described a different edition of the book. Enriching
a thin file is a deliberate per-book action for later, not a silent guess at ingest time.

Two behaviours of the Calibre CLI shape this module:

* Every binary writes Qt/GPU noise to stderr on a headless host and still exits 0, so
  success is judged by **exit code alone** — never by whether stderr is empty.
* `calibredb remove` deletes the database row synchronously but its files in a
  background thread, which a fast process exit drops. Removal is therefore verified
  against the book directory and finished by hand when Calibre leaves it behind.

Every subprocess goes through `run_cli`, the single seam tests replace.
"""

import json
import logging
import re
import shutil
import subprocess
import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import httpx

from app.config import settings
from app.db import SessionLocal
from app.models.book import Book
from app.services.calibre import open_calibre_db

logger = logging.getLogger(__name__)

# What the library accepts, with the signature that proves the bytes match the
# extension. None means the format has no usable magic (plain text shapes), so the
# extension is the only check available. Everything outside LIBRARY_FORMATS is
# converted to EPUB on the way in.
ACCEPTED_FORMATS: dict[str, tuple[int, bytes] | None] = {
    "epub": (0, b"PK\x03\x04"),
    "pdf": (0, b"%PDF-"),
    "htmlz": (0, b"PK\x03\x04"),
    "mobi": (60, b"BOOKMOBI"),
    "prc": (60, b"BOOKMOBI"),
    "azw": (60, b"BOOKMOBI"),
    "azw3": (60, b"BOOKMOBI"),
    "lit": (0, b"ITOLITLS"),
    "rtf": (0, b"{\\rtf"),
    "pdb": None,
    "fb2": None,
    "txt": None,
}

# Formats that go into the library as they are. A cookbook PDF is fixed-layout, often
# page images: ebook-convert would destroy it, so it is held and read as a PDF.
LIBRARY_FORMATS = {"epub", "pdf"}

STAGING_MAX_AGE_SECONDS = 24 * 60 * 60
_CLI_TIMEOUT = 300
_METADATA_TIMEOUT = 60
_LOCK_RETRIES = 5


class IngestError(Exception):
    """Any ingestion failure the user should see verbatim on the failed run."""


class UnsupportedFormatError(IngestError):
    pass


class FileTooLargeError(IngestError):
    pass


class StagedFileMissingError(IngestError):
    pass


class CalibreCLIError(IngestError):
    pass


class DuplicateBookError(IngestError):
    """The library already holds a book with this title. Carries the existing entry so
    the run can offer replace instead of leaving the user to work out what clashed."""

    def __init__(self, calibre_id: int, title: str) -> None:
        super().__init__(f"Already in the library: {title}")
        self.calibre_id = calibre_id
        self.title = title


@dataclass(frozen=True)
class StagedBook:
    """A file accepted onto disk and inspected, waiting for the user to confirm it."""

    staging_id: str
    filename: str
    format: str
    title: str
    author: str


@dataclass(frozen=True)
class IngestOutcome:
    calibre_id: int
    title: str
    author: str
    format: str
    converted: bool
    cover: bool
    replaced_calibre_id: int | None


def run_cli(args: list[str], *, timeout: int = _CLI_TIMEOUT) -> str:
    """Run a Calibre command and return its stdout. The one seam every subprocess goes
    through, so tests replace this and never shell out. Judges success by exit code
    only — the binaries chatter on stderr even when they work."""
    logger.info("calibre cli: %s", " ".join(args))
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise CalibreCLIError(f"{args[0]} is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise CalibreCLIError(f"{args[0]} timed out after {timeout}s") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        raise CalibreCLIError(f"{args[0]} failed: {detail[-1] if detail else 'no output'}")
    return result.stdout


def _calibredb(*args: str, timeout: int = _CLI_TIMEOUT) -> str:
    """`calibredb` against our library, retrying while another Calibre process holds the
    lock — the worker and an admin action can collide on a busy library."""
    command = ["calibredb", "--with-library", str(settings.calibre_library_path), *args]
    for attempt in range(_LOCK_RETRIES):
        try:
            return run_cli(command, timeout=timeout)
        except CalibreCLIError as exc:
            if "using this library" not in str(exc) or attempt == _LOCK_RETRIES - 1:
                raise
            time.sleep(2**attempt)
    raise CalibreCLIError("unreachable")


def staging_dir() -> Path:
    path = settings.ingest_staging_path
    path.mkdir(parents=True, exist_ok=True)
    return path


def sweep_staging() -> int:
    """Delete staged files nobody came back for. A duplicate-failed run keeps its file so
    the replace offer can reuse the same staging_id, so the window is generous."""
    cutoff = time.time() - STAGING_MAX_AGE_SECONDS
    removed = 0
    for path in staging_dir().iterdir():
        if path.is_file() and path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)
            removed += 1
    if removed:
        logger.info("Swept %d stale staged file(s)", removed)
    return removed


def staged_path(staging_id: str) -> Path:
    """The staged book for this id, preferring the converted EPUB when one exists."""
    candidates = sorted(staging_dir().glob(f"{staging_id}.*"))
    books = [p for p in candidates if p.suffix.lstrip(".").lower() in ACCEPTED_FORMATS]
    if not books:
        raise StagedFileMissingError("The staged file has expired — upload it again.")
    for path in books:
        if path.suffix.lower() == ".epub":
            return path
    return books[0]


def discard_staged(staging_id: str) -> None:
    for path in staging_dir().glob(f"{staging_id}.*"):
        path.unlink(missing_ok=True)


def _extension(filename: str) -> str:
    ext = Path(filename).suffix.lstrip(".").lower()
    if ext not in ACCEPTED_FORMATS:
        supported = ", ".join(sorted(ACCEPTED_FORMATS))
        raise UnsupportedFormatError(f"{ext or 'that file'} can't be added. Try: {supported}")
    return ext


def _check_magic(path: Path, ext: str) -> None:
    signature = ACCEPTED_FORMATS[ext]
    if signature is None:
        return
    offset, expected = signature
    with path.open("rb") as handle:
        handle.seek(offset)
        if handle.read(len(expected)) != expected:
            raise UnsupportedFormatError(f"That file isn't really a {ext} book.")


def _write_capped(dest: Path, chunks: Iterable[bytes]) -> None:
    written = 0
    with dest.open("wb") as handle:
        for chunk in chunks:
            written += len(chunk)
            if written > settings.ingest_max_bytes:
                handle.close()
                dest.unlink(missing_ok=True)
                cap = settings.ingest_max_bytes // 1_000_000
                raise FileTooLargeError(f"That book is over the {cap} MB limit.")
            handle.write(chunk)


def _stage(filename: str, chunks: Iterable[bytes]) -> StagedBook:
    sweep_staging()
    ext = _extension(filename)
    staging_id = str(uuid.uuid4())
    dest = staging_dir() / f"{staging_id}.{ext}"
    try:
        _write_capped(dest, chunks)
        _check_magic(dest, ext)
    except IngestError:
        dest.unlink(missing_ok=True)
        raise
    title, author = prefill_metadata(dest, filename)
    return StagedBook(
        staging_id=staging_id, filename=filename, format=ext, title=title, author=author
    )


def stage_file(filename: str, stream: BinaryIO) -> StagedBook:
    return _stage(filename, iter(lambda: stream.read(1024 * 1024), b""))


def stage_url(url: str) -> StagedBook:
    """Fetch a book from a direct download link. Follows redirects and honours
    Content-Disposition, since download links rarely end in the filename."""
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=60) as response:
            response.raise_for_status()
            filename = _filename_from_response(response, url)
            return _stage(filename, response.iter_bytes(1024 * 1024))
    except httpx.HTTPError as exc:
        raise IngestError(f"Could not download that link: {exc}") from exc


def _filename_from_response(response: httpx.Response, url: str) -> str:
    disposition = response.headers.get("content-disposition", "")
    match = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", disposition)
    if match:
        return Path(match.group(1).strip()).name
    return Path(httpx.URL(url).path).name or "download"


def prefill_metadata(path: Path, filename: str) -> tuple[str, str]:
    """Title and author for the confirm form, from the file's own metadata where it has
    any and a tidied filename where it hasn't. The user corrects it either way, so a
    failure here is not worth failing the upload over."""
    title = author = ""
    try:
        output = run_cli(["ebook-meta", str(path)], timeout=_METADATA_TIMEOUT)
    except CalibreCLIError:
        logger.warning("ebook-meta could not read %s", path.name)
        output = ""
    for line in output.splitlines():
        field, _, value = line.partition(":")
        if field.strip() == "Title" and not title:
            title = value.strip()
        elif field.strip().startswith("Author") and not author:
            author = re.sub(r"\s*\[[^\]]*\]", "", value).strip()
    # A file carrying no title of its own makes ebook-meta echo the filename stem back —
    # and ours is the staging uuid, which is no use to anybody. Prefer the real filename.
    if title == path.stem:
        title = ""
    if not title or title.lower() == "unknown":
        title = _title_from_filename(filename)
    if author.lower() == "unknown":
        author = ""
    return title, author


def _title_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    return re.sub(r"\s+", " ", re.sub(r"[._]+", " ", stem)).strip()


def _normalise(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip().casefold()


def find_duplicate(title: str) -> tuple[int, str] | None:
    """The library entry whose title matches, if any. Our own check rather than
    calibredb's, so the add can pass --duplicates and this stays the only authority."""
    wanted = _normalise(title)
    conn = open_calibre_db(settings.calibre_library_path)
    try:
        for row in conn.execute("SELECT id, title FROM books"):
            if _normalise(row["title"]) == wanted:
                return row["id"], row["title"]
    finally:
        conn.close()
    return None


def _book_directory(calibre_id: int) -> Path | None:
    conn = open_calibre_db(settings.calibre_library_path)
    try:
        row = conn.execute("SELECT path FROM books WHERE id = ?", (calibre_id,)).fetchone()
    finally:
        conn.close()
    return settings.calibre_library_path / row["path"] if row else None


def remove_from_library(calibre_id: int) -> None:
    """Delete a book from the Calibre library, files and all.

    calibredb hands the file deletion to a background thread it doesn't wait for, so a
    row can vanish while its directory survives. We read the directory first and clear
    any remains ourselves rather than leaving orphans the next add would trip over."""
    directory = _book_directory(calibre_id)
    _calibredb("remove", "--permanent", str(calibre_id))
    if directory is None or not directory.exists():
        return
    library = settings.calibre_library_path.resolve()
    if not directory.resolve().is_relative_to(library):
        logger.error("Refusing to clear %s — outside the library", directory)
        return
    shutil.rmtree(directory, ignore_errors=True)
    logger.info("Cleared book directory Calibre left behind: %s", directory.name)


def _cover_from_file(book: Path, staging_id: str) -> Path | None:
    """The cover the book carries itself — the only cover source we use, since Calibre's
    all go through its embedded browser. Applying a fetched OPF also clears the cover
    Calibre extracts on add, so without this a successful metadata lookup would leave a
    book worse off than a failed one."""
    path = staging_dir() / f"{staging_id}.filecover.jpg"
    try:
        run_cli(["ebook-meta", str(book), "--get-cover", str(path)], timeout=_METADATA_TIMEOUT)
    except CalibreCLIError:
        logger.warning("Could not read a cover out of %s", book.name)
        return None
    return path if path.exists() else None


def _existing_tags(calibre_id: int) -> list[str]:
    output = _calibredb("list", "--search", f"id:{calibre_id}", "--fields", "tags", "--for-machine")
    try:
        rows = json.loads(output or "[]")
    except json.JSONDecodeError:
        return []
    tags = rows[0].get("tags", []) if rows else []
    return [tags] if isinstance(tags, str) else list(tags)


def _apply_metadata(calibre_id: int, title: str, author: str, cover: Path | None) -> None:
    """Add the selection tag and force the user's confirmed title and author over
    whatever the file claimed. Everything else — publisher, ISBN, publication date,
    description — calibredb read out of the book itself on add."""
    tags = _existing_tags(calibre_id)
    if settings.calibre_sync_tag not in tags:
        tags.append(settings.calibre_sync_tag)
    fields = [
        "--field",
        f"tags:{','.join(tags)}",
        "--field",
        f"title:{title}",
        "--field",
        f"authors:{author}",
    ]
    if cover is not None:
        fields += ["--field", f"cover:{cover}"]
    _calibredb("set_metadata", str(calibre_id), *fields)


def _added_id(output: str) -> int:
    match = re.search(r"Added book ids?:\s*(\d+)", output)
    if match is None:
        raise CalibreCLIError(f"calibredb add gave no book id: {output.strip()[:200]}")
    return int(match.group(1))


def _repoint_book(book_id: uuid.UUID, calibre_id: int) -> int:
    """Point an existing Book at the newly added library entry and commit before the old
    entry is removed. Add-before-remove: no committed Book ever names a calibre_id that
    has left the library, which is the one state the next sync answers by deleting the
    book and every recipe under it."""
    with SessionLocal() as session:
        book = session.get(Book, book_id)
        if book is None:
            raise IngestError("The book being replaced no longer exists.")
        old_calibre_id = book.calibre_id
        book.calibre_id = calibre_id
        session.commit()
    return old_calibre_id


def run_ingest(
    staging_id: str,
    title: str,
    author: str,
    *,
    replace_book_id: uuid.UUID | None = None,
) -> IngestOutcome:
    """Put a staged book into the Calibre library and return what happened.

    Everything before `calibredb add` is reversible by doing nothing. Everything after it
    is undone by a compensating remove, so a failure never leaves a half-ingested entry
    for the next attempt to trip over as a phantom duplicate."""
    source = staged_path(staging_id)
    fmt = source.suffix.lstrip(".").lower()

    if replace_book_id is None:
        duplicate = find_duplicate(title)
        if duplicate is not None:
            raise DuplicateBookError(*duplicate)

    library_file = source
    converted = False
    if fmt not in LIBRARY_FORMATS:
        library_file = staging_dir() / f"{staging_id}.epub"
        run_cli(["ebook-convert", str(source), str(library_file)])
        source.unlink(missing_ok=True)
        converted = True

    cover = _cover_from_file(library_file, staging_id)
    calibre_id = _added_id(_calibredb("add", "--duplicates", str(library_file)))

    replaced: int | None = None
    try:
        _apply_metadata(calibre_id, title, author, cover)
        if replace_book_id is not None:
            replaced = _repoint_book(replace_book_id, calibre_id)
    except Exception:
        # Nothing durable points at the new entry yet, so take it back out.
        logger.exception("Ingest failed after add; removing library entry %d", calibre_id)
        try:
            remove_from_library(calibre_id)
        except Exception:
            logger.exception("Compensating remove of %d failed — stray entry left", calibre_id)
        raise

    if replaced is not None:
        try:
            remove_from_library(replaced)
        except Exception as exc:
            # The repoint is committed, so the new entry is the book — compensating now
            # would destroy it. Name the stray instead: the next sync surfaces it as a
            # zero-recipe book, which delete-from-library clears.
            raise IngestError(
                f"Added and relinked, but the old library entry {replaced} could not be "
                f"removed: {exc}"
            ) from exc

    discard_staged(staging_id)
    return IngestOutcome(
        calibre_id=calibre_id,
        title=title,
        author=author,
        format=fmt,
        converted=converted,
        cover=cover is not None,
        replaced_calibre_id=replaced,
    )
