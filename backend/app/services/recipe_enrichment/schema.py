"""Versioned wire contract for one enrichment completion."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "v4"
PROMPT_VERSION = "v6"
TAXONOMY_VERSION = "v1"


class EnrichmentDecision(BaseModel):
    """Shared validation configuration for enrichment response models."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class OccurrenceDecision(EnrichmentDecision):
    canonical_name: str = Field(min_length=1, alias="n")
    source_name: str | None = Field(default=None, alias="s")
    quantity: str | None = Field(default=None, alias="q")
    unit: str | None = Field(default=None, alias="u")
    preparation: str | None = Field(default=None, alias="p")
    optional: bool = Field(default=False, alias="x")
    alternative_group: int | None = Field(default=None, ge=0, alias="a")
    is_key: bool = Field(default=False, alias="k")

class LineDecision(EnrichmentDecision):
    """An AI replacement or an otherwise unresolved ingredient line."""

    line_id: str = Field(alias="l")
    occurrences: list[OccurrenceDecision] = Field(alias="o")


class NonIngredientLineDecision(EnrichmentDecision):
    """Only exceptional heading/note lines need a decision; ingredient is the default."""

    line_id: str = Field(alias="l")
    kind: Literal["heading", "note"] = Field(alias="k")


class FactDecision(EnrichmentDecision):
    value_id: str = Field(alias="v")
    source: Literal["explicit", "inferred"] = Field(alias="s")
    evidence: str | None = Field(default=None, alias="e")


class MethodDecision(FactDecision):
    is_primary: bool = Field(default=False, alias="p")


class EnrichmentResponse(EnrichmentDecision):
    recipe_id: str = Field(alias="r")
    source_fingerprint: str = Field(alias="f")
    parsed_lines: list[LineDecision] = Field(default_factory=list, alias="p")
    non_ingredient_lines: list[NonIngredientLineDecision] = Field(default_factory=list, alias="n")
    cuisines: list[FactDecision] = Field(default_factory=list, alias="c")
    methods: list[MethodDecision] = Field(default_factory=list, alias="m")
    courses: list[FactDecision] = Field(default_factory=list, alias="o")
    keywords: list[str] = Field(alias="w")

    @model_validator(mode="after")
    def one_primary_method(self) -> "EnrichmentResponse":
        if sum(fact.is_primary for fact in self.methods) > 1:
            raise ValueError("at most one primary method")
        return self


ENRICHMENT_JSON_SCHEMA = EnrichmentResponse.model_json_schema()
