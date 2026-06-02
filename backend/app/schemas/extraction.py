import string

from pydantic import BaseModel, ConfigDict, Field


class RecipeData(BaseModel):
    """A single AI-extracted recipe: validated against the schema.org-style keys the
    model returns (hence the field aliases) and lightly normalised. The pipeline
    injects author/bookTitle/bookOrder before the recipe is persisted."""

    name: str
    description: str | None = None
    ingredients: list[str] = Field(min_length=1, alias="recipeIngredients")
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
