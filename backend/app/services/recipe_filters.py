"""SQL predicates for advanced recipe filters, without duplicating recipe rows."""

import uuid
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import and_, exists, false, func, or_, select, true
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.models.book import Book
from app.models.enums import KeywordCategory
from app.models.ingredient import RecipeIngredient
from app.models.recipe import Keyword, Recipe, recipe_keywords
from app.models.recipe_list import RecipeList, RecipeListItem
from app.schemas.recipe_filters import RecipeFilterRule, RecipeFilters


def parse_filters(raw: str | None) -> RecipeFilters | None:
    if raw is None:
        return None
    try:
        return RecipeFilters.model_validate_json(raw)
    except ValidationError as error:
        raise HTTPException(
            status_code=422, detail="Invalid advanced filters: " + str(error)
        ) from error


def _text_match(column: Any, rule: RecipeFilterRule) -> ColumnElement[bool]:
    # The connection's Unicode casefold function also handles non-ASCII keywords.
    column = func.cookmarks_casefold(func.coalesce(column, ""))
    value = str(rule.value).casefold()
    if rule.operator in {"is_empty", "is_not_empty"}:
        return func.trim(column) != ""
    if rule.operator in {"eq", "neq"}:
        return and_(func.trim(column) != "", column == value)
    if rule.operator in {"contains", "not_contains"}:
        return column.contains(value, autoescape=True)
    if rule.operator == "starts_with":
        return column.startswith(value, autoescape=True)
    return column.endswith(value, autoescape=True)


def _rule_condition(session: Session, user_id: uuid.UUID, rule: RecipeFilterRule):
    negative = rule.operator in {"neq", "not_contains", "is_empty", "not_in_list"}
    field = rule.field
    if field in {"list", "favourite"}:
        lists = select(RecipeList.id).where(RecipeList.user_id == user_id)
        if field == "list":
            list_id = uuid.UUID(str(rule.value))
            lists = lists.where(RecipeList.id == list_id)
            if session.scalar(lists) is None:
                raise HTTPException(status_code=404, detail="list not found")
        else:
            lists = lists.where(RecipeList.is_default.is_(True))
            negative = rule.value is False
        matched = Recipe.id.in_(
            select(RecipeListItem.recipe_id).where(RecipeListItem.recipe_list_id.in_(lists))
        )
    elif field == "has_image":
        matched = and_(Recipe.image.is_not(None), func.trim(Recipe.image) != "")
        negative = rule.value is False
    elif field == "book" and rule.operator in {"eq", "neq"}:
        matched = Recipe.book_id == uuid.UUID(str(rule.value))
    elif field == "ingredients":
        matched = Recipe.id.in_(
            select(RecipeIngredient.recipe_id).where(_text_match(RecipeIngredient.text, rule))
        )
    elif field == "instructions":
        steps = func.json_each(Recipe.instructions).table_valued("value", joins_implicitly=True)
        matched = exists(select(1).select_from(steps).where(_text_match(steps.c.value, rule)))
    elif field == "keyword" or field in {category.value for category in KeywordCategory}:
        keywords = select(Keyword.id).where(_text_match(Keyword.name, rule))
        if field != "keyword":
            keywords = keywords.where(Keyword.category == KeywordCategory(field))
        matched = Recipe.id.in_(
            select(recipe_keywords.c.recipe_id).where(recipe_keywords.c.keyword_id.in_(keywords))
        )
    else:
        column = (
            Book.title
            if field == "book"
            else Book.author
            if field == "author"
            else getattr(Recipe, field)
        )
        matched = _text_match(column, rule)
    return ~matched if negative else matched


def advanced_condition(session: Session, user_id: uuid.UUID, filters: RecipeFilters | None):
    if filters is None or not filters.rules:
        return true()
    conditions = [_rule_condition(session, user_id, rule) for rule in filters.rules]
    return and_(*conditions) if filters.match == "all" else or_(false(), *conditions)
