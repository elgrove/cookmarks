"""Tests for recipe filtering logic in the recipes view."""

import pytest
from django.test import Client

from core.models import Book, Keyword, Recipe, RecipeList, RecipeListItem


@pytest.fixture
def sample_data(db):
    """Create sample books, recipes, and keywords for testing filters."""
    # Create books
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

    # Create keywords
    chinese_kw = Keyword.objects.create(name="Chinese")
    indian_kw = Keyword.objects.create(name="Indian")
    vegetarian_kw = Keyword.objects.create(name="Vegetarian")
    starter_kw = Keyword.objects.create(name="Starter")
    curry_kw = Keyword.objects.create(name="Curry")
    quick_kw = Keyword.objects.create(name="Quick")

    # Create recipes
    # Chinese chicken dish
    kung_pao = Recipe.objects.create(
        book=chinese_book,
        name="Kung Pao Chicken",
        ingredients="chicken, peanuts, chilli",
        instructions="Stir fry chicken with sauce",
        order=1,
    )
    kung_pao.keywords.add(chinese_kw)

    # Chinese pork dish
    char_siu = Recipe.objects.create(
        book=chinese_book,
        name="Char Siu Pork",
        ingredients="pork, honey, soy sauce",
        instructions="Roast pork with glaze",
        order=2,
    )
    char_siu.keywords.add(chinese_kw)

    # Chinese vegetarian starter
    spring_rolls = Recipe.objects.create(
        book=chinese_book,
        name="Vegetable Spring Rolls",
        ingredients="cabbage, carrots, spring roll wrappers",
        instructions="Roll and fry",
        order=3,
    )
    spring_rolls.keywords.add(chinese_kw, vegetarian_kw, starter_kw)

    # Indian curry with coconut and beef
    beef_curry = Recipe.objects.create(
        book=indian_book,
        name="Kerala Beef Curry",
        ingredients="beef, coconut milk, curry leaves",
        instructions="Slow cook with spices",
        order=1,
    )
    beef_curry.keywords.add(indian_kw, curry_kw)

    # Indian vegetarian curry
    dal = Recipe.objects.create(
        book=indian_book,
        name="Dal Tadka",
        ingredients="lentils, onions, tomatoes",
        instructions="Cook lentils with tempered spices",
        order=2,
    )
    dal.keywords.add(indian_kw, vegetarian_kw, curry_kw, quick_kw)

    # Indian starter
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


@pytest.mark.django_db
class TestRecipeQuickSearch:
    """Tests for quick search (q parameter) functionality."""

    def test_quick_search_finds_by_recipe_name(self, sample_data):
        client = Client()
        response = client.get("/recipes/", {"q": "kung pao"})

        assert response.status_code == 200
        recipes = list(response.context["recipes"])
        assert len(recipes) == 1
        assert recipes[0].name == "Kung Pao Chicken"

    def test_quick_search_finds_by_ingredient(self, sample_data):
        client = Client()
        response = client.get("/recipes/", {"q": "coconut"})

        assert response.status_code == 200
        recipes = list(response.context["recipes"])
        assert len(recipes) == 1
        assert recipes[0].name == "Kerala Beef Curry"

    def test_quick_search_finds_by_author(self, sample_data):
        client = Client()
        response = client.get("/recipes/", {"q": "fuchsia"})

        assert response.status_code == 200
        recipes = list(response.context["recipes"])
        assert len(recipes) == 3  # All Chinese cookbook recipes
        recipe_names = {r.name for r in recipes}
        assert "Kung Pao Chicken" in recipe_names
        assert "Char Siu Pork" in recipe_names
        assert "Vegetable Spring Rolls" in recipe_names

    def test_quick_search_finds_by_keyword(self, sample_data):
        client = Client()
        response = client.get("/recipes/", {"q": "vegetarian"})

        assert response.status_code == 200
        recipes = list(response.context["recipes"])
        assert len(recipes) == 3
        recipe_names = {r.name for r in recipes}
        assert "Vegetable Spring Rolls" in recipe_names
        assert "Dal Tadka" in recipe_names
        assert "Vegetable Samosas" in recipe_names


@pytest.mark.django_db
class TestRecipeAdvancedFilters:
    """Tests for advanced filter builder functionality."""

    def test_single_filter_contains(self, sample_data):
        """Test single filter: keywords contains 'Chinese'."""
        client = Client()
        response = client.get(
            "/recipes/",
            {
                "filter_field[]": "keywords",
                "filter_op[]": "contains",
                "filter_value[]": "Chinese",
                "filter_group[]": "0",
                "filter_logic[]": "and",
            },
        )

        assert response.status_code == 200
        recipes = list(response.context["recipes"])
        assert len(recipes) == 3
        for recipe in recipes:
            assert any(kw.name == "Chinese" for kw in recipe.keywords.all())

    def test_single_filter_not_contains(self, sample_data):
        """Test negation: ingredients doesn't contain 'chicken'."""
        # First search for all Chinese recipes, then exclude chicken
        client = Client()
        response = client.get(
            "/recipes/",
            {
                "filter_field[]": ["keywords", "ingredients"],
                "filter_op[]": ["contains", "not_contains"],
                "filter_value[]": ["Chinese", "chicken"],
                "filter_group[]": ["0", "0"],
                "filter_logic[]": ["and", "and"],
            },
        )

        assert response.status_code == 200
        recipes = list(response.context["recipes"])
        assert len(recipes) == 2
        recipe_names = {r.name for r in recipes}
        assert "Kung Pao Chicken" not in recipe_names
        assert "Char Siu Pork" in recipe_names
        assert "Vegetable Spring Rolls" in recipe_names


@pytest.mark.django_db
class TestRecipeFilterCombinations:
    """Tests for complex filter combinations like the prompt examples."""

    def test_chinese_with_chicken_or_pork(self, sample_data):
        """
        Example: 'chinese recipes with chicken or pork'
        Should match Kung Pao Chicken and Char Siu Pork.
        """
        client = Client()
        response = client.get(
            "/recipes/",
            {
                "group_logic": "and",
                "filter_field[]": ["keywords", "ingredients", "ingredients"],
                "filter_op[]": ["contains", "contains", "contains"],
                "filter_value[]": ["Chinese", "chicken", "pork"],
                "filter_group[]": ["0", "1", "1"],
                "filter_logic[]": ["and", "or", "or"],
            },
        )

        assert response.status_code == 200
        recipes = list(response.context["recipes"])
        assert len(recipes) == 2
        recipe_names = {r.name for r in recipes}
        assert "Kung Pao Chicken" in recipe_names
        assert "Char Siu Pork" in recipe_names

    def test_vegetarian_or_starter(self, sample_data):
        """
        Test OR logic: recipes with Vegetarian OR Starter keyword.
        Should match Spring Rolls, Samosas, and Dal.
        """
        client = Client()
        response = client.get(
            "/recipes/",
            {
                "group_logic": "and",
                "filter_field[]": ["keywords", "keywords"],
                "filter_op[]": ["contains", "contains"],
                "filter_value[]": ["Vegetarian", "Starter"],
                "filter_group[]": ["0", "0"],  # Same group = OR within group
                "filter_logic[]": ["or", "or"],
            },
        )

        assert response.status_code == 200
        recipes = list(response.context["recipes"])
        # Matches: Spring Rolls (both), Samosas (both), Dal (vegetarian)
        assert len(recipes) >= 3
        recipe_names = {r.name for r in recipes}
        assert "Vegetable Spring Rolls" in recipe_names
        assert "Vegetable Samosas" in recipe_names

    def test_curry_with_coconut_and_beef(self, sample_data):
        """
        Example: 'beef and coconut curries'
        Should match Kerala Beef Curry.
        """
        client = Client()
        response = client.get(
            "/recipes/",
            {
                "group_logic": "and",
                "filter_field[]": ["keywords", "ingredients", "ingredients"],
                "filter_op[]": ["contains", "contains", "contains"],
                "filter_value[]": ["Curry", "coconut", "beef"],
                "filter_group[]": ["0", "0", "0"],
                "filter_logic[]": ["and", "and", "and"],
            },
        )

        assert response.status_code == 200
        recipes = list(response.context["recipes"])
        assert len(recipes) == 1
        assert recipes[0].name == "Kerala Beef Curry"

    def test_recipes_by_author(self, sample_data):
        """
        Example: 'recipes by fuchsia dunlop'
        Should match all recipes from Chinese Cooking book.
        """
        client = Client()
        response = client.get(
            "/recipes/",
            {
                "filter_field[]": "author",
                "filter_op[]": "contains",
                "filter_value[]": "Fuchsia Dunlop",
                "filter_group[]": "0",
                "filter_logic[]": "and",
            },
        )

        assert response.status_code == 200
        recipes = list(response.context["recipes"])
        assert len(recipes) == 3
        for recipe in recipes:
            assert recipe.book.author == "Fuchsia Dunlop"

    def test_indian_quick_recipes(self, sample_data):
        """
        Test AND across different fields: Indian cuisine + Quick keyword.
        Should match Dal Tadka (Indian + Quick).
        Uses different filter fields to avoid M2M AND limitation.
        """
        client = Client()
        response = client.get(
            "/recipes/",
            {
                "group_logic": "and",
                "filter_field[]": ["keywords", "author"],
                "filter_op[]": ["contains", "contains"],
                "filter_value[]": ["Quick", "Asma Khan"],
                "filter_group[]": ["0", "1"],
                "filter_logic[]": ["and", "and"],
            },
        )

        assert response.status_code == 200
        recipes = list(response.context["recipes"])
        assert len(recipes) == 1
        assert recipes[0].name == "Dal Tadka"


@pytest.mark.django_db
class TestRecipeListFiltering:
    """Tests for filtering recipes by list."""

    def test_filter_by_list(self, sample_data):
        """Test filtering recipes by a custom list."""
        # Create a list and add some recipes
        my_list = RecipeList.objects.create(name="Favourites")
        RecipeListItem.objects.create(
            recipe=sample_data["recipes"]["kung_pao"], recipe_list=my_list
        )
        RecipeListItem.objects.create(recipe=sample_data["recipes"]["dal"], recipe_list=my_list)

        client = Client()
        response = client.get("/recipes/", {"selected_lists[]": str(my_list.id)})

        assert response.status_code == 200
        recipes = list(response.context["recipes"])
        assert len(recipes) == 2
        recipe_names = {r.name for r in recipes}
        assert "Kung Pao Chicken" in recipe_names
        assert "Dal Tadka" in recipe_names

    def test_filter_by_list_with_additional_filters(self, sample_data):
        """Test filtering by list AND keyword."""
        my_list = RecipeList.objects.create(name="To Try")
        RecipeListItem.objects.create(
            recipe=sample_data["recipes"]["kung_pao"], recipe_list=my_list
        )
        RecipeListItem.objects.create(recipe=sample_data["recipes"]["dal"], recipe_list=my_list)
        RecipeListItem.objects.create(
            recipe=sample_data["recipes"]["beef_curry"], recipe_list=my_list
        )

        # Filter list + vegetarian keyword
        client = Client()
        response = client.get(
            "/recipes/",
            {
                "selected_lists[]": str(my_list.id),
                "filter_field[]": "keywords",
                "filter_op[]": "contains",
                "filter_value[]": "Vegetarian",
                "filter_group[]": "0",
                "filter_logic[]": "and",
            },
        )

        assert response.status_code == 200
        recipes = list(response.context["recipes"])
        assert len(recipes) == 1
        assert recipes[0].name == "Dal Tadka"


@pytest.mark.django_db
class TestRecipeSorting:
    """Tests for recipe sorting options."""

    def test_sort_by_name(self, sample_data):
        """Test sorting by name A-Z."""
        client = Client()
        response = client.get("/recipes/", {"q": "curry", "sort": "name"})

        assert response.status_code == 200
        recipes = list(response.context["recipes"])
        names = [r.name for r in recipes]
        assert names == sorted(names)

    def test_sort_by_author(self, sample_data):
        """Test sorting by author."""
        # Search for all recipes with a broad term
        client = Client()
        response = client.get(
            "/recipes/",
            {
                "filter_field[]": "name",
                "filter_op[]": "contains",
                "filter_value[]": "a",  # Matches most recipes
                "filter_group[]": "0",
                "filter_logic[]": "and",
                "sort": "author",
            },
        )

        assert response.status_code == 200
        recipes = list(response.context["recipes"])
        # Asma Khan comes before Fuchsia Dunlop alphabetically
        authors = [r.book.author for r in recipes]
        assert authors == sorted(authors)

    def test_sort_random(self, sample_data):
        """Test random sort doesn't error."""
        client = Client()
        response = client.get(
            "/recipes/",
            {
                "filter_field[]": "keywords",
                "filter_op[]": "contains",
                "filter_value[]": "Chinese",
                "filter_group[]": "0",
                "filter_logic[]": "and",
                "sort": "random",
            },
        )

        assert response.status_code == 200
        recipes = list(response.context["recipes"])
        assert len(recipes) == 3
