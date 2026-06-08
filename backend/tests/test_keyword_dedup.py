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

    merges = propose_merges(provider, ["Veggie", "Veg", "Vegetarian"])

    # A->B->C collapses so both duplicates point straight at the terminal canonical.
    assert merges == {"Veggie": "Vegetarian", "Veg": "Vegetarian"}


def test_propose_merges_drops_self_maps_and_cycles() -> None:
    provider = _MapProvider({"Keep": "Keep", "A": "B", "B": "A"})

    assert propose_merges(provider, ["Keep", "A", "B"]) == {}


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
