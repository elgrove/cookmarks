from enum import StrEnum


class AIProvider(StrEnum):
    GEMINI = "GEMINI"
    OPENROUTER = "OPENROUTER"
    STUB = "STUB"


class TaskType(StrEnum):
    """Which kind of background job a task run records. Extraction is one type among
    several maintenance jobs (book-keyword tagging, keyword dedup, Calibre sync)."""

    EXTRACTION = "extraction"
    BOOK_KEYWORDS = "book_keywords"
    KEYWORD_DEDUP = "keyword_dedup"
    CALIBRE_SYNC = "calibre_sync"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    REVIEW = "review"
    DONE = "done"
    FAILED = "failed"


class ExtractionMethod(StrEnum):
    FILE = "file"
    BLOCK = "block"


def enum_values(enum_cls: type[StrEnum]) -> list[str]:
    """values_callable for SQLAlchemy Enum: store member values, not names."""
    return [member.value for member in enum_cls.__members__.values()]
