"""The in-app AI assistant: a Pydantic AI agent over Cookmarks' own search and lists.

`build_agent` maps the provider configured in `Config` onto a Pydantic AI model, so the
assistant follows the same provider/key/model-override rules as every other AI task. The
tools are thin wrappers over the query internals the API endpoints already use, scoped to
the calling account through `AssistantDeps`.

The tools are async and share the caller's session rather than opening their own: an async
tool that never awaits runs to completion on the event loop, so two tools can't interleave
on one Session.
"""

import uuid
from dataclasses import dataclass

from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.providers.anthropic import AnthropicProvider as PydanticAnthropicProvider
from pydantic_ai.providers.google import GoogleProvider as PydanticGoogleProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider as PydanticOpenRouterProvider
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.api.lists import get_or_create_favourites
from app.api.recipes import _search_conditions, _search_order
from app.models.book import Book
from app.models.recipe import Recipe
from app.models.recipe_list import RecipeList, RecipeListItem
from app.services import embeddings
from app.services.ai.anthropic import AnthropicProvider
from app.services.ai.base import AIProvider, ModelRole
from app.services.ai.gemini import GeminiProvider
from app.services.ai.openrouter import OpenRouterProvider
from app.services.ai.registry import get_ai_provider
from app.services.ai.stub import StubProvider
from app.services.prompts import ASSISTANT_SYSTEM_PROMPT

# Ceiling on rows any one tool call returns — the model searches many times, so each
# result set stays small enough to keep the context affordable.
MAX_RESULTS = 20


@dataclass
class AssistantDeps:
    """What every tool needs: the request's session and the account to act as."""

    session: Session
    user_id: uuid.UUID


def _recipe_row(recipe: Recipe, book: Book) -> dict:
    # `book_id` rides along on every row: without it the model has no real id to link a
    # book by, and it will cheerfully invent one out of the recipe's.
    return {
        "id": str(recipe.id),
        "name": recipe.name,
        "book": book.title,
        "book_id": str(book.id),
        "author": book.author,
        "keywords": sorted(k.name for k in recipe.keywords),
    }


def _clamp(limit: int) -> int:
    return max(1, min(limit, MAX_RESULTS))


async def search_recipes(ctx: RunContext[AssistantDeps], query: str, limit: int = 10) -> list[dict]:
    """Search the recipe library by keyword. Matches words in the recipe name, its book's
    title and author, its keywords and its ingredients; every word must match somewhere.
    Best for a named dish, an ingredient, or a cuisine."""
    query = query.strip()
    if not query:
        return []
    rows = ctx.deps.session.execute(
        select(Recipe, Book)
        .join(Book, Recipe.book_id == Book.id)
        .where(*_search_conditions(query, [], None, None))
        .order_by(*_search_order(query, "relevance", 0), Recipe.id)
        .limit(_clamp(limit))
        .options(selectinload(Recipe.keywords))
    ).all()
    return [_recipe_row(recipe, book) for recipe, book in rows]


async def semantic_search_recipes(
    ctx: RunContext[AssistantDeps], query: str, limit: int = 10
) -> list[dict]:
    """Search the recipe library by meaning rather than by word. Best for a description of
    what the cook fancies ("something warming with lentils") where the words themselves may
    not appear in any recipe. Returns an empty list if the library has no embeddings."""
    session = ctx.deps.session
    query = query.strip()
    if not query:
        return []
    matches = embeddings.search(session, query, _clamp(limit))
    if not matches:
        return []
    ids = [recipe_id for recipe_id, _ in matches]
    rows = session.execute(
        select(Recipe, Book)
        .join(Book, Recipe.book_id == Book.id)
        .where(Recipe.id.in_(ids))
        .options(selectinload(Recipe.keywords))
    ).all()
    by_id = {recipe.id: (recipe, book) for recipe, book in rows}
    return [_recipe_row(*by_id[rid]) for rid in ids if rid in by_id]


async def get_recipe(ctx: RunContext[AssistantDeps], recipe_id: str) -> dict:
    """Fetch one recipe in full — its ingredients and its method. Read this before advising
    on how a recipe works, how to scale it, or what to substitute in it."""
    recipe = _recipe(ctx.deps.session, recipe_id)
    if recipe is None:
        return {"error": "no recipe with that id"}
    return {
        **_recipe_row(recipe, recipe.book),
        "description": recipe.description,
        "yields": recipe.yields,
        "ingredients": list(recipe.ingredients),
        "instructions": list(recipe.instructions),
    }


async def list_books(ctx: RunContext[AssistantDeps]) -> list[dict]:
    """Every cookbook in the library, with how many recipes each has. The library holds a
    couple of hundred books, so this is the whole catalogue — there is no book search."""
    rows = ctx.deps.session.execute(
        select(Book, func.count(Recipe.id))
        .outerjoin(Recipe, Recipe.book_id == Book.id)
        .group_by(Book.id)
        .order_by(Book.title)
        .options(selectinload(Book.keywords))
    ).all()
    return [
        {
            "id": str(book.id),
            "title": book.title,
            "author": book.author,
            "keywords": sorted(k.name for k in book.keywords),
            "recipe_count": count,
        }
        for book, count in rows
    ]


async def get_book(ctx: RunContext[AssistantDeps], book_id: str) -> dict:
    """One cookbook with its full recipe index, in the book's own order."""
    session = ctx.deps.session
    book = session.get(Book, _as_uuid(book_id)) if _as_uuid(book_id) else None
    if book is None:
        return {"error": "no book with that id"}
    rows = session.execute(
        select(Recipe.id, Recipe.name).where(Recipe.book_id == book.id).order_by(Recipe.order)
    ).all()
    return {
        "id": str(book.id),
        "title": book.title,
        "author": book.author,
        "description": book.description,
        "keywords": sorted(k.name for k in book.keywords),
        "recipes": [{"id": str(rid), "name": name} for rid, name in rows],
    }


async def list_lists(ctx: RunContext[AssistantDeps]) -> list[dict]:
    """The cook's own recipe lists, including the default Favourites."""
    session = ctx.deps.session
    get_or_create_favourites(session, ctx.deps.user_id)
    counts = (
        select(RecipeListItem.recipe_list_id, func.count().label("n"))
        .group_by(RecipeListItem.recipe_list_id)
        .subquery()
    )
    rows = session.execute(
        select(RecipeList, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.recipe_list_id == RecipeList.id)
        .where(RecipeList.user_id == ctx.deps.user_id)
        .order_by(RecipeList.is_default.desc(), func.lower(RecipeList.name))
    ).all()
    return [
        {
            "id": str(lst.id),
            "name": lst.name,
            "is_favourites": lst.is_default,
            "recipe_count": count,
        }
        for lst, count in rows
    ]


async def create_list(ctx: RunContext[AssistantDeps], name: str) -> dict:
    """Create a new named recipe list for the cook."""
    name = name.strip()
    if not name:
        return {"error": "a list needs a name"}
    session = ctx.deps.session
    lst = RecipeList(name=name, is_default=False, user_id=ctx.deps.user_id)
    session.add(lst)
    session.commit()
    return {"id": str(lst.id), "name": lst.name, "recipe_count": 0}


async def add_recipes_to_list(
    ctx: RunContext[AssistantDeps], list_id: str, recipe_ids: list[str]
) -> dict:
    """Add one or more recipes to one of the cook's lists. Adding a recipe already in the
    list changes nothing."""
    session = ctx.deps.session
    lst = _owned_list(session, list_id, ctx.deps.user_id)
    if lst is None:
        return {"error": "no list with that id"}
    ids = _known_recipe_ids(session, recipe_ids)
    existing = set(
        session.scalars(
            select(RecipeListItem.recipe_id).where(
                RecipeListItem.recipe_list_id == lst.id, RecipeListItem.recipe_id.in_(ids)
            )
        ).all()
    )
    added = ids - existing
    session.add_all(RecipeListItem(recipe_list_id=lst.id, recipe_id=rid) for rid in added)
    session.commit()
    return {"list": lst.name, "added": len(added), "recipe_count": _list_size(session, lst.id)}


async def remove_recipes_from_list(
    ctx: RunContext[AssistantDeps], list_id: str, recipe_ids: list[str]
) -> dict:
    """Remove one or more recipes from one of the cook's lists."""
    session = ctx.deps.session
    lst = _owned_list(session, list_id, ctx.deps.user_id)
    if lst is None:
        return {"error": "no list with that id"}
    ids = _known_recipe_ids(session, recipe_ids)
    members = session.scalars(
        select(RecipeListItem.recipe_id).where(
            RecipeListItem.recipe_list_id == lst.id, RecipeListItem.recipe_id.in_(ids)
        )
    ).all()
    session.execute(
        delete(RecipeListItem).where(
            RecipeListItem.recipe_list_id == lst.id, RecipeListItem.recipe_id.in_(members)
        )
    )
    session.commit()
    return {
        "list": lst.name,
        "removed": len(members),
        "recipe_count": _list_size(session, lst.id),
    }


async def set_favourite(
    ctx: RunContext[AssistantDeps], recipe_id: str, favourite: bool
) -> dict:
    """Star or unstar a recipe — its membership of the cook's default Favourites list."""
    session = ctx.deps.session
    recipe = _recipe(session, recipe_id)
    if recipe is None:
        return {"error": "no recipe with that id"}
    favourites = get_or_create_favourites(session, ctx.deps.user_id)
    item = session.scalar(
        select(RecipeListItem).where(
            RecipeListItem.recipe_list_id == favourites.id,
            RecipeListItem.recipe_id == recipe.id,
        )
    )
    if favourite and item is None:
        session.add(RecipeListItem(recipe_list_id=favourites.id, recipe_id=recipe.id))
    elif not favourite and item is not None:
        session.delete(item)
    session.commit()
    return {"recipe": recipe.name, "is_favourite": favourite}


TOOLS = [
    search_recipes,
    semantic_search_recipes,
    get_recipe,
    list_books,
    get_book,
    list_lists,
    create_list,
    add_recipes_to_list,
    remove_recipes_from_list,
    set_favourite,
]


def _as_uuid(value: str) -> uuid.UUID | None:
    """A model can hand back anything as an id; a malformed one is a miss, not a crash."""
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        return None


def _recipe(session: Session, recipe_id: str) -> Recipe | None:
    parsed = _as_uuid(recipe_id)
    if parsed is None:
        return None
    return session.scalar(
        select(Recipe)
        .where(Recipe.id == parsed)
        .options(selectinload(Recipe.keywords), selectinload(Recipe.book))
    )


def _owned_list(session: Session, list_id: str, user_id: uuid.UUID) -> RecipeList | None:
    parsed = _as_uuid(list_id)
    if parsed is None:
        return None
    return session.scalar(
        select(RecipeList).where(RecipeList.id == parsed, RecipeList.user_id == user_id)
    )


def _known_recipe_ids(session: Session, recipe_ids: list[str]) -> set[uuid.UUID]:
    parsed = {u for u in (_as_uuid(rid) for rid in recipe_ids) if u is not None}
    if not parsed:
        return set()
    return set(session.scalars(select(Recipe.id).where(Recipe.id.in_(parsed))).all())


def _list_size(session: Session, list_id: uuid.UUID) -> int:
    return session.scalar(
        select(func.count()).where(RecipeListItem.recipe_list_id == list_id)
    ) or 0


def _model(provider: AIProvider) -> Model | None:
    """The Pydantic AI model for the configured provider's assistant role."""
    name = provider.model_for(ModelRole.ASSISTANT)
    if provider.name == AnthropicProvider.name:
        return AnthropicModel(name, provider=PydanticAnthropicProvider(api_key=provider.api_key))
    if provider.name == GeminiProvider.name:
        return GoogleModel(name, provider=PydanticGoogleProvider(api_key=provider.api_key))
    if provider.name == OpenRouterProvider.name:
        return OpenAIChatModel(
            name, provider=PydanticOpenRouterProvider(api_key=provider.api_key)
        )
    if provider.name == StubProvider.name:
        # Offline: exercises the whole tool-calling path without a network or a key.
        # Read-only — a stub must never mutate the cook's lists.
        return TestModel(call_tools=["search_recipes"])
    return None


def build_agent(session: Session) -> Agent[AssistantDeps, str] | None:
    """The assistant agent for the configured provider, or None when none is usable —
    same rules as `get_ai_provider`, plus the providers this has no Pydantic AI model for."""
    provider = get_ai_provider(session)
    if provider is None:
        return None
    model = _model(provider)
    if model is None:
        return None
    return Agent(
        model,
        deps_type=AssistantDeps,
        instructions=ASSISTANT_SYSTEM_PROMPT,
        tools=TOOLS,
    )
