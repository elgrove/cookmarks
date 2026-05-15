"""Tests for the recipes API endpoint and filter logic."""

import pytest
from django.test import Client

from core.models import Book, Keyword, Recipe, RecipeList, RecipeListItem


@pytest.fixture
def sample_data(db):
    """Create sample books, recipes, and keywords for testing filters."""
    chinese_book = Book.objects.create(
        calibre_id=1001,
        title="Chinese Cooking",
        author="Fuchsia Dunlop",
    )
    indian_book = Book.objects.create(
        calibre_id=1002,
        title="Indian Kitchen",
        author="Asma Khan",
    )

    chinese_kw = Keyword.objects.create(name="Chinese")
    indian_kw = Keyword.objects.create(name="Indian")
    vegetarian_kw = Keyword.objects.create(name="Vegetarian")
    starter_kw = Keyword.objects.create(name="Starter")
    curry_kw = Keyword.objects.create(name="Curry")
    quick_kw = Keyword.objects.create(name="Quick")

    kung_pao = Recipe.objects.create(
        book=chinese_book,
        name="Kung Pao Chicken",
        ingredients="chicken, peanuts, chilli",
        instructions="Stir fry chicken with sauce",
        order=1,
    )
    kung_pao.keywords.add(chinese_kw)

    char_siu = Recipe.objects.create(
        book=chinese_book,
        name="Char Siu Pork",
        ingredients="pork, honey, soy sauce",
        instructions="Roast pork with glaze",
        order=2,
    )
    char_siu.keywords.add(chinese_kw)

    spring_rolls = Recipe.objects.create(
        book=chinese_book,
        name="Vegetable Spring Rolls",
        ingredients="cabbage, carrots, spring roll wrappers",
        instructions="Roll and fry",
        order=3,
    )
    spring_rolls.keywords.add(chinese_kw, vegetarian_kw, starter_kw)

    beef_curry = Recipe.objects.create(
        book=indian_book,
        name="Kerala Beef Curry",
        ingredients="beef, coconut milk, curry leaves",
        instructions="Slow cook with spices",
        order=1,
    )
    beef_curry.keywords.add(indian_kw, curry_kw)

    dal = Recipe.objects.create(
        book=indian_book,
        name="Dal Tadka",
        ingredients="lentils, onions, tomatoes",
        instructions="Cook lentils with tempered spices",
        order=2,
    )
    dal.keywords.add(indian_kw, vegetarian_kw, curry_kw, quick_kw)

    samosa = Recipe.objects.create(
        book=indian_book,
        name="Vegetable Samosas",
        ingredients="potatoes, peas, pastry",
        instructions="Fill and fry",
        order=3,
    )
    samosa.keywords.add(indian_kw, vegetarian_kw, starter_kw)

    return {
        "books": {"chinese": chinese_book, "indian": indian_book},
        "keywords": {
            "chinese": chinese_kw,
            "indian": indian_kw,
            "vegetarian": vegetarian_kw,
            "starter": starter_kw,
            "curry": curry_kw,
            "quick": quick_kw,
        },
        "recipes": {
            "kung_pao": kung_pao,
            "char_siu": char_siu,
            "spring_rolls": spring_rolls,
            "beef_curry": beef_curry,
            "dal": dal,
            "samosa": samosa,
        },
    }


def api_get(params=None):
    return Client().get("/api/v1/recipes", params or {})


def names(payload):
    return [item["name"] for item in payload["items"]]


@pytest.mark.django_db
class TestRecipeQuickSearch:
    def test_quick_search_finds_by_recipe_name(self, sample_data):
        r = api_get({"q": "kung pao"})
        assert r.status_code == 200
        assert names(r.json()) == ["Kung Pao Chicken"]

    def test_quick_search_finds_by_ingredient(self, sample_data):
        r = api_get({"q": "coconut"})
        assert r.status_code == 200
        assert names(r.json()) == ["Kerala Beef Curry"]

    def test_quick_search_finds_by_author(self, sample_data):
        r = api_get({"q": "fuchsia"})
        assert r.status_code == 200
        out = set(names(r.json()))
        assert out == {"Kung Pao Chicken", "Char Siu Pork", "Vegetable Spring Rolls"}

    def test_quick_search_finds_by_keyword(self, sample_data):
        r = api_get({"q": "vegetarian"})
        assert r.status_code == 200
        out = set(names(r.json()))
        assert "Vegetable Spring Rolls" in out
        assert "Dal Tadka" in out
        assert "Vegetable Samosas" in out


@pytest.mark.django_db
class TestRecipeAdvancedFilters:
    def test_single_filter_contains(self, sample_data):
        r = api_get(
            {
                "filter_field": "keywords",
                "filter_op": "contains",
                "filter_value": "Chinese",
                "filter_group": "0",
                "filter_logic": "and",
            }
        )
        assert r.status_code == 200
        out = names(r.json())
        assert len(out) == 3

    def test_single_filter_not_contains(self, sample_data):
        r = api_get(
            {
                "filter_field": ["keywords", "ingredients"],
                "filter_op": ["contains", "not_contains"],
                "filter_value": ["Chinese", "chicken"],
                "filter_group": ["0", "0"],
                "filter_logic": ["and", "and"],
            }
        )
        assert r.status_code == 200
        out = set(names(r.json()))
        assert "Kung Pao Chicken" not in out
        assert "Char Siu Pork" in out
        assert "Vegetable Spring Rolls" in out


@pytest.mark.django_db
class TestRecipeFilterCombinations:
    def test_chinese_with_chicken_or_pork(self, sample_data):
        r = api_get(
            {
                "group_logic": "and",
                "filter_field": ["keywords", "ingredients", "ingredients"],
                "filter_op": ["contains", "contains", "contains"],
                "filter_value": ["Chinese", "chicken", "pork"],
                "filter_group": ["0", "1", "1"],
                "filter_logic": ["and", "or", "or"],
            }
        )
        assert r.status_code == 200
        out = set(names(r.json()))
        assert out == {"Kung Pao Chicken", "Char Siu Pork"}

    def test_vegetarian_and_starter_m2m(self, sample_data):
        r = api_get(
            {
                "group_logic": "and",
                "filter_field": ["keywords", "keywords"],
                "filter_op": ["contains", "contains"],
                "filter_value": ["Vegetarian", "Starter"],
                "filter_group": ["0", "0"],
                "filter_logic": ["and", "and"],
            }
        )
        assert r.status_code == 200
        out = set(names(r.json()))
        assert out == {"Vegetable Spring Rolls", "Vegetable Samosas"}

    def test_curry_with_coconut_and_beef(self, sample_data):
        r = api_get(
            {
                "group_logic": "and",
                "filter_field": ["keywords", "ingredients", "ingredients"],
                "filter_op": ["contains", "contains", "contains"],
                "filter_value": ["Curry", "coconut", "beef"],
                "filter_group": ["0", "0", "0"],
                "filter_logic": ["and", "and", "and"],
            }
        )
        assert r.status_code == 200
        out = names(r.json())
        assert out == ["Kerala Beef Curry"]

    def test_recipes_by_author(self, sample_data):
        r = api_get(
            {
                "filter_field": "author",
                "filter_op": "contains",
                "filter_value": "Fuchsia Dunlop",
                "filter_group": "0",
                "filter_logic": "and",
            }
        )
        assert r.status_code == 200
        out = names(r.json())
        assert len(out) == 3

    def test_indian_quick_recipes(self, sample_data):
        r = api_get(
            {
                "group_logic": "and",
                "filter_field": ["keywords", "author"],
                "filter_op": ["contains", "contains"],
                "filter_value": ["Quick", "Asma Khan"],
                "filter_group": ["0", "1"],
                "filter_logic": ["and", "and"],
            }
        )
        assert r.status_code == 200
        out = names(r.json())
        assert out == ["Dal Tadka"]


@pytest.mark.django_db
class TestRecipeListFiltering:
    def test_filter_by_list(self, sample_data):
        my_list = RecipeList.objects.create(name="Favourites")
        RecipeListItem.objects.create(
            recipe=sample_data["recipes"]["kung_pao"], recipe_list=my_list
        )
        RecipeListItem.objects.create(recipe=sample_data["recipes"]["dal"], recipe_list=my_list)

        r = api_get({"selected_lists": str(my_list.id)})
        assert r.status_code == 200
        out = set(names(r.json()))
        assert out == {"Kung Pao Chicken", "Dal Tadka"}

    def test_filter_by_list_with_additional_filters(self, sample_data):
        my_list = RecipeList.objects.create(name="To Try")
        for key in ("kung_pao", "dal", "beef_curry"):
            RecipeListItem.objects.create(recipe=sample_data["recipes"][key], recipe_list=my_list)

        r = api_get(
            {
                "selected_lists": str(my_list.id),
                "filter_field": "keywords",
                "filter_op": "contains",
                "filter_value": "Vegetarian",
                "filter_group": "0",
                "filter_logic": "and",
            }
        )
        assert r.status_code == 200
        out = names(r.json())
        assert out == ["Dal Tadka"]


@pytest.mark.django_db
class TestRecipeSorting:
    def test_sort_by_name(self, sample_data):
        r = api_get({"q": "curry", "sort": "name"})
        assert r.status_code == 200
        out = names(r.json())
        assert out == sorted(out)

    def test_sort_by_author(self, sample_data):
        r = api_get(
            {
                "filter_field": "name",
                "filter_op": "contains",
                "filter_value": "a",
                "filter_group": "0",
                "filter_logic": "and",
                "sort": "author",
            }
        )
        assert r.status_code == 200
        items = r.json()["items"]
        authors = [item["book_author"] for item in items]
        assert authors == sorted(authors)

    def test_sort_random(self, sample_data):
        r = api_get(
            {
                "filter_field": "keywords",
                "filter_op": "contains",
                "filter_value": "Chinese",
                "filter_group": "0",
                "filter_logic": "and",
                "sort": "random",
            }
        )
        assert r.status_code == 200
        assert len(r.json()["items"]) == 3
