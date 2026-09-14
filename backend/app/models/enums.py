from enum import StrEnum


class AIProvider(StrEnum):
    ANTHROPIC = "ANTHROPIC"
    GEMINI = "GEMINI"
    OPENROUTER = "OPENROUTER"
    STUB = "STUB"


class ModelRole(StrEnum):
    """The job a model is being asked to do. Each provider maps these roles to its
    own model names, so model selection is decoupled from the stored extraction
    method (file/block) and from any one provider's catalogue.

    Lives here rather than in `app.services.ai.base` so the AI-configuration tables
    (`AIProviderConfig`, `AITaskAssignment`) and the config schemas can reference it
    without importing the provider layer. `base.py` re-exports it for its callers."""

    IMAGE_MATCH = "image_match"
    OCR = "ocr"
    MANY_RECIPES_PER_FILE = "many_recipes_per_file"
    ONE_RECIPE_PER_FILE = "one_recipe_per_file"
    BLOCKS_OF_FILES = "blocks_of_files"
    BOOK_KEYWORDS = "book_keywords"
    KEYWORD_DEDUP = "keyword_dedup"
    INGREDIENT_DEDUP = "ingredient_dedup"
    ASSISTANT = "assistant"
    RECIPE_ENRICHMENT = "recipe_enrichment"
    RECIPE_INGREDIENTS = "recipe_ingredients"
    RECIPE_INGREDIENTS_FALLBACK = "recipe_ingredients_fallback"
    RECIPE_SEMANTICS = "recipe_semantics"


class TaskType(StrEnum):
    """Which kind of background job a task run records. Extraction is one type among
    several maintenance jobs (book-keyword tagging, keyword dedup, Calibre sync, adding
    a book to the library).

    RECIPE_ENRICHMENT_PILOT and RECIPE_ENRICHMENT_BACKFILL are retired: nothing
    creates them any more (their endpoints and workers are removed), but the
    members stay so historical runs from the completed backfill still load.
    """

    EXTRACTION = "extraction"
    BOOK_KEYWORDS = "book_keywords"
    KEYWORD_DEDUP = "keyword_dedup"
    INGREDIENT_DEDUP = "ingredient_dedup"
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


class RecipeFacetKind(StrEnum):
    METHOD = "method"
    COURSE = "course"


def enum_values(enum_cls: type[StrEnum]) -> list[str]:
    """values_callable for SQLAlchemy Enum: store member values, not names."""
    return [member.value for member in enum_cls.__members__.values()]
