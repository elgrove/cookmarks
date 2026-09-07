"""Versioned wire contract for one enrichment completion."""

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "v8"
PROMPT_VERSION = "v23"
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


class Stage1LineDecision(EnrichmentDecision):
    line_id: str = Field(alias="id")
    name: str | None = Field(default=None, alias="n")

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        return normalize_ingredient_name(text)


class Stage1Response(EnrichmentDecision):
    """Stage 1 extracts singular UK-English canonical ingredient names per line."""

    ingredients: list[Stage1LineDecision] = Field(default_factory=list, max_length=200, alias="i")


class MethodDecision(EnrichmentDecision):
    value_id: str = Field(alias="v")
    is_primary: bool = Field(default=False, alias="p")


class Stage2Response(EnrichmentDecision):
    key_ingredients: list[str] = Field(default_factory=list, max_length=3, alias="k")
    cuisines: list[str] = Field(default_factory=list, max_length=10, alias="c")
    methods: list[MethodDecision] = Field(default_factory=list, max_length=10, alias="m")
    courses: list[str] = Field(default_factory=list, max_length=10, alias="o")
    keywords: list[str] = Field(default_factory=list, max_length=5, alias="w")

    @field_validator("key_ingredients", mode="before")
    @classmethod
    def normalize_key_ingredients(cls, value: object) -> list[str]:
        if isinstance(value, list):
            return [normalize_ingredient_name(str(item).strip()) for item in value if str(item).strip()]
        return []

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


class RecipeIngredientDecision(EnrichmentDecision):
    line_id: str = Field(alias="id")
    name: str | None = Field(default=None, alias="n")
    is_key: bool = Field(default=False, alias="k")

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        return normalize_ingredient_name(text)


class EnrichmentResponse(EnrichmentDecision):
    ingredients: list[RecipeIngredientDecision] = Field(
        default_factory=list, max_length=200, alias="i"
    )
    cuisines: list[str] = Field(default_factory=list, max_length=10, alias="c")
    methods: list[MethodDecision] = Field(default_factory=list, max_length=10, alias="m")
    courses: list[str] = Field(default_factory=list, max_length=10, alias="o")
    keywords: list[str] = Field(default_factory=list, max_length=5, alias="w")

    @property
    def canonical_ingredients(self) -> list[RecipeIngredientDecision]:
        return [item for item in self.ingredients if item.name]

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
    def from_stages(
        cls, stage1: Stage1Response, stage2: Stage2Response
    ) -> "EnrichmentResponse":
        available = {
            item.name.casefold()
            for item in stage1.ingredients
            if item.name
        }
        selected = [k.casefold() for k in stage2.key_ingredients]
        if len(selected) != len(set(selected)):
            raise ValueError("Stage 2 contains duplicate key-ingredient selections")
        if available and not selected:
            raise ValueError("Stage 2 must select at least one key ingredient")
        if not set(selected) <= available:
            raise ValueError("Stage 2 refers to an unknown Stage 1 ingredient")
        key_folded = set(selected)
        ingredients: list[RecipeIngredientDecision] = []
        for line in stage1.ingredients:
            is_key = line.name is not None and line.name.casefold() in key_folded
            ingredients.append(
                RecipeIngredientDecision(
                    id=line.line_id,
                    n=line.name,
                    k=is_key,
                )
            )
        return cls(
            i=ingredients,
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


GEMINI_ENRICHMENT_JSON_SCHEMA = _without_stateful_constraints(ENRICHMENT_JSON_SCHEMA)
GEMINI_STAGE1_JSON_SCHEMA = _without_stateful_constraints(STAGE1_JSON_SCHEMA)
GEMINI_STAGE2_JSON_SCHEMA = _without_stateful_constraints(STAGE2_JSON_SCHEMA)

