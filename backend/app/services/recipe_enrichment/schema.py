"""Versioned wire contract for one enrichment completion."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "v6"
PROMPT_VERSION = "v15"
TAXONOMY_VERSION = "v1"

_EN_GB_INGREDIENT_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bchil[ei]s?\b", re.IGNORECASE), "chilli"),
    (re.compile(r"\bcilantro\b", re.IGNORECASE), "coriander"),
    (re.compile(r"\beggplants?\b", re.IGNORECASE), "aubergine"),
    (re.compile(r"\bzucchinis?\b", re.IGNORECASE), "courgette"),
    (re.compile(r"\b(scallions?|green onions?)\b", re.IGNORECASE), "spring onion"),
]


def normalize_ingredient_name(name: str) -> str:
    cleaned = name.strip()
    for pattern, replacement in _EN_GB_INGREDIENT_RULES:
        def _replace_match(match: re.Match[str], repl: str = replacement) -> str:
            val = match.group(0)
            if val.istitle():
                return repl.title()
            if val.isupper():
                return repl.upper()
            return repl.lower()

        cleaned = pattern.sub(_replace_match, cleaned)
    return cleaned

_CUISINE_ALIASES: dict[str, str] = {
    "afghanistan": "afghan",
    "albania": "albanian",
    "algeria": "algerian",
    "america": "american",
    "argentina": "argentinian",
    "armenia": "armenian",
    "australia": "australian",
    "austria": "austrian",
    "bangladesh": "bangladeshi",
    "belgium": "belgian",
    "brazil": "brazilian",
    "britain": "british",
    "bulgaria": "bulgarian",
    "cambodia": "cambodian",
    "canada": "canadian",
    "chile": "chilean",
    "china": "chinese",
    "colombia": "colombian",
    "croatia": "croatian",
    "cuba": "cuban",
    "denmark": "danish",
    "egypt": "egyptian",
    "ethiopia": "ethiopian",
    "finland": "finnish",
    "france": "french",
    "georgia": "georgian",
    "germany": "german",
    "greece": "greek",
    "hungary": "hungarian",
    "iceland": "icelandic",
    "india": "indian",
    "indonesia": "indonesian",
    "iran": "iranian",
    "iraq": "iraqi",
    "ireland": "irish",
    "israel": "israeli",
    "italy": "italian",
    "jamaica": "jamaican",
    "japan": "japanese",
    "jordan": "jordanian",
    "kenya": "kenyan",
    "korea": "korean",
    "lebanon": "lebanese",
    "malaysia": "malaysian",
    "mexico": "mexican",
    "morocco": "moroccan",
    "nepal": "nepalese",
    "nigeria": "nigerian",
    "norway": "norwegian",
    "pakistan": "pakistani",
    "palestine": "palestinian",
    "peru": "peruvian",
    "poland": "polish",
    "portugal": "portuguese",
    "romania": "romanian",
    "russia": "russian",
    "saudi arabia": "saudi",
    "scotland": "scottish",
    "serbia": "serbian",
    "singapore": "singaporean",
    "slovakia": "slovak",
    "somalia": "somali",
    "south africa": "south-african",
    "spain": "spanish",
    "sri lanka": "sri-lankan",
    "sweden": "swedish",
    "switzerland": "swiss",
    "syria": "syrian",
    "taiwan": "taiwanese",
    "thailand": "thai",
    "tunisia": "tunisian",
    "turkey": "turkish",
    "ukraine": "ukrainian",
    "venezuela": "venezuelan",
    "vietnam": "vietnamese",
    "wales": "welsh",
}


def normalize_cuisine_ids(cuisines: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in cuisines:
        folded = item.strip().lower().replace(" ", "-")
        resolved = _CUISINE_ALIASES.get(item.strip().lower(), folded)
        if resolved and resolved not in seen:
            seen.add(resolved)
            cleaned.append(resolved)
    return cleaned


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

    @field_validator("canonical_name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> str:
        if isinstance(value, str):
            return normalize_ingredient_name(value)
        return str(value)


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


class Stage1Response(EnrichmentDecision):
    parsed_lines: list[LineDecision] = Field(default_factory=list, max_length=100, alias="p")
    non_ingredient_lines: list[NonIngredientLineDecision] = Field(
        default_factory=list, max_length=100, alias="n"
    )


class Stage2Response(EnrichmentDecision):
    cuisines: list[str] = Field(default_factory=list, max_length=10, alias="c")
    methods: list[MethodDecision] = Field(default_factory=list, max_length=10, alias="m")
    courses: list[str] = Field(default_factory=list, max_length=10, alias="o")
    keywords: list[str] = Field(default_factory=list, max_length=5, alias="w")

    @field_validator("cuisines", mode="before")
    @classmethod
    def normalize_cuisines(cls, value: object) -> list[str]:
        if isinstance(value, list):
            return normalize_cuisine_ids([str(item) for item in value])
        return []

    @model_validator(mode="after")
    def one_primary_method(self) -> "Stage2Response":
        if sum(fact.is_primary for fact in self.methods) > 1:
            raise ValueError("at most one primary method")
        return self


class EnrichmentResponse(EnrichmentDecision):
    parsed_lines: list[LineDecision] = Field(default_factory=list, max_length=100, alias="p")
    non_ingredient_lines: list[NonIngredientLineDecision] = Field(
        default_factory=list, max_length=100, alias="n"
    )
    cuisines: list[str] = Field(default_factory=list, max_length=10, alias="c")
    methods: list[MethodDecision] = Field(default_factory=list, max_length=10, alias="m")
    courses: list[str] = Field(default_factory=list, max_length=10, alias="o")
    keywords: list[str] = Field(default_factory=list, max_length=5, alias="w")

    @field_validator("cuisines", mode="before")
    @classmethod
    def normalize_cuisines(cls, value: object) -> list[str]:
        if isinstance(value, list):
            return normalize_cuisine_ids([str(item) for item in value])
        return []

    @model_validator(mode="after")
    def one_primary_method(self) -> "EnrichmentResponse":
        if sum(fact.is_primary for fact in self.methods) > 1:
            raise ValueError("at most one primary method")
        return self

    @classmethod
    def from_stages(cls, stage1: Stage1Response, stage2: Stage2Response) -> "EnrichmentResponse":
        return cls(
            p=stage1.parsed_lines,
            n=stage1.non_ingredient_lines,
            c=stage2.cuisines,
            m=stage2.methods,
            o=stage2.courses,
            w=stage2.keywords,
        )


ENRICHMENT_JSON_SCHEMA = EnrichmentResponse.model_json_schema()
STAGE1_JSON_SCHEMA = Stage1Response.model_json_schema()
STAGE2_JSON_SCHEMA = Stage2Response.model_json_schema()


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
GEMINI_STAGE1_JSON_SCHEMA = _without_stateful_constraints(STAGE1_JSON_SCHEMA)
GEMINI_STAGE2_JSON_SCHEMA = _without_stateful_constraints(STAGE2_JSON_SCHEMA)

