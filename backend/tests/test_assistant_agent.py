"""The assistant agent: provider wiring and the domain tools.

The tools run against a scripted `FunctionModel`, so a whole tool-calling turn is
exercised without a network or an API key.
"""

import uuid
from collections.abc import Iterator

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Config, Recipe, RecipeList, RecipeListItem, User
from app.models.enums import AIProvider
from app.services.assistant import AssistantDeps, build_agent
from app.services.users import create_user


def _configure(session: Session, provider: AIProvider | None) -> None:
    config = session.get(Config, 1) or Config(id=1)
    config.assistant_provider = provider
    config.assistant_api_key = "k" if provider is AIProvider.GEMINI else None
    session.add(config)
    session.commit()


def _scripted(tool: str, args: dict) -> FunctionModel:
    """A model that calls `tool` once, then answers with whatever came back."""
    calls: list[str] = []

    def respond(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        if not calls:
            calls.append(tool)
            return ModelResponse(parts=[ToolCallPart(tool, args)])
        returned = messages[-1].parts[0]
        return ModelResponse(parts=[TextPart(str(getattr(returned, "content", "")))])

    return FunctionModel(respond)


@pytest.fixture
def deps(session: Session) -> AssistantDeps:
    user = session.scalar(select(User).where(User.username == "tester"))
    assert user is not None
    return AssistantDeps(session=session, user_id=user.id)


@pytest.fixture
def agent(session: Session) -> Iterator:
    _configure(session, AIProvider.STUB)
    built = build_agent(session)
    assert built is not None
    yield built


def _recipe(session: Session, name: str = "Recipe 0") -> Recipe:
    recipe = session.scalar(select(Recipe).where(Recipe.name == name))
    assert recipe is not None
    return recipe


def test_no_agent_without_a_provider(session: Session) -> None:
    _configure(session, None)
    assert build_agent(session) is None


def test_no_agent_when_the_key_is_missing(session: Session) -> None:
    config = session.get(Config, 1) or Config(id=1)
    config.assistant_provider = AIProvider.GEMINI
    config.assistant_api_key = None
    session.add(config)
    session.commit()
    assert build_agent(session) is None


def test_stub_provider_builds_an_agent(session: Session) -> None:
    _configure(session, AIProvider.STUB)
    assert build_agent(session) is not None


def test_search_tool_runs_end_to_end(agent, deps: AssistantDeps) -> None:
    result = agent.run_sync(
        "find me a pasta",
        deps=deps,
        model=_scripted("search_recipes", {"query": "pasta"}),
    )
    assert "Recipe 0" in result.output


def test_semantic_search_without_embeddings_is_empty(agent, deps: AssistantDeps) -> None:
    result = agent.run_sync(
        "something warming",
        deps=deps,
        model=_scripted("semantic_search_recipes", {"query": "warming"}),
    )
    assert result.output == "[]"


def test_get_recipe_returns_the_method(agent, deps: AssistantDeps) -> None:
    recipe = _recipe(deps.session)
    result = agent.run_sync(
        "how does it work",
        deps=deps,
        model=_scripted("get_recipe", {"recipe_id": str(recipe.id)}),
    )
    assert "Boil the pasta." in result.output


def test_get_recipe_rejects_a_bogus_id(agent, deps: AssistantDeps) -> None:
    result = agent.run_sync(
        "how does it work",
        deps=deps,
        model=_scripted("get_recipe", {"recipe_id": "not-a-uuid"}),
    )
    assert "no recipe with that id" in result.output


def test_list_books_returns_the_catalogue(agent, deps: AssistantDeps) -> None:
    result = agent.run_sync(
        "what have I got",
        deps=deps,
        model=_scripted("list_books", {}),
    )
    assert "With Recipes" in result.output


def test_create_list_and_add_recipes(agent, deps: AssistantDeps) -> None:
    session = deps.session
    agent.run_sync("make a list", deps=deps, model=_scripted("create_list", {"name": "Sunday"}))
    created = session.scalar(select(RecipeList).where(RecipeList.name == "Sunday"))
    assert created is not None and created.user_id == deps.user_id

    recipe = _recipe(session)
    agent.run_sync(
        "add it",
        deps=deps,
        model=_scripted(
            "add_recipes_to_list",
            {"list_id": str(created.id), "recipe_ids": [str(recipe.id)]},
        ),
    )
    assert _members(session, created.id) == [recipe.id]

    agent.run_sync(
        "take it out",
        deps=deps,
        model=_scripted(
            "remove_recipes_from_list",
            {"list_id": str(created.id), "recipe_ids": [str(recipe.id)]},
        ),
    )
    assert _members(session, created.id) == []


def test_set_favourite_toggles_the_star(agent, deps: AssistantDeps) -> None:
    session = deps.session
    recipe = _recipe(session)
    agent.run_sync(
        "star it",
        deps=deps,
        model=_scripted("set_favourite", {"recipe_id": str(recipe.id), "favourite": True}),
    )
    favourites = session.scalar(
        select(RecipeList).where(
            RecipeList.user_id == deps.user_id, RecipeList.is_default.is_(True)
        )
    )
    assert favourites is not None
    assert _members(session, favourites.id) == [recipe.id]

    agent.run_sync(
        "unstar it",
        deps=deps,
        model=_scripted("set_favourite", {"recipe_id": str(recipe.id), "favourite": False}),
    )
    assert _members(session, favourites.id) == []


def test_list_tools_are_scoped_to_the_caller(agent, session: Session) -> None:
    """Another account's list is invisible: the tool reports a miss, not their data."""
    owner = session.scalar(select(User).where(User.username == "tester"))
    assert owner is not None
    theirs = RecipeList(name="Private", is_default=False, user_id=owner.id)
    session.add(theirs)
    session.commit()

    intruder = create_user(session, "intruder", "password1")
    result = agent.run_sync(
        "add it",
        deps=AssistantDeps(session=session, user_id=intruder.id),
        model=_scripted(
            "add_recipes_to_list",
            {"list_id": str(theirs.id), "recipe_ids": [str(_recipe(session).id)]},
        ),
    )
    assert "no list with that id" in result.output
    assert _members(session, theirs.id) == []


def test_list_lists_only_shows_the_callers_lists(agent, session: Session) -> None:
    owner = session.scalar(select(User).where(User.username == "tester"))
    assert owner is not None
    session.add(RecipeList(name="Theirs", is_default=False, user_id=owner.id))
    session.commit()

    intruder = create_user(session, "intruder", "password1")
    result = agent.run_sync(
        "my lists",
        deps=AssistantDeps(session=session, user_id=intruder.id),
        model=_scripted("list_lists", {}),
    )
    assert "Theirs" not in result.output
    assert "Favourites" in result.output


def _members(session: Session, list_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        session.scalars(
            select(RecipeListItem.recipe_id).where(RecipeListItem.recipe_list_id == list_id)
        ).all()
    )


def test_user_instructions_reach_model_instructions(agent, session: Session) -> None:
    seen_prompts: list[str] = []

    def respond(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if info.instructions:
            seen_prompts.append(info.instructions)
        return ModelResponse(parts=[TextPart("Advice ready.")])

    user = session.scalar(select(User).where(User.username == "tester"))
    assert user is not None
    deps = AssistantDeps(
        session=session,
        user_id=user.id,
        user_instructions="Vegetarian only. Cooking with cast iron on induction.",
    )
    result = agent.run_sync("what to cook", deps=deps, model=FunctionModel(respond))
    assert result.output == "Advice ready."
    assert len(seen_prompts) == 1
    assert "Vegetarian only. Cooking with cast iron on induction." in seen_prompts[0]
    assert "User instructions for the user of this app:" in seen_prompts[0]


def test_no_user_instructions_uses_base_prompt(agent, session: Session) -> None:
    seen_prompts: list[str] = []

    def respond(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if info.instructions:
            seen_prompts.append(info.instructions)
        return ModelResponse(parts=[TextPart("Base advice.")])

    user = session.scalar(select(User).where(User.username == "tester"))
    assert user is not None
    deps = AssistantDeps(session=session, user_id=user.id, user_instructions=None)
    result = agent.run_sync("what to cook", deps=deps, model=FunctionModel(respond))
    assert result.output == "Base advice."
    assert len(seen_prompts) == 1
    assert "User instructions for the user of this app:" not in seen_prompts[0]


def test_user_instructions_change_response_and_do_not_cross_accounts(
    agent, session: Session
) -> None:
    user_a = create_user(session, "cook_a", "password123")
    user_b = create_user(session, "cook_b", "password456")

    def respond(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if info.instructions and "Nut allergy" in info.instructions:
            return ModelResponse(parts=[TextPart("Filtered out nuts.")])
        return ModelResponse(parts=[TextPart("Standard recommendation.")])

    deps_a = AssistantDeps(
        session=session,
        user_id=user_a.id,
        user_instructions="Nut allergy. Avoid peanuts and tree nuts.",
    )
    result_a = agent.run_sync("suggest dinner", deps=deps_a, model=FunctionModel(respond))
    assert result_a.output == "Filtered out nuts."

    deps_b = AssistantDeps(
        session=session,
        user_id=user_b.id,
        user_instructions=None,
    )
    result_b = agent.run_sync("suggest dinner", deps=deps_b, model=FunctionModel(respond))
    assert result_b.output == "Standard recommendation."

