from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from ninja import Field, Schema


class UserOut(Schema):
    id: int
    username: str
    is_staff: bool


class LoginIn(Schema):
    username: str
    password: str


class MessageOut(Schema):
    detail: str


class BookOut(Schema):
    id: UUID
    calibre_id: int
    title: str
    clean_title: str
    author: str
    pubdate: date | None = None
    isbn: str = ""
    description: str = ""
    recipe_count: int = 0


class BookDetailOut(BookOut):
    available_models: list[str] = []
    sample_recipe_ids: list[UUID] = []
    first_recipe_id: UUID | None = None


class KeywordOut(Schema):
    id: UUID
    name: str
    recipe_count: int = 0


class RecipeSummary(Schema):
    id: UUID
    book_id: UUID
    book_title: str
    book_clean_title: str
    book_author: str
    order: int
    name: str
    clean_name: str
    description: str | None = None
    yields: str | None = None
    has_image: bool
    image: str | None = None
    keywords: list[str] = []


class NeighbourRecipe(Schema):
    id: UUID
    name: str
    clean_name: str


class BreadcrumbContext(Schema):
    type: Literal["book", "list", "search"]
    book_id: UUID | None = None
    book_title: str | None = None
    list_id: UUID | None = None
    list_name: str | None = None


class RecipeDetail(Schema):
    id: UUID
    book_id: UUID
    book_title: str
    book_clean_title: str
    book_author: str
    order: int
    name: str
    clean_name: str
    description: str | None = None
    yields: str | None = None
    ingredients: list[str] = []
    instructions: list[str] = []
    image: str | None = None
    keywords: list[str] = []
    list_ids: list[UUID] = []
    is_favourite: bool = False
    favourites_list_id: UUID | None = None
    previous_recipe: NeighbourRecipe | None = None
    next_recipe: NeighbourRecipe | None = None
    breadcrumb: BreadcrumbContext | None = None


class RecipeListSummary(Schema):
    id: UUID
    name: str
    is_default: bool
    recipe_count: int = 0


class RecipeListIn(Schema):
    name: str


class KeywordsIn(Schema):
    keywords: list[str]


class PaginatedRecipes(Schema):
    items: list[RecipeSummary]
    page: int
    pages: int
    total: int
    page_size: int
    has_next: bool
    has_previous: bool


class PaginatedBooks(Schema):
    items: list[BookOut]
    page: int
    pages: int
    total: int
    page_size: int
    has_next: bool
    has_previous: bool


class ConfigOut(Schema):
    ai_provider: str
    api_key_masked: str = ""
    has_api_key: bool = False
    extraction_rate_limit_per_minute: int
    is_configured: bool


class ConfigPatch(Schema):
    ai_provider: str | None = None
    api_key: str | None = None
    extraction_rate_limit_per_minute: int | None = None


class ExtractionReportOut(Schema):
    id: UUID
    book_id: UUID
    book_title: str
    book_clean_title: str
    book_author: str
    provider_name: str | None = None
    model_name: str | None = None
    queued_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    total_chapters: int
    chapters_processed_count: int
    extraction_method: str | None = None
    images_in_separate_chapters: bool | None = None
    images_can_be_matched: bool | None = None
    recipes_found: int
    cost_usd: Decimal | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    status: str
    image_count: int = 0


class ExtractionReportsBundle(Schema):
    reports: list[ExtractionReportOut]
    total_books: int
    total_recipes: int
    processed_books: int
    total_cost: float
    provider_configured: bool


class ExtractIn(Schema):
    extraction_method: Literal["file", "block"] | None = None
    model_name: str | None = None


class ResumeExtractionIn(Schema):
    response: Literal["has_images", "no_images"]


class AISearchIn(Schema):
    prompt: str
    limit: int = 1000


class AISearchOut(Schema):
    search_key: str
    count: int


class HomeStats(Schema):
    has_books: bool
    has_recipes: bool
    is_configured: bool
    books_count: int
    book_of_the_day: BookOut | None = None


class QueueCountIn(Schema):
    count: int = 10
    extraction_method: Literal["file", "block"] | None = None


class QueueAllIn(Schema):
    extraction_method: Literal["file", "block"] | None = None


class TasksOverview(Schema):
    books_count: int
    books_with_recipes_count: int


class FilterCondition(Schema):
    field: str
    op: Literal["contains", "not_contains", "equals", "starts"] = "contains"
    value: str
    group: int = 0
    logic: Literal["and", "or"] = "or"


class RecipeQuery(Schema):
    q: str = ""
    book_id: UUID | None = None
    selected_lists: list[UUID] = Field(default_factory=list)
    selected_keywords: list[str] = Field(default_factory=list)
    vector_search_key: str = ""
    group_logic: Literal["and", "or"] = "or"
    sort: str = ""
    page: int = 1
    page_size: int = 30
    filters: list[FilterCondition] = Field(default_factory=list)
