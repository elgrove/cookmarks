"""The versioned wire contract for one enrichment completion."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "v1"
PROMPT_VERSION = "v2"
TAXONOMY_VERSION = "v1"


class OccurrenceDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ingredient_id: str | None = Field(
        default=None,
        description="An exact ID from the supplied ingredient vocabulary. Mutually exclusive with canonical_name.",
    )
    canonical_name: str | None = Field(
        default=None,
        description="A new singular UK-English canonical ingredient name. Mutually exclusive with ingredient_id.",
    )
    source_name: str | None = None
    quantity: str | None = None
    unit: str | None = None
    preparation: str | None = None
    optional: bool = False
    alternative_group: int | None = Field(default=None, ge=0)
    is_key: bool = False

    @model_validator(mode="after")
    def has_resolution(self) -> "OccurrenceDecision":
        if bool(self.ingredient_id) == bool(self.canonical_name):
            raise ValueError("occurrence needs exactly one ingredient_id or canonical_name")
        return self


class LineDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_id: str
    kind: Literal["ingredient", "heading", "note"]
    accept_deterministic: Literal[True] | None = Field(
        default=None,
        description=(
            "Set true only for a line ID supplied in deterministic_proposals; then omit occurrences. "
            "For every ai_parse_line_id omit this field."
        ),
    )
    occurrences: list[OccurrenceDecision] = Field(default_factory=list)

    @model_validator(mode="after")
    def has_one_parse_path(self) -> "LineDecision":
        if self.accept_deterministic and self.occurrences:
            raise ValueError("an accepted deterministic proposal must not include occurrences")
        return self


class FactDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value_id: str
    source: Literal["explicit", "inferred"]
    evidence: str | None = None


class MethodDecision(FactDecision):
    is_primary: bool = False


class EnrichmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipe_id: str
    source_fingerprint: str
    lines: list[LineDecision]
    cuisines: list[FactDecision] = Field(default_factory=list)
    methods: list[MethodDecision] = Field(default_factory=list)
    courses: list[FactDecision] = Field(default_factory=list)
    keywords: list[str]

    @model_validator(mode="after")
    def one_primary_method(self) -> "EnrichmentResponse":
        if sum(fact.is_primary for fact in self.methods) > 1:
            raise ValueError("at most one primary method")
        return self


ENRICHMENT_JSON_SCHEMA = EnrichmentResponse.model_json_schema()
