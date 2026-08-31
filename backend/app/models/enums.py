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


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
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


class IngredientLineKind(StrEnum):
    INGREDIENT = "ingredient"
    HEADING = "heading"
    NOTE = "note"


class IngredientParseMethod(StrEnum):
    DETERMINISTIC = "deterministic"
    AI = "ai"


class IngredientResolutionMethod(StrEnum):
    CANONICAL_NAME = "canonical_name"
    ALIAS = "alias"
    AI_EXISTING = "ai_existing"
    AI_CREATED = "ai_created"


class RecipeFactSource(StrEnum):
    EXPLICIT = "explicit"
    INFERRED = "inferred"


class RecipeEnrichmentStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class RecipeFacetKind(StrEnum):
    METHOD = "method"
    COURSE = "course"


def enum_values(enum_cls: type[StrEnum]) -> list[str]:
    """values_callable for SQLAlchemy Enum: store member values, not names."""
    return [member.value for member in enum_cls.__members__.values()]
