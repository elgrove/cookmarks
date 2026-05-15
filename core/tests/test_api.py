"""Smoke tests for the Django Ninja API."""

import pytest
from django.contrib.auth.models import User
from django.test import Client

from core.models import Book, Config, Recipe, RecipeList, RecipeListItem


@pytest.mark.django_db
class TestAuth:
    def test_me_with_no_auth_creates_admin(self):
        r = Client().get("/api/v1/auth/me")
        assert r.status_code == 200
        body = r.json()
        assert body["username"] == "admin"
        assert User.objects.filter(username="admin").exists()

    def test_me_without_no_auth_returns_401(self, monkeypatch):
        monkeypatch.delenv("NO_AUTH", raising=False)
        r = Client().get("/api/v1/auth/me")
        assert r.status_code == 401

    def test_login_and_me(self, monkeypatch):
        monkeypatch.delenv("NO_AUTH", raising=False)
        u = User.objects.create_user(username="bob", password="hunter2")
        c = Client()
        r = c.post(
            "/api/v1/auth/login",
            data={"username": "bob", "password": "hunter2"},
            content_type="application/json",
        )
        assert r.status_code == 200
        assert r.json()["username"] == "bob"

        r = c.get("/api/v1/auth/me")
        assert r.status_code == 200
        assert r.json()["id"] == u.id

    def test_login_bad_creds(self, monkeypatch):
        monkeypatch.delenv("NO_AUTH", raising=False)
        User.objects.create_user(username="bob", password="hunter2")
        r = Client().post(
            "/api/v1/auth/login",
            data={"username": "bob", "password": "wrong"},
            content_type="application/json",
        )
        assert r.status_code == 401

    def test_auth_config_reflects_no_auth(self):
        r = Client().get("/api/v1/auth/config")
        assert r.json() == {"no_auth": True}


@pytest.mark.django_db
class TestOpenAPI:
    def test_openapi_schema_served(self):
        r = Client().get("/api/v1/openapi.json")
        assert r.status_code == 200
        spec = r.json()
        assert spec["info"]["title"] == "Cookmarks API"
        paths = spec["paths"]
        for p in [
            "/api/v1/auth/me",
            "/api/v1/books",
            "/api/v1/recipes",
            "/api/v1/lists",
            "/api/v1/keywords",
            "/api/v1/tasks",
            "/api/v1/config",
            "/api/v1/extraction-reports",
            "/api/v1/stats/home",
        ]:
            assert p in paths, p


@pytest.mark.django_db
class TestBooksAndStats:
    def test_home_stats_empty(self):
        r = Client().get("/api/v1/stats/home")
        assert r.status_code == 200
        body = r.json()
        assert body["has_books"] is False
        assert body["books_count"] == 0

    def test_home_stats_with_books(self):
        Book.objects.create(calibre_id=1, title="A", author="Z")
        r = Client().get("/api/v1/stats/home")
        body = r.json()
        assert body["has_books"] is True
        assert body["books_count"] == 1

    def test_books_list_filter(self):
        Book.objects.create(calibre_id=1, title="Indian Curry", author="A")
        Book.objects.create(calibre_id=2, title="Chinese Wok", author="B")
        r = Client().get("/api/v1/books", {"search": "Indian", "sort": "title"})
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "Indian Curry"


@pytest.mark.django_db
class TestLists:
    def test_create_and_list(self):
        c = Client()
        r = c.post("/api/v1/lists", data={"name": "My list"}, content_type="application/json")
        assert r.status_code == 201
        list_id = r.json()["id"]

        r = c.get("/api/v1/lists")
        names = [item["name"] for item in r.json()]
        assert "My list" in names

        r = c.delete(f"/api/v1/lists/{list_id}")
        assert r.status_code == 200

    def test_add_and_remove_recipe(self):
        book = Book.objects.create(calibre_id=1, title="B", author="A")
        recipe = Recipe.objects.create(book=book, name="X", order=1)
        rl = RecipeList.objects.create(name="L")
        c = Client()

        r = c.post(f"/api/v1/lists/{rl.id}/recipes/{recipe.id}")
        assert r.status_code == 200
        assert RecipeListItem.objects.filter(recipe=recipe, recipe_list=rl).exists()

        r = c.post(f"/api/v1/lists/{rl.id}/recipes/{recipe.id}")
        assert r.status_code == 409

        r = c.delete(f"/api/v1/lists/{rl.id}/recipes/{recipe.id}")
        assert r.status_code == 200


@pytest.mark.django_db
class TestRecipeToggleFavourite:
    def test_toggle(self):
        book = Book.objects.create(calibre_id=1, title="B", author="A")
        recipe = Recipe.objects.create(book=book, name="X", order=1)
        c = Client()

        r = c.post(f"/api/v1/recipes/{recipe.id}/toggle-favourite")
        assert r.json() == {"is_favourite": True}

        r = c.post(f"/api/v1/recipes/{recipe.id}/toggle-favourite")
        assert r.json() == {"is_favourite": False}


@pytest.mark.django_db
class TestConfig:
    def test_patch_config(self):
        c = Client()
        r = c.patch(
            "/api/v1/config",
            data={"ai_provider": "GEMINI", "api_key": "key123"},
            content_type="application/json",
        )
        assert r.status_code == 200
        assert Config.get_solo().ai_provider == "GEMINI"
        assert Config.get_solo().api_key == "key123"

        r = c.get("/api/v1/config")
        assert r.json()["is_configured"] is True
        assert r.json()["api_key_masked"] != ""
