from enum import StrEnum


class AIProvider(StrEnum):
    ANTHROPIC = "ANTHROPIC"
    GEMINI = "GEMINI"
    OPENROUTER = "OPENROUTER"
    STUB = "STUB"


class TaskType(StrEnum):
    """Which kind of background job a task run records. Extraction is one type among
    several maintenance jobs (book-keyword tagging, keyword dedup, Calibre sync, adding
    a book to the library)."""

    EXTRACTION = "extraction"
    BOOK_KEYWORDS = "book_keywords"
    KEYWORD_DEDUP = "keyword_dedup"
    CALIBRE_SYNC = "calibre_sync"
    BOOK_INGEST = "book_ingest"
    RECIPE_ENRICHMENT_PILOT = "recipe_enrichment_pilot"
    RECIPE_ENRICHMENT_BACKFILL = "recipe_enrichment_backfill"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    REVIEW = "review"
    DONE = "done"
    FAILED = "failed"


class ReadingMode(StrEnum):
    """The two ways a book is read: its own pages in the EPUB reader, or its extracted
    recipes one at a time in book order."""

    BOOK = "book"
    RECIPES = "recipes"


class ExtractionMethod(StrEnum):
    FILE = "file"
    BLOCK = "block"
    PDF_OCR = "pdf_ocr"


class RecipeEnrichmentStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class EnrichmentBatchStatus(StrEnum):
    PREPARING = "preparing"
    SUBMITTED = "submitted"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    APPLIED = "applied"


class EnrichmentBatchItemStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STALE = "stale"
    APPLIED = "applied"


class RecipeFacetKind(StrEnum):
    METHOD = "method"
    COURSE = "course"


def enum_values(enum_cls: type[StrEnum]) -> list[str]:
    """values_callable for SQLAlchemy Enum: store member values, not names."""
    return [member.value for member in enum_cls.__members__.values()]
