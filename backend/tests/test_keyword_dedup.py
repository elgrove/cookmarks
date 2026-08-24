"""AI-assisted keyword dedup: the deterministic pre-pass, chain resolution, and the
apply step that reassigns associations across recipes and books and deletes the
merged-away keyword."""

import json
from typing import ClassVar

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.book import Book
from app.models.recipe import Keyword, Recipe
from app.services.ai import AIProvider, ModelRole, Usage
from app.services.keyword_dedup import (
    apply_merges,
    deduplicate_keywords,
    pre_deduplicate,
    propose_merges,
    select_candidates,
)


class _MapProvider(AIProvider):
    """A provider whose dedup step returns a fixed {duplicate -> canonical} map,
    regardless of input — lets the merge logic be tested without a network call."""

    name = "MAP"
    requires_api_key = False
    models: ClassVar[dict[ModelRole, str]] = {ModelRole.KEYWORD_DEDUP: "map"}

    def __init__(self, mapping: dict[str, str]) -> None:
        super().__init__("")
        self._mapping = mapping

    def _complete(
        self, prompt: str, model: str, *, schema: dict | None = None, temp: float = 0
    ) -> tuple[str, Usage]:
        return json.dumps(self._mapping), Usage()


class _RawProvider(AIProvider):
    """A provider whose dedup step returns a fixed raw string — lets a truncated or
    malformed reply be exercised exactly as the model would deliver it."""

    name = "RAW"
    requires_api_key = False
    models: ClassVar[dict[ModelRole, str]] = {ModelRole.KEYWORD_DEDUP: "raw"}

    def __init__(self, response: str) -> None:
        super().__init__("")
        self._response = response

    def _complete(
        self, prompt: str, model: str, *, schema: dict | None = None, temp: float = 0
    ) -> tuple[str, Usage]:
        return self._response, Usage()


def _recipe_zero(session: Session) -> Recipe:
    return session.scalars(select(Recipe).where(Recipe.name == "Recipe 0")).one()


def _with_recipes(session: Session) -> Book:
    return session.scalars(select(Book).where(Book.title == "With Recipes")).one()


# --- The deterministic pre-pass ------------------------------------------------------


def test_pre_deduplicate_folds_case_and_whitespace_without_restyling() -> None:
    # Most-used first: the kept spelling is the dominant one, NOT a title-cased form —
    # the pre-pass must never restyle a keyword, only fold genuine variants.
    survivors, merge_map = pre_deduplicate(["almond milk", "Almond Milk", "almond  milk"])

    assert survivors == ["almond milk"]
    assert merge_map == {"Almond Milk": "almond milk", "almond  milk": "almond milk"}


def test_pre_deduplicate_leaves_a_lone_keyword_untouched() -> None:
    # A single sentence-case keyword with no variant is left exactly as-is (the old
    # title-casing pre-pass would have rewritten this to "Almond Milk").
    survivors, merge_map = pre_deduplicate(["Almond milk"])

    assert survivors == ["Almond milk"]
    assert merge_map == {}


def test_pre_deduplicate_folds_plural_into_singular() -> None:
    survivors, merge_map = pre_deduplicate(["Egg", "Eggs"])

    assert survivors == ["Egg"]
    assert merge_map == {"Eggs": "Egg"}


def test_pre_deduplicate_leaves_distinct_terms_alone() -> None:
    survivors, merge_map = pre_deduplicate(["Pasta", "Quick", "Italian"])

    assert sorted(survivors) == ["Italian", "Pasta", "Quick"]
    assert merge_map == {}


# --- Chain resolution (proven through propose_merges with a fixed AI map) -------------


def test_propose_merges_resolves_a_transitive_chain() -> None:
    provider = _MapProvider({"Veggie": "Veg", "Veg": "Vegetarian"})

    merges, _stats = propose_merges(provider, ["Veggie", "Veg", "Vegetarian"])

    # A->B->C collapses so both duplicates point straight at the terminal canonical.
    assert merges == {"Veggie": "Vegetarian", "Veg": "Vegetarian"}


def test_propose_merges_drops_self_maps_and_cycles() -> None:
    provider = _MapProvider({"Keep": "Keep", "A": "B", "B": "A"})

    assert propose_merges(provider, ["Keep", "A", "B"])[0] == {}


# --- Applying merges to the database -------------------------------------------------


def test_apply_merges_reassigns_recipe_and_book_associations(session: Session) -> None:
    recipe = _recipe_zero(session)
    book = _with_recipes(session)
    # "Pasta" is shared: on recipe 0 and on the book (the single shared vocabulary).
    applied = apply_merges(session, {"Pasta": "Noodles"})
    session.commit()

    assert applied == 1
    assert "Noodles" in {k.name for k in recipe.keywords}
    assert "Pasta" not in {k.name for k in recipe.keywords}
    assert "Noodles" in {k.name for k in book.keywords}
    assert "Pasta" not in {k.name for k in book.keywords}
    # The merged-away keyword is gone; the canonical exists exactly once.
    assert session.scalar(select(func.count()).select_from(Keyword).where(Keyword.name == "Pasta")) == 0
    assert session.scalar(select(func.count()).select_from(Keyword).where(Keyword.name == "Noodles")) == 1


def test_apply_merges_dedupes_when_owner_already_has_both(session: Session) -> None:
    recipe = _recipe_zero(session)
    veg = Keyword(name="Veg")
    vegetarian = Keyword(name="Vegetarian")
    session.add_all([veg, vegetarian])
    recipe.keywords.extend([veg, vegetarian])
    session.commit()

    applied = apply_merges(session, {"Veg": "Vegetarian"})
    session.commit()

    assert applied == 1
    # No duplicate association: "Vegetarian" appears exactly once on the recipe.
    assert [k.name for k in recipe.keywords].count("Vegetarian") == 1
    assert "Veg" not in {k.name for k in recipe.keywords}


def test_apply_merges_creates_the_canonical_when_absent(session: Session) -> None:
    recipe = _recipe_zero(session)
    veggie = Keyword(name="Veggie")
    session.add(veggie)
    recipe.keywords.append(veggie)
    session.commit()

    applied = apply_merges(session, {"Veggie": "Vegetarian"})
    session.commit()

    assert applied == 1
    assert "Vegetarian" in {k.name for k in recipe.keywords}
    assert session.scalar(select(func.count()).select_from(Keyword).where(Keyword.name == "Vegetarian")) == 1


def test_apply_merges_skips_a_duplicate_with_no_row(session: Session) -> None:
    applied = apply_merges(session, {"Ghost": "Phantom"})
    session.commit()

    assert applied == 0
    # A duplicate that doesn't exist is skipped before the canonical is touched.
    assert session.scalar(select(func.count()).select_from(Keyword).where(Keyword.name == "Phantom")) == 0


# --- The full run --------------------------------------------------------------------


def test_deduplicate_keywords_end_to_end(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.keyword_dedup.get_ai_provider",
        lambda _session: _MapProvider({"Pasta": "Noodles"}),
    )
    recipe = _recipe_zero(session)

    result = deduplicate_keywords(session)
    session.commit()

    assert result.merges_applied == 1
    assert result.keywords_removed == 1
    assert result.keywords_in == 3  # Pasta, Quick, Italian
    assert "Noodles" in {k.name for k in recipe.keywords}


def test_deduplicate_keywords_is_a_noop_without_a_provider(session: Session) -> None:
    before = session.scalar(select(func.count()).select_from(Keyword))

    result = deduplicate_keywords(session)

    assert result == type(result)()  # all-zero DedupResult
    assert session.scalar(select(func.count()).select_from(Keyword)) == before


def test_deduplicate_keywords_with_stub_provider_merges_nothing(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.ai import StubProvider

    monkeypatch.setattr(
        "app.services.keyword_dedup.get_ai_provider", lambda _session: StubProvider("")
    )
    before = session.scalar(select(func.count()).select_from(Keyword))

    result = deduplicate_keywords(session)
    session.commit()

    # The stub echoes every keyword as its own canonical: vocabulary seen, nothing merged.
    assert result.keywords_in == before
    assert result.merges_applied == 0
    assert session.scalar(select(func.count()).select_from(Keyword)) == before


# --- Salvaging a truncated reply -----------------------------------------------------


def test_propose_merges_salvages_a_truncated_reply() -> None:
    # Cut off mid-pair, exactly as Gemini leaves it when it hits the output cap.
    provider = _RawProvider('{\n "Shrimp": "Prawn",\n "Eggplant": "Aubergine",\n "Zuc')

    merges, stats = propose_merges(provider, ["Shrimp", "Prawn", "Eggplant", "Aubergine"])

    assert merges == {"Shrimp": "Prawn", "Eggplant": "Aubergine"}
    assert stats.ai_merges == 2
    assert stats.ai_truncated is True


def test_propose_merges_yields_nothing_from_an_unsalvageable_reply() -> None:
    provider = _RawProvider("I'm sorry, I can't help with that.")

    merges, stats = propose_merges(provider, ["Pasta", "Quick"])

    assert merges == {}
    assert stats.ai_merges == 0


def test_propose_merges_drops_a_key_outside_the_candidate_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.keyword_dedup.DEDUP_CANDIDATE_WINDOW", 1)
    # Sorted, the window is ["Aubergine"], so the Shrimp entry names a keyword the model
    # was only given as context — it must not be merged away.
    provider = _MapProvider({"Aubergine": "Brinjal", "Shrimp": "Prawn"})

    merges, stats = propose_merges(provider, ["Shrimp", "Prawn", "Aubergine"])

    assert merges == {"Aubergine": "Brinjal"}
    assert stats.candidates == 1


# --- The rotating candidate window ---------------------------------------------------


def test_select_candidates_rotates_without_repeats_and_wraps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.keyword_dedup.DEDUP_CANDIDATE_WINDOW", 2)
    names = ["Egg", "Fish", "Grain", "Herb", "Ice"]

    first, cursor = select_candidates(names, None)
    second, cursor = select_candidates(names, cursor)
    third, cursor = select_candidates(names, cursor)

    assert first == ["Egg", "Fish"]
    assert second == ["Grain", "Herb"]
    # The tail is short, so the window wraps to the start of the vocabulary.
    assert third == ["Ice", "Egg"]
    assert cursor == "Egg"


def test_select_candidates_resumes_past_a_removed_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.keyword_dedup.DEDUP_CANDIDATE_WINDOW", 2)

    # "Fish" was merged away since the last run; the window simply starts at the next name.
    window, _cursor = select_candidates(["Egg", "Grain", "Herb", "Ice"], "Fish")

    assert window == ["Grain", "Herb"]


def test_select_candidates_on_an_empty_vocabulary() -> None:
    assert select_candidates([], None) == ([], None)


def test_deduplicate_keywords_reports_both_stages(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    recipe = _recipe_zero(session)
    recipe.keywords.append(Keyword(name="Pastas"))
    session.commit()
    monkeypatch.setattr(
        "app.services.keyword_dedup.get_ai_provider",
        lambda _session: _MapProvider({"Quick": "Fast"}),
    )

    result = deduplicate_keywords(session)
    session.commit()

    # "Pastas" folds into "Pasta" deterministically; "Quick" -> "Fast" is the AI's.
    assert result.pre_merges == 1
    assert result.ai_merges == 1
    assert result.merges_applied == result.pre_merges + result.ai_merges
    assert result.keywords_removed == result.merges_applied
    assert result.cursor_to is not None
