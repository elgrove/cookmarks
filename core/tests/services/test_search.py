import json

import pytest
import responses
from django.test import Client

from core.services.ai import translate_prompt_to_filters


def mock_openrouter_response(response_content: str):
    responses.add(
        responses.POST,
        "https://openrouter.ai/api/v1/chat/completions",
        json={
            "choices": [{"message": {"content": response_content}}],
            "usage": {
                "prompt_tokens": 500,
                "completion_tokens": 100,
                "cost": 0.0005,
            },
        },
        status=200,
    )


@pytest.mark.django_db
class TestAISearchTranslation:
    @responses.activate
    def test_translate_simple_prompt(self, configured_app):
        ai_response = json.dumps(
            {
                "group_logic": "and",
                "groups": [
                    {
                        "logic": "and",
                        "conditions": [{"field": "keywords", "op": "contains", "value": "Chinese"}],
                    }
                ],
            }
        )
        mock_openrouter_response(ai_response)

        result = translate_prompt_to_filters("chinese recipes")

        assert result is not None
        assert result["group_logic"] == "and"
        assert len(result["groups"]) == 1
        assert result["groups"][0]["conditions"][0]["field"] == "keywords"
        assert result["groups"][0]["conditions"][0]["value"] == "Chinese"

    @responses.activate
    def test_translate_complex_prompt(self, configured_app):
        ai_response = json.dumps(
            {
                "group_logic": "and",
                "groups": [
                    {
                        "logic": "and",
                        "conditions": [{"field": "keywords", "op": "contains", "value": "Chinese"}],
                    },
                    {
                        "logic": "or",
                        "conditions": [
                            {"field": "ingredients", "op": "contains", "value": "chicken"},
                            {"field": "ingredients", "op": "contains", "value": "pork"},
                        ],
                    },
                ],
            }
        )
        mock_openrouter_response(ai_response)

        result = translate_prompt_to_filters("chinese recipes with chicken or pork")

        assert result is not None
        assert result["group_logic"] == "and"
        assert len(result["groups"]) == 2
        assert result["groups"][1]["logic"] == "or"
        assert len(result["groups"][1]["conditions"]) == 2

    @responses.activate
    def test_translate_handles_markdown_wrapped_json(self, configured_app):
        ai_response = """```json
{
    "group_logic": "and",
    "groups": [{"logic": "and", "conditions": [{"field": "keywords", "op": "contains", "value": "Vegetarian"}]}]
}
```"""
        mock_openrouter_response(ai_response)

        result = translate_prompt_to_filters("vegetarian recipes")

        assert result is not None
        assert result["groups"][0]["conditions"][0]["value"] == "Vegetarian"

    def test_translate_returns_none_without_config(self):
        result = translate_prompt_to_filters("test prompt")
        assert result is None


@pytest.mark.django_db
class TestAISearchView:
    @responses.activate
    def test_view_returns_filters(self, configured_app):
        ai_response = json.dumps(
            {
                "group_logic": "and",
                "groups": [
                    {
                        "logic": "and",
                        "conditions": [
                            {"field": "keywords", "op": "contains", "value": "Japanese"}
                        ],
                    }
                ],
            }
        )
        mock_openrouter_response(ai_response)

        client = Client()
        response = client.post(
            "/search/ai-translate/",
            data=json.dumps({"prompt": "japanese food"}),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        assert "groups" in data
        assert data["groups"][0]["conditions"][0]["value"] == "Japanese"

    def test_view_rejects_get_request(self, configured_app):
        client = Client()
        response = client.get("/search/ai-translate/")

        assert response.status_code == 405
        assert response.json()["error"] == "POST required"

    def test_view_requires_prompt(self, configured_app):
        client = Client()
        response = client.post(
            "/search/ai-translate/",
            data=json.dumps({"prompt": ""}),
            content_type="application/json",
        )

        assert response.status_code == 400
        assert "required" in response.json()["error"].lower()

    def test_view_handles_invalid_json(self, configured_app):
        client = Client()
        response = client.post(
            "/search/ai-translate/",
            data="not json",
            content_type="application/json",
        )

        assert response.status_code == 400
        assert "json" in response.json()["error"].lower()
