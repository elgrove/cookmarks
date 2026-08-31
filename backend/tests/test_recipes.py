import uuid
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.recipes import _clear_keyword_cache
from app.config import settings
from app.models import Keyword, Recipe

# Matches the image member recorded on the seeded "Recipe 0" (see tests/conftest.py).
RECIPE0_IMAGE_MEMBER = "OPS/images/recipe-0.jpg"
JPEG_MAGIC = b"\xff\xd8\xff"

RECIPE_KEYS = {
    "id",
    "book_id",
    "book_title",
    "book_author",
    "book_has_cover",
    "name",
    "description",
    "ingredients_verbatim",
    "ingredients",
    "enrichment_status",
    "cuisines",
    "methods",
    "courses",
    "instructions",
    "yields",
    "keywords",
    "has_image",
    "is_favourite",
    "context",
    "in_book",
    "previous",
    "next",
}


def _book_id(client: TestClient, title: str) -> str:
    books = {b["title"]: b for b in client.get("/api/books").json()}
    return books[title]["id"]


def _recipe_id(client: TestClient, name: str = "Recipe 0") -> str:
    book_id = _book_id(client, "With Recipes")
    recipes = client.get(f"/api/books/{book_id}").json()["recipes"]
    return next(r["id"] for r in recipes if r["name"] == name)


# --- Search / keyword endpoints -------------------------------------------------


def test_empty_until_a_query(client: TestClient) -> None:
    # No query and no filters → the resting (empty) state, not a full dump.
    body = client.get("/api/recipes").json()
    assert body == {"total": 0, "items": [], "facets": []}


def test_search_matches_name(client: TestClient) -> None:
    body = client.get("/api/recipes", params={"q": "recipe"}).json()
    assert body["total"] == 3
    assert {r["name"] for r in body["items"]} == {"Recipe 0", "Recipe 1", "Recipe 2"}


def test_search_matches_ingredients(client: TestClient) -> None:
    # "anchovy" only appears in Recipe 0's ingredient list.
    body = client.get("/api/recipes", params={"q": "anchovy"}).json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Recipe 0"


def test_search_terms_need_not_be_adjacent(client: TestClient) -> None:
    # Each term matches independently: "anchovy" is an ingredient, "0" the name.
    body = client.get("/api/recipes", params={"q": "anchovy 0"}).json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Recipe 0"
    assert client.get("/api/recipes", params={"q": "anchovy sardine"}).json()["total"] == 0


def test_search_quoted_phrase_is_one_term(client: TestClient) -> None:
    assert client.get("/api/recipes", params={"q": '"100g anchovy"'}).json()["total"] == 1
    assert client.get("/api/recipes", params={"q": '"anchovy 100g"'}).json()["total"] == 0
    # An unbalanced quote falls back to plain terms rather than erroring.
    assert client.get("/api/recipes", params={"q": '"anchovy'}).json()["total"] == 1


def test_search_folds_accents(client: TestClient, session: Session) -> None:
    recipe = session.scalars(select(Recipe).where(Recipe.name == "Recipe 0")).one()
    recipe.name = "Cheese Soufflé"
    session.commit()
    body = client.get("/api/recipes", params={"q": "souffle"}).json()
    assert [r["name"] for r in body["items"]] == ["Cheese Soufflé"]


def test_search_stems_plurals(client: TestClient, session: Session) -> None:
    recipe = session.scalars(select(Recipe).where(Recipe.name == "Recipe 0")).one()
    recipe.name = "Tomato Salad"
    session.commit()
    body = client.get("/api/recipes", params={"q": "tomatoes"}).json()
    assert [r["name"] for r in body["items"]] == ["Tomato Salad"]


def test_relevance_puts_name_matches_first(client: TestClient, session: Session) -> None:
    # "anchovy" is in Recipe 1's name and only in Recipe 0's ingredient list.
    recipe = session.scalars(select(Recipe).where(Recipe.name == "Recipe 1")).one()
    recipe.name = "Anchovy Butter"
    session.commit()
    params = {"q": "anchovy", "sort": "relevance"}
    names = [r["name"] for r in client.get("/api/recipes", params=params).json()["items"]]
    assert names == ["Anchovy Butter", "Recipe 0"]


def test_search_matches_book_author(client: TestClient) -> None:
    body = client.get("/api/recipes", params={"q": "author one"}).json()
    assert body["total"] == 3


def test_keyword_filter(client: TestClient) -> None:
    body = client.get("/api/recipes", params={"keyword": "Pasta"}).json()
    assert body["total"] == 1
    assert body["items"][0]["keywords"] == ["Pasta", "Quick"]


def test_keyword_filter_unknown_is_empty(client: TestClient) -> None:
    body = client.get("/api/recipes", params={"keyword": "nope"}).json()
    assert body == {"total": 0, "items": [], "facets": []}


def test_book_filter(client: TestClient) -> None:
    with_recipes = _book_id(client, "With Recipes")
    without = _book_id(client, "No Recipes Yet")
    assert client.get("/api/recipes", params={"book_id": with_recipes}).json()["total"] == 3
    assert client.get("/api/recipes", params={"book_id": without}).json()["total"] == 0


def test_author_filter(client: TestClient) -> None:
    assert client.get("/api/recipes", params={"author": "Author One"}).json()["total"] == 3
    assert client.get("/api/recipes", params={"author": "Author Two"}).json()["total"] == 0


def test_query_and_filter_are_anded(client: TestClient) -> None:
    # "recipe" matches all three by name; the keyword narrows to Recipe 0.
    both = client.get("/api/recipes", params={"q": "recipe", "keyword": "Pasta"}).json()
    assert both["total"] == 1
    assert both["items"][0]["name"] == "Recipe 0"


def test_sort_name(client: TestClient) -> None:
    items = client.get("/api/recipes", params={"q": "recipe", "sort": "name"}).json()["items"]
    assert [r["name"] for r in items] == ["Recipe 0", "Recipe 1", "Recipe 2"]


def test_sort_book_follows_stored_order(client: TestClient) -> None:
    # Book order is the recipe's stored sequence within its book — what the
    # book-detail "Browse recipes" action lands on.
    book_id = _book_id(client, "With Recipes")
    items = client.get("/api/recipes", params={"book_id": book_id, "sort": "book"}).json()["items"]
    assert [r["name"] for r in items] == ["Recipe 0", "Recipe 1", "Recipe 2"]


def test_default_sort_is_random(client: TestClient) -> None:
    # The default returns the full set; order is the shuffle, so assert membership.
    body = client.get("/api/recipes", params={"q": "recipe"}).json()
    assert body["total"] == 3
    assert {r["name"] for r in body["items"]} == {"Recipe 0", "Recipe 1", "Recipe 2"}


def test_random_sort_is_stable_per_seed(client: TestClient) -> None:
    # Same seed → same ordering (so pagination is coherent); the full set returns.
    params = {"q": "recipe", "sort": "random", "seed": 12345}
    first = [r["name"] for r in client.get("/api/recipes", params=params).json()["items"]]
    again = [r["name"] for r in client.get("/api/recipes", params=params).json()["items"]]
    assert first == again
    assert set(first) == {"Recipe 0", "Recipe 1", "Recipe 2"}


def test_pagination(client: TestClient) -> None:
    base = {"q": "recipe", "sort": "name", "limit": 2}
    first = client.get("/api/recipes", params={**base, "offset": 0}).json()
    assert first["total"] == 3
    assert [r["name"] for r in first["items"]] == ["Recipe 0", "Recipe 1"]
    second = client.get("/api/recipes", params={**base, "offset": 2}).json()
    assert second["total"] == 3
    assert [r["name"] for r in second["items"]] == ["Recipe 2"]


def test_pagination_past_the_end_keeps_the_total(client: TestClient) -> None:
    # No rows means no windowed count to read off them, so the total falls back
    # to its own query rather than collapsing to 0.
    body = client.get(
        "/api/recipes", params={"q": "recipe", "sort": "name", "limit": 2, "offset": 10}
    ).json()
    assert body["items"] == []
    assert body["total"] == 3


def test_facets_rank_cooccurring_keywords(client: TestClient) -> None:
    # "recipe" matches all three; only Recipe 0 carries keywords, so the facets
    # are its keywords, counted over the matching set.
    body = client.get("/api/recipes", params={"q": "recipe"}).json()
    assert body["facets"] == [
        {"name": "Pasta", "recipe_count": 1},
        {"name": "Quick", "recipe_count": 1},
    ]


def test_facets_exclude_selected_keywords(client: TestClient) -> None:
    # With Pasta selected, the facet list offers what narrows *further* — Quick —
    # and drops the already-chosen Pasta.
    body = client.get("/api/recipes", params={"keyword": "Pasta"}).json()
    assert body["facets"] == [{"name": "Quick", "recipe_count": 1}]


def test_facets_respect_the_query(client: TestClient) -> None:
    # "anchovy" narrows to Recipe 0 alone; the facets are that recipe's keywords.
    body = client.get("/api/recipes", params={"q": "anchovy"}).json()
    assert body["facets"] == [
        {"name": "Pasta", "recipe_count": 1},
        {"name": "Quick", "recipe_count": 1},
    ]


def test_keywords_endpoint(client: TestClient) -> None:
    body = client.get("/api/keywords").json()
    assert body == [
        {"name": "Pasta", "recipe_count": 1},
        {"name": "Quick", "recipe_count": 1},
    ]


def test_keywords_limit_caps_result(client: TestClient) -> None:
    # The client only renders the most-used keywords; the limit keeps the endpoint
    # from serialising the whole corpus. Ordered by count desc, name asc → Pasta.
    body = client.get("/api/keywords", params={"limit": 1}).json()
    assert body == [{"name": "Pasta", "recipe_count": 1}]


def test_keywords_endpoint_is_cached_until_cleared(client: TestClient, session: Session) -> None:
    # Computed once per process, then served from memory.
    assert [k["name"] for k in client.get("/api/keywords").json()] == ["Pasta", "Quick"]
    # A keyword added afterwards isn't reflected — the cached top-N is served as-is.
    # It must be on a recipe to qualify: /api/keywords is recipe-scoped.
    recipe = session.scalars(select(Recipe)).first()
    assert recipe is not None
    recipe.keywords.append(Keyword(name="Zzz"))
    session.commit()
    assert [k["name"] for k in client.get("/api/keywords").json()] == ["Pasta", "Quick"]
    # Clearing the cache (as the extraction task will on write) picks it up.
    _clear_keyword_cache()
    assert "Zzz" in [k["name"] for k in client.get("/api/keywords").json()]


# --- Recipe detail + prev/next navigation --------------------------------------


def test_recipe_detail_shape(client: TestClient) -> None:
    resp = client.get(f"/api/recipes/{_recipe_id(client)}")
    assert resp.status_code == 200
    assert set(resp.json().keys()) == RECIPE_KEYS


def test_recipe_detail_content(client: TestClient) -> None:
    body = client.get(f"/api/recipes/{_recipe_id(client)}").json()
    assert body["name"] == "Recipe 0"
    assert body["description"] == "A quick weeknight pasta."
    assert body["yields"] == "Serves 2"
    assert [line["text"] for line in body["ingredients_verbatim"]] == [
        "200g pasta",
        "100g anchovy",
        "2 tbsp olive oil",
    ]
    assert body["ingredients"] == []
    assert body["enrichment_status"] == "pending"
    assert body["instructions"] == ["Boil the pasta.", "Toss with the oil and serve."]
    # Keywords come back sorted by name.
    assert body["keywords"] == ["Pasta", "Quick"]
    assert body["has_image"] is True


def test_recipe_detail_provenance(client: TestClient) -> None:
    body = client.get(f"/api/recipes/{_recipe_id(client)}").json()
    assert body["book_id"] == _book_id(client, "With Recipes")
    assert body["book_title"] == "With Recipes"
    assert body["book_author"] == "Author One"
    assert body["book_has_cover"] is False


def test_recipe_optional_fields_when_absent(client: TestClient) -> None:
    # "Recipe 1" carries no description/yields/image/keywords.
    body = client.get(f"/api/recipes/{_recipe_id(client, 'Recipe 1')}").json()
    assert body["description"] is None
    assert body["yields"] is None
    assert body["has_image"] is False
    assert body["ingredients_verbatim"] == []
    assert body["ingredients"] == []
    assert body["instructions"] == []
    assert body["keywords"] == []


# --- The cached position in the book's pages -----------------------------------


def test_epub_location_is_a_tri_state(client: TestClient) -> None:
    """Never checked reads null; a hit reads true and comes back on the book's recipe
    index for the reader; a miss reads false without a cached position."""
    recipe_id = _recipe_id(client, "Recipe 0")
    book_id = _book_id(client, "With Recipes")
    cfi = "epubcfi(/6/14!/4/2/6,/1:0,/1:34)"

    assert client.get(f"/api/recipes/{recipe_id}").json()["in_book"] is None
    index = {r["id"]: r for r in client.get(f"/api/books/{book_id}/recipe-index").json()}
    assert index[recipe_id]["epub_cfi"] is None

    resp = client.put(f"/api/recipes/{recipe_id}/epub-location", json={"cfi": cfi})
    assert resp.status_code == 204
    assert client.get(f"/api/recipes/{recipe_id}").json()["in_book"] is True
    index = {r["id"]: r for r in client.get(f"/api/books/{book_id}/recipe-index").json()}
    assert index[recipe_id]["epub_cfi"] == cfi

    # A re-check that finds nothing (the book no longer spells it that way) clears the
    # cached position and records the recipe as absent, not as never checked.
    resp = client.put(f"/api/recipes/{recipe_id}/epub-location", json={"cfi": None})
    assert resp.status_code == 204
    assert client.get(f"/api/recipes/{recipe_id}").json()["in_book"] is False
    index = {r["id"]: r for r in client.get(f"/api/books/{book_id}/recipe-index").json()}
    assert index[recipe_id]["epub_cfi"] is None


def test_epub_location_unknown_recipe_is_404(client: TestClient) -> None:
    resp = client.put(f"/api/recipes/{uuid.uuid4()}/epub-location", json={"cfi": None})
    assert resp.status_code == 404


def test_epub_location_rejects_an_empty_body_and_an_overlong_cfi(client: TestClient) -> None:
    """A miss has to be stated: an empty body must not record one by default, and the
    cached position is bounded — it comes back to every reader on the book's index."""
    recipe_id = _recipe_id(client, "Recipe 0")
    assert client.put(f"/api/recipes/{recipe_id}/epub-location", json={}).status_code == 422
    overlong = client.put(f"/api/recipes/{recipe_id}/epub-location", json={"cfi": "x" * 501})
    assert overlong.status_code == 422
    assert client.get(f"/api/recipes/{recipe_id}").json()["in_book"] is None


def test_recipe_nav_default_is_book_order(client: TestClient) -> None:
    # The seed's three recipes have order 0,1,2; the middle one has both neighbours.
    body = client.get(f"/api/recipes/{_recipe_id(client, 'Recipe 1')}").json()
    assert body["context"] == "book"
    assert body["previous"]["name"] == "Recipe 0"
    assert body["next"]["name"] == "Recipe 2"


def test_recipe_nav_first_has_no_previous(client: TestClient) -> None:
    body = client.get(f"/api/recipes/{_recipe_id(client, 'Recipe 0')}").json()
    assert body["previous"] is None
    assert body["next"]["name"] == "Recipe 1"


def test_recipe_nav_last_has_no_next(client: TestClient) -> None:
    body = client.get(f"/api/recipes/{_recipe_id(client, 'Recipe 2')}").json()
    assert body["previous"]["name"] == "Recipe 1"
    assert body["next"] is None


def test_recipe_nav_unknown_context_falls_back_to_book(client: TestClient) -> None:
    # "list" isn't wired yet — an unsupported context resolves to book order.
    body = client.get(f"/api/recipes/{_recipe_id(client, 'Recipe 1')}?context=list").json()
    assert body["context"] == "book"
    assert body["previous"]["name"] == "Recipe 0"


def test_recipe_nav_search_order(client: TestClient) -> None:
    # context=search re-runs the search ordering; q=recipe + sort=name gives
    # Recipe 0,1,2, so the middle recipe's neighbours are 0 and 2.
    rid = _recipe_id(client, "Recipe 1")
    body = client.get(
        f"/api/recipes/{rid}", params={"context": "search", "q": "recipe", "sort": "name"}
    ).json()
    assert body["context"] == "search"
    assert body["previous"]["name"] == "Recipe 0"
    assert body["next"]["name"] == "Recipe 2"


def test_recipe_nav_search_respects_filters(client: TestClient) -> None:
    # Only Recipe 0 carries the Pasta keyword, so in that filtered search it is
    # alone — no neighbours — even though in book order it has a next (Recipe 1).
    rid = _recipe_id(client, "Recipe 0")
    book = client.get(f"/api/recipes/{rid}", params={"context": "book"}).json()
    assert book["next"]["name"] == "Recipe 1"
    search = client.get(
        f"/api/recipes/{rid}", params={"context": "search", "keyword": "Pasta"}
    ).json()
    assert search["context"] == "search"
    assert search["previous"] is None
    assert search["next"] is None


def test_recipe_404_for_unknown_id(client: TestClient) -> None:
    assert client.get(f"/api/recipes/{uuid.uuid4()}").status_code == 404


# --- Recipe image endpoint ------------------------------------------------------


def _write_epub(library: Path, *members: str) -> None:
    """Write a minimal EPUB for the seeded "With Recipes" book holding `members`."""
    book_dir = library / "Author One" / "With Recipes (1)"
    book_dir.mkdir(parents=True)
    with zipfile.ZipFile(book_dir / "book.epub", "w") as archive:
        for member in members:
            archive.writestr(member, JPEG_MAGIC + b" jpeg-ish bytes")


@pytest.fixture
def library_with_recipe_image(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A temp Calibre root whose EPUB carries the seeded recipe's image member."""
    _write_epub(tmp_path, RECIPE0_IMAGE_MEMBER)
    monkeypatch.setattr(settings, "calibre_library_path", tmp_path)
    return tmp_path


def test_recipe_image_served(client: TestClient, library_with_recipe_image: Path) -> None:
    rid = _recipe_id(client, "Recipe 0")
    resp = client.get(f"/api/recipes/{rid}/image")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.content.startswith(JPEG_MAGIC)


def test_recipe_image_404_when_no_image_recorded(
    client: TestClient, library_with_recipe_image: Path
) -> None:
    # Recipe 1 was seeded without an image, so the client never asks — and is 404'd.
    rid = _recipe_id(client, "Recipe 1")
    assert client.get(f"/api/recipes/{rid}/image").status_code == 404


def test_recipe_image_404_when_epub_missing(client: TestClient) -> None:
    # The image member is recorded but no EPUB exists on disk.
    rid = _recipe_id(client, "Recipe 0")
    assert client.get(f"/api/recipes/{rid}/image").status_code == 404


def test_recipe_image_404_when_member_absent(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # An EPUB is present but doesn't contain the recorded member.
    _write_epub(tmp_path, "OPS/images/something-else.jpg")
    monkeypatch.setattr(settings, "calibre_library_path", tmp_path)
    rid = _recipe_id(client, "Recipe 0")
    assert client.get(f"/api/recipes/{rid}/image").status_code == 404


def test_recipe_image_404_for_unknown_recipe(client: TestClient) -> None:
    assert client.get(f"/api/recipes/{uuid.uuid4()}/image").status_code == 404
