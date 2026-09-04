"""Versioned wire contract for one enrichment completion."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "v6"
PROMPT_VERSION = "v15"
TAXONOMY_VERSION = "v1"


class EnrichmentDecision(BaseModel):
    """Shared validation configuration for enrichment response models."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class OccurrenceDecision(EnrichmentDecision):
    canonical_name: str = Field(min_length=1, max_length=300, alias="n")
    quantity: str | None = Field(default=None, max_length=100, alias="q")
    unit: str | None = Field(default=None, max_length=50, alias="u")
    preparation: str | None = Field(default=None, max_length=500, alias="p")
    optional: bool = Field(default=False, alias="x")
    alternative_group: int | None = Field(default=None, ge=0, alias="a")
    is_key: bool = Field(default=False, alias="k")


class LineDecision(EnrichmentDecision):
    """An AI replacement or an otherwise unresolved ingredient line."""

    line_id: str = Field(alias="l")
    occurrences: list[OccurrenceDecision] = Field(min_length=1, max_length=20, alias="o")


class NonIngredientLineDecision(EnrichmentDecision):
    """Only exceptional heading/note lines need a decision; ingredient is the default."""

    line_id: str = Field(alias="l")
    kind: Literal["heading", "note"] = Field(alias="k")


class MethodDecision(EnrichmentDecision):
    value_id: str = Field(alias="v")
    is_primary: bool = Field(default=False, alias="p")


class EnrichmentResponse(EnrichmentDecision):
    parsed_lines: list[LineDecision] = Field(default_factory=list, max_length=100, alias="p")
    non_ingredient_lines: list[NonIngredientLineDecision] = Field(
        default_factory=list, max_length=100, alias="n"
    )
    cuisines: list[str] = Field(default_factory=list, max_length=10, alias="c")
    methods: list[MethodDecision] = Field(default_factory=list, max_length=10, alias="m")
    courses: list[str] = Field(default_factory=list, max_length=10, alias="o")
    keywords: list[str] = Field(max_length=5, alias="w")

    @model_validator(mode="after")
    def one_primary_method(self) -> "EnrichmentResponse":
        if sum(fact.is_primary for fact in self.methods) > 1:
            raise ValueError("at most one primary method")
        return self


ENRICHMENT_JSON_SCHEMA = EnrichmentResponse.model_json_schema()


def _without_stateful_constraints(value: object) -> object:
    """Remove JSON Schema limits that Gemini cannot compile for this response."""
    if isinstance(value, dict):
        return {
            key: _without_stateful_constraints(item)
            for key, item in value.items()
            if key not in {"maxItems", "maxLength", "minItems", "minLength", "minimum"}
        }
    if isinstance(value, list):
        return [_without_stateful_constraints(item) for item in value]
    return value


# Gemini validates the returned JSON with this reduced schema. Pydantic still applies
# the full constraints after the response is received.
GEMINI_ENRICHMENT_JSON_SCHEMA = _without_stateful_constraints(ENRICHMENT_JSON_SCHEMA)
