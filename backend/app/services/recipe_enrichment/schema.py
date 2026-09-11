"""Versioned wire contract for one enrichment completion."""

import re
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "v10"
PROMPT_VERSION = "v47"
TAXONOMY_VERSION = "v1"

SUMMARY_MIN_WORDS = 3
SUMMARY_MAX_WORDS = 12
_SUMMARY_FORBIDDEN_TERMS = (
    "spiced",
    "ground",
    "coated",
    "with spices",
    "until tender",
    "rich",
    "deep",
    "complex",
    "classic",
    "fresh",
    "crisp",
    "creamy",
    "fragrant",
    "vibrant",
    "delicate",
    "luscious",
    "aromatic",
    "warming",
    "luxurious",
    "silky",
    "tender",
    "golden",
    "finished",
)


def summary_style_error(summary: str) -> str | None:
    """Return the descriptor-style violation, if the summary is not suitably terse."""
    words = summary.split()
    if not SUMMARY_MIN_WORDS <= len(words) <= SUMMARY_MAX_WORDS:
        return f"summary must contain {SUMMARY_MIN_WORDS} to {SUMMARY_MAX_WORDS} words"
    if summary.casefold().startswith(("a ", "an ")):
        return "summary must not start with an article"
    if summary.endswith((".", "!", "?")):
        return "summary must be a fragment without terminal punctuation"

    lowered = summary.casefold()
    for term in _SUMMARY_FORBIDDEN_TERMS:
        if re.search(rf"(?<!\\w){re.escape(term)}(?!\\w)", lowered):
            return f"summary contains decorative or forbidden term: {term}"
    return None

_EN_GB_INGREDIENT_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bchil[ei]s?\b", re.IGNORECASE), "chilli"),
    (re.compile(r"\bcilantro\b", re.IGNORECASE), "coriander"),
    (re.compile(r"\beggplants?\b", re.IGNORECASE), "aubergine"),
    (re.compile(r"\bzucchinis?\b", re.IGNORECASE), "courgette"),
    (re.compile(r"\b(scallions?|green onions?)\b", re.IGNORECASE), "spring onion"),
]

_EXCLUDED_SEASONING_PATTERN: re.Pattern[str] = re.compile(
    r"^(?:(?:sea|kosher|table|flaked?|coarse|fine|maldon|rock|cooking|iodi[sz]ed|himalayan|pink)\s+)*salt$"
    r"|^fleur\s+de\s+sel$"
    r"|^(?:(?:ground|cracked|freshly ground|coarse|whole)\s+)*(?:black\s+|white\s+)?pepper(?:corn)?$"
    r"|^(?:(?:sea|kosher|table|flaked?|coarse|fine|maldon|rock|cooking|iodi[sz]ed|himalayan|pink)\s+)*salt\s+and\s+(?:(?:ground|cracked|freshly ground|coarse|whole)\s+)*(?:black\s+|white\s+)?pepper(?:corn)?$"
    r"|^(?:(?:ground|cracked|freshly ground|coarse|whole)\s+)*(?:black\s+|white\s+)?pepper(?:corn)?\s+and\s+(?:(?:sea|kosher|table|flaked?|coarse|fine|maldon|rock|cooking|iodi[sz]ed|himalayan|pink)\s+)*salt$",
    re.IGNORECASE,
)


def is_excluded_seasoning(name: str) -> bool:
    """Return True for universal seasonings (salt, black/white pepper) that should not be extracted."""
    return bool(_EXCLUDED_SEASONING_PATTERN.match(name.strip()))


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
    "argentina": "argentine",
    "argentinian": "argentine",
    "armenia": "armenian",
    "australia": "australian",
    "austria": "austrian",
    "bangladesh": "bengali",
    "bangladeshi": "bengali",
    "belgium": "belgian",
    "brazil": "brazilian",
    "britain": "british",
    "great britain": "british",
    "uk": "british",
    "united kingdom": "british",
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
    "nepal": "nepali",
    "nepalese": "nepali",
    "nigeria": "nigerian",
    "norway": "norwegian",
    "pakistan": "pakistani",
    "palestine": "palestinian",
    "peru": "peruvian",
    "poland": "polish",
    "portugal": "portuguese",
    "romania": "romanian",
    "russia": "russian",
    "saudi arabia": "arabian-peninsula",
    "saudi": "arabian-peninsula",
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


def normalize_method_decisions(methods: Sequence[Any]) -> list[Any]:
    seen: set[str] = set()
    cleaned: list[Any] = []
    has_primary = False
    for item in methods:
        vid = None
        is_p = False
        if isinstance(item, Mapping):
            vid = item.get("v") or item.get("value_id")
            is_p = bool(item.get("p") or item.get("is_primary"))
        elif hasattr(item, "value_id") and hasattr(item, "is_primary"):
            vid = item.value_id
            is_p = bool(item.is_primary)
        if vid is not None:
            s_vid = str(vid).strip().lower()
            if s_vid and s_vid not in seen:
                seen.add(s_vid)
                clean_p = is_p and not has_primary
                if clean_p:
                    has_primary = True
                if isinstance(item, Mapping):
                    clean_dict = dict(item)
                    if "v" in clean_dict:
                        clean_dict["v"] = s_vid
                    elif "value_id" in clean_dict:
                        clean_dict["value_id"] = s_vid
                    clean_dict["p"] = clean_p
                    clean_dict.pop("is_primary", None)
                    cleaned.append(clean_dict)
                else:
                    cleaned.append(MethodDecision(v=s_vid, p=clean_p))
        else:
            cleaned.append(item)
    return cleaned


def normalize_course_ids(courses: Sequence[Any]) -> list[Any]:
    seen: set[str] = set()
    cleaned: list[Any] = []
    for item in courses:
        if isinstance(item, str):
            s = item.strip().lower()
            if s and s not in seen:
                seen.add(s)
                cleaned.append(s)
        else:
            cleaned.append(item)
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
        cleaned = normalize_ingredient_name(text)
        if is_excluded_seasoning(cleaned):
            return None
        return cleaned


class Stage1Response(EnrichmentDecision):
    """Stage 1 extracts singular UK-English canonical ingredient names per line."""

    ingredients: list[Stage1LineDecision] = Field(default_factory=list, max_length=200, alias="i")


class MethodDecision(EnrichmentDecision):
    value_id: str = Field(alias="v")
    is_primary: bool = Field(default=False, alias="p")


class Stage2Response(EnrichmentDecision):
    key_ingredients: list[str] = Field(
        default_factory=list,
        max_length=3,
        alias="k",
        description="1 to 3 key distinguishing ingredients chosen strictly from the supplied ingredients list. Never return more than 3.",
    )
    cuisines: list[str] = Field(default_factory=list, max_length=10, alias="c")
    methods: list[MethodDecision] = Field(default_factory=list, max_length=10, alias="m")
    courses: list[str] = Field(default_factory=list, max_length=10, alias="o")
    keywords: list[str] = Field(default_factory=list, max_length=100, alias="w")
    alternate_name: str | None = Field(
        default=None,
        alias="a",
        description="Title Case UK-English literal translation only when a native-language title directly describes the food, ingredients, or form and its translation makes the dish self-descriptive (e.g. 'Bharli Mirchi' -> 'Stuffed Chillies', 'Mouna Au Lait' -> 'Milk Bread'). Set null for a named cultural dish, opaque traditional name, loanword, self-descriptive English title, or a generic translation such as 'Pomodori Fritti' -> 'Fried Tomatoes'. Do not translate a named dish word by word; it needs summary (s) instead.",
    )
    summary: str | None = Field(
        default=None,
        alias="s",
        description="3-12 word food-first descriptor for a named cultural dish, opaque traditional name, loanword, regional style, glaze/sauce style, or noodle dish (e.g. 'Bhel Puri' -> 'Puffed rice with tamarind chutney', 'Gazpacho' -> 'Chilled tomato and pepper soup'). Must be null for literal native-language translations and self-descriptive English titles. Never start with 'A' or 'An'. Do not use decorative language, cooking-process detail, or forbidden words including 'spiced', 'rich', 'deep', 'complex', 'crisp', 'creamy', 'fragrant', 'vibrant', 'golden', 'ground', 'coated', 'with spices', or 'until tender'.",
    )

    @field_validator("alternate_name", mode="before")
    @classmethod
    def normalize_alternate_name(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text if text else None

    @field_validator("summary", mode="before")
    @classmethod
    def normalize_summary(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        if error := summary_style_error(text):
            raise ValueError(error)
        return text

    @field_validator("key_ingredients", mode="before")
    @classmethod
    def normalize_key_ingredients(cls, value: object) -> list[str]:
        if isinstance(value, list):
            return [
                cleaned
                for item in value
                if (cleaned := normalize_ingredient_name(str(item).strip()))
                and not is_excluded_seasoning(cleaned)
            ]
        return []

    @field_validator("cuisines", mode="before")
    @classmethod
    def normalize_cuisines(cls, value: object) -> list[str]:
        if isinstance(value, list):
            return normalize_cuisine_ids([str(item) for item in value])
        return []

    @field_validator("methods", mode="before")
    @classmethod
    def normalize_methods(cls, value: object) -> list[object]:
        if isinstance(value, list):
            return normalize_method_decisions(value)
        return []

    @field_validator("courses", mode="before")
    @classmethod
    def normalize_courses(cls, value: object) -> list[object]:
        if isinstance(value, list):
            return normalize_course_ids(value)
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
        cleaned = normalize_ingredient_name(text)
        if is_excluded_seasoning(cleaned):
            return None
        return cleaned


class EnrichmentResponse(EnrichmentDecision):
    ingredients: list[RecipeIngredientDecision] = Field(
        default_factory=list, max_length=200, alias="i"
    )
    cuisines: list[str] = Field(default_factory=list, max_length=10, alias="c")
    methods: list[MethodDecision] = Field(default_factory=list, max_length=10, alias="m")
    courses: list[str] = Field(default_factory=list, max_length=10, alias="o")
    keywords: list[str] = Field(default_factory=list, max_length=100, alias="w")
    alternate_name: str | None = Field(
        default=None,
        alias="a",
        description="Title Case UK-English literal translation only when a native-language title directly describes the food, ingredients, or form and its translation makes the dish self-descriptive (e.g. 'Bharli Mirchi' -> 'Stuffed Chillies', 'Mouna Au Lait' -> 'Milk Bread'). Set null for a named cultural dish, opaque traditional name, loanword, self-descriptive English title, or a generic translation such as 'Pomodori Fritti' -> 'Fried Tomatoes'. Do not translate a named dish word by word; it needs summary (s) instead.",
    )
    summary: str | None = Field(
        default=None,
        alias="s",
        description="3-12 word food-first descriptor for a named cultural dish, opaque traditional name, loanword, regional style, glaze/sauce style, or noodle dish (e.g. 'Bhel Puri' -> 'Puffed rice with tamarind chutney', 'Gazpacho' -> 'Chilled tomato and pepper soup'). Must be null for literal native-language translations and self-descriptive English titles. Never start with 'A' or 'An'. Do not use decorative language, cooking-process detail, or forbidden words including 'spiced', 'rich', 'deep', 'complex', 'crisp', 'creamy', 'fragrant', 'vibrant', 'golden', 'ground', 'coated', 'with spices', or 'until tender'.",
    )

    @field_validator("alternate_name", mode="before")
    @classmethod
    def normalize_alternate_name(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text if text else None

    @field_validator("summary", mode="before")
    @classmethod
    def normalize_summary(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        if error := summary_style_error(text):
            raise ValueError(error)
        return text

    @property
    def canonical_ingredients(self) -> list[RecipeIngredientDecision]:
        return [item for item in self.ingredients if item.name]

    @field_validator("cuisines", mode="before")
    @classmethod
    def normalize_cuisines(cls, value: object) -> list[str]:
        if isinstance(value, list):
            return normalize_cuisine_ids([str(item) for item in value])
        return []

    @field_validator("methods", mode="before")
    @classmethod
    def normalize_methods(cls, value: object) -> list[object]:
        if isinstance(value, list):
            return normalize_method_decisions(value)
        return []

    @field_validator("courses", mode="before")
    @classmethod
    def normalize_courses(cls, value: object) -> list[object]:
        if isinstance(value, list):
            return normalize_course_ids(value)
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
            a=stage2.alternate_name,
            s=stage2.summary,
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
