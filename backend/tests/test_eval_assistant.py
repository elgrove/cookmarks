"""The assistant eval's scoring: pure checks over a transcript, no network, no DB."""

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)

from evals.assistant import (
    PromptSpec,
    Transcript,
    check_prompt,
    linked_ids,
    load_assistant_config,
    read_transcript,
    score,
)

RECIPE = "1c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e5f"
BOOK = "2b3c4d5e-6f7a-4b8c-9d0e-1f2a3b4c5d6e"
INVENTED = "99999999-9999-4999-8999-999999999999"


def _spec(
    expect_tools: list[str] | None = None,
    min_searches: int = 0,
    min_recipe_links: int = 0,
    must_mention: list[str] | None = None,
) -> PromptSpec:
    return PromptSpec(
        id="t",
        prompt="p",
        expect_tools=expect_tools or [],
        min_searches=min_searches,
        min_recipe_links=min_recipe_links,
        must_mention=must_mention or [],
    )


def _transcript(answer: str, tools: list[str], ids: set[str]) -> Transcript:
    return Transcript(
        answer=answer, tool_calls=[(name, {}) for name in tools], returned_ids=ids
    )


def test_reads_tool_calls_and_returned_ids_off_a_run() -> None:
    messages = [
        ModelResponse(parts=[ToolCallPart("search_recipes", {"query": "lentil"})]),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="search_recipes",
                    content=[{"id": RECIPE, "name": "Soup", "book_id": BOOK}],
                    tool_call_id="c1",
                )
            ]
        ),
        ModelResponse(parts=[TextPart("done")]),
    ]
    transcript = read_transcript(messages, "done")
    assert transcript.tool_names == ["search_recipes"]
    assert transcript.tool_calls[0][1] == {"query": "lentil"}
    assert transcript.returned_ids == {RECIPE, BOOK}


def test_finds_app_links_in_an_answer() -> None:
    answer = f"Try [Soup](/recipes/{RECIPE}) from [A Book](/books/{BOOK})."
    assert linked_ids(answer) == [("recipes", RECIPE), ("books", BOOK)]


def test_a_link_to_an_id_no_tool_returned_fails_grounding() -> None:
    transcript = _transcript(f"[Soup](/recipes/{INVENTED})", ["search_recipes"], {RECIPE})
    grounded = next(c for c in check_prompt(_spec(), transcript) if c.name == "grounded")
    assert not grounded.passed
    assert INVENTED in grounded.detail


def test_grounding_passes_when_every_link_came_from_a_tool() -> None:
    transcript = _transcript(f"[Soup](/recipes/{RECIPE})", ["search_recipes"], {RECIPE, BOOK})
    assert all(c.passed for c in check_prompt(_spec(), transcript))


def test_an_answer_with_no_links_is_grounded() -> None:
    """Nothing claimed is nothing to invent — a plain 'I found nothing' must score well."""
    transcript = _transcript("Your library has nothing like that.", ["search_recipes"], set())
    assert all(c.passed for c in check_prompt(_spec(), transcript))


def test_expected_tools_and_search_count_are_checked() -> None:
    spec = _spec(expect_tools=["get_recipe"], min_searches=2)
    transcript = _transcript("no links", ["search_recipes"], set())
    failed = {c.name for c in check_prompt(spec, transcript) if not c.passed}
    assert failed == {"calls:get_recipe", "searches>=2"}


def test_semantic_search_counts_towards_the_search_minimum() -> None:
    spec = _spec(min_searches=2)
    transcript = _transcript("", ["search_recipes", "semantic_search_recipes"], set())
    assert all(c.passed for c in check_prompt(spec, transcript))


def test_recipe_links_are_counted_distinctly_and_books_do_not_count() -> None:
    spec = _spec(min_recipe_links=2)
    answer = f"[a](/recipes/{RECIPE}) [again](/recipes/{RECIPE}) [book](/books/{BOOK})"
    transcript = _transcript(answer, [], {RECIPE, BOOK})
    links = next(c for c in check_prompt(spec, transcript) if c.name.startswith("links"))
    assert not links.passed
    assert links.detail == "1"


def test_must_mention_is_case_insensitive() -> None:
    spec = _spec(must_mention=["Tamarind"])
    transcript = _transcript("Use lime juice instead of TAMARIND.", [], set())
    assert all(c.passed for c in check_prompt(spec, transcript))


def test_score_is_the_fraction_of_checks_passed() -> None:
    spec = _spec(expect_tools=["get_recipe", "list_books"])
    transcript = _transcript("", ["get_recipe"], set())
    checks = check_prompt(spec, transcript)
    assert len(checks) == 3
    assert score(checks) == 2 / 3


def test_the_shipped_config_parses() -> None:
    models, prompts = load_assistant_config()
    assert models and prompts
    assert {p.id for p in prompts} == {"discovery", "substitution"}
    assert all(m.provider and m.model for m in models)
