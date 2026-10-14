"""Validated rules shared by recipe search and its navigation context."""

import uuid
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FilterField = Literal[
    "name",
    "alternate_name",
    "summary",
    "description",
    "ingredients",
    "instructions",
    "keyword",
    "cuisine_region",
    "course",
    "key_ingredient",
    "method",
    "dish_type",
    "book",
    "author",
    "favourite",
    "list",
    "has_image",
]
FilterOperator = Literal[
    "eq",
    "neq",
    "contains",
    "not_contains",
    "starts_with",
    "ends_with",
    "is_empty",
    "is_not_empty",
    "in_list",
    "not_in_list",
]
TEXT_OPERATORS = {
    "eq",
    "neq",
    "contains",
    "not_contains",
    "starts_with",
    "ends_with",
    "is_empty",
    "is_not_empty",
}


class RecipeFilterRule(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    field: FilterField
    operator: FilterOperator
    value: str | bool | None = None

    @model_validator(mode="after")
    def validate_rule(self) -> Self:
        if self.field in {"favourite", "has_image"}:
            if self.operator != "eq" or not isinstance(self.value, bool):
                raise ValueError("This field needs equals and a yes/no value")
            return self
        allowed = (
            {"in_list", "not_in_list"}
            if self.field == "list"
            else TEXT_OPERATORS - {"is_empty", "is_not_empty"}
            if self.field == "book"
            else TEXT_OPERATORS
        )
        if self.operator not in allowed:
            raise ValueError("Operator is not supported for this field")
        if self.operator in {"is_empty", "is_not_empty"}:
            if self.value is not None:
                raise ValueError("Empty checks do not take a value")
            return self
        if not isinstance(self.value, str) or not self.value.strip() or len(self.value) > 500:
            raise ValueError("Enter text between 1 and 500 characters")
        self.value = self.value.strip()
        if self.field == "list" or (self.field == "book" and self.operator in {"eq", "neq"}):
            try:
                self.value = str(uuid.UUID(self.value))
            except ValueError as error:
                raise ValueError("Select a valid book or list") from error
        return self


class RecipeFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[1]
    match: Literal["all", "any"]
    rules: list[RecipeFilterRule] = Field(max_length=20)

    @field_validator("version", mode="before")
    @classmethod
    def validate_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Filter version must be the integer 1")
        return value
