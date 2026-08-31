import string

from pydantic import BaseModel, ConfigDict, Field

from app.services.extraction.review import REVIEW_CHOICES, REVIEW_QUESTION


class ReviewChoice(BaseModel):
    """One answer the operator can give to a paused run's question: the resume token
    (`value`) and the label shown on the choice."""

    value: str
    label: str


class ReviewQuestion(BaseModel):
    """The pending human-in-the-loop question on a run paused at REVIEW — what to ask
    and the choices to offer. Built from the extraction review constants so the graph
    (which raises the interrupt) and the UI (which answers it) never drift."""

    question: str
    choices: list[ReviewChoice]

    @classmethod
    def current(cls) -> "ReviewQuestion":
        return cls(
            question=REVIEW_QUESTION,
            choices=[ReviewChoice(value=value, label=label) for value, label in REVIEW_CHOICES],
        )


class ResumeRequest(BaseModel):
    """The operator's answer to a paused run's review question. `response` must be one
    of the choices the graph offers (validated in the endpoint)."""

    response: str


class RecipeData(BaseModel):
    """A single AI-extracted recipe: validated against the schema.org-style keys the
    model returns (hence the field aliases) and lightly normalised. The pipeline
    injects author/bookTitle/bookOrder before the recipe is persisted."""

    name: str
    description: str | None = None
    ingredients: list["RecipeIngredientData"] = Field(min_length=1, alias="recipeIngredients")
    instructions: list[str] = Field(min_length=1, alias="recipeInstructions")
    yields: str | None = Field(None, alias="recipeYield")
    image: str | None = None
    keywords: list[str] = Field(default_factory=list)
    author: str | None = None
    book_title: str | None = Field(None, alias="bookTitle")
    book_order: int | None = Field(None, alias="bookOrder")

    model_config = ConfigDict(populate_by_name=True)

    def model_post_init(self, _context: object) -> None:
        self.name = string.capwords(self.name)
        if self.yields:
            self.yields = (
                self.yields.capitalize() if self.yields[0].isalpha() else self.yields.lower()
            )


class RecipeIngredientData(BaseModel):
    """A verbatim source line. Classification and parsing happen in enrichment."""

    text: str = Field(min_length=1)
