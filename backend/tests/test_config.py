"""Behaviour of the config settings endpoints (GET/PATCH /api/config).

The defining contract here is that the API key is write-only: it can be set, rotated
and cleared, but is never serialised back to the client — only a boolean `api_key_set`.
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.config import Config


def _stored(session: Session) -> Config:
    config = session.get(Config, 1)
    assert config is not None
    return config


def test_read_config_returns_defaults_and_provider_catalogue(client: TestClient) -> None:
    body = client.get("/api/config").json()
    assert body["ai_provider"] is None
    assert body["api_key_set"] is False
    assert body["enrichment_stage1_provider"] is None
    assert body["enrichment_stage1_api_key_set"] is False
    assert body["enrichment_stage2_provider"] is None
    assert body["enrichment_stage2_api_key_set"] is False
    assert body["extraction_rate_limit_per_minute"] == 256

    providers = {p["name"]: p["requires_api_key"] for p in body["providers"]}
    assert providers == {"ANTHROPIC": True, "GEMINI": True, "OPENROUTER": True}


def test_update_provider_and_rate_limit(client: TestClient) -> None:
    body = client.patch(
        "/api/config",
        json={"ai_provider": "GEMINI", "extraction_rate_limit_per_minute": 120},
    ).json()
    assert body["ai_provider"] == "GEMINI"
    assert body["extraction_rate_limit_per_minute"] == 120

    # Persisted: a fresh read reflects the update.
    again = client.get("/api/config").json()
    assert again["ai_provider"] == "GEMINI"
    assert again["extraction_rate_limit_per_minute"] == 120


def test_update_assistant_provider(client: TestClient, session: Session) -> None:
    body = client.patch(
        "/api/config", json={"assistant_provider": "ANTHROPIC", "assistant_api_key": "sk-assistant"}
    ).json()
    assert body["assistant_provider"] == "ANTHROPIC"
    assert body["assistant_api_key_set"] is True
    assert "assistant_api_key" not in body
    assert _stored(session).assistant_api_key == "sk-assistant"


def test_update_recipe_enrichment_providers(client: TestClient, session: Session) -> None:
    body = client.patch(
        "/api/config",
        json={
            "enrichment_stage1_provider": "GEMINI",
            "enrichment_stage1_api_key": "gemini-key",
            "enrichment_stage2_provider": "ANTHROPIC",
            "enrichment_stage2_api_key": "anthropic-key",
        },
    ).json()
    assert body["enrichment_stage1_provider"] == "GEMINI"
    assert body["enrichment_stage1_api_key_set"] is True
    assert body["enrichment_stage2_provider"] == "ANTHROPIC"
    assert body["enrichment_stage2_api_key_set"] is True
    assert "enrichment_stage1_api_key" not in body
    assert "enrichment_stage2_api_key" not in body
    assert _stored(session).enrichment_stage1_api_key == "gemini-key"
    assert _stored(session).enrichment_stage2_api_key == "anthropic-key"


def test_setting_api_key_flips_flag_but_never_echoes_it(
    client: TestClient, session: Session
) -> None:
    body = client.patch("/api/config", json={"api_key": "sk-secret"}).json()
    assert body["api_key_set"] is True
    assert "api_key" not in body

    # The key is persisted but only ever observable server-side.
    assert _stored(session).api_key == "sk-secret"
    assert client.get("/api/config").json()["api_key_set"] is True


def test_clearing_api_key_with_empty_string(client: TestClient, session: Session) -> None:
    client.patch("/api/config", json={"api_key": "sk-secret"})
    body = client.patch("/api/config", json={"api_key": ""}).json()
    assert body["api_key_set"] is False
    assert _stored(session).api_key is None


def test_clearing_api_key_with_null(client: TestClient, session: Session) -> None:
    client.patch("/api/config", json={"api_key": "sk-secret"})
    body = client.patch("/api/config", json={"api_key": None}).json()
    assert body["api_key_set"] is False
    assert _stored(session).api_key is None


def test_rotating_api_key_replaces_the_stored_value(client: TestClient, session: Session) -> None:
    client.patch("/api/config", json={"api_key": "sk-first"})
    body = client.patch("/api/config", json={"api_key": "sk-second"}).json()
    assert body["api_key_set"] is True
    assert _stored(session).api_key == "sk-second"


def test_omitting_api_key_leaves_it_unchanged(client: TestClient, session: Session) -> None:
    client.patch("/api/config", json={"api_key": "sk-secret"})
    # A later update that doesn't mention the key must not disturb it.
    body = client.patch("/api/config", json={"extraction_rate_limit_per_minute": 64}).json()
    assert body["api_key_set"] is True
    assert body["extraction_rate_limit_per_minute"] == 64
    assert _stored(session).api_key == "sk-secret"


def test_rate_limit_below_one_is_rejected(client: TestClient) -> None:
    assert (
        client.patch("/api/config", json={"extraction_rate_limit_per_minute": 0}).status_code == 422
    )


def test_unknown_provider_is_rejected(client: TestClient) -> None:
    assert client.patch("/api/config", json={"ai_provider": "NOPE"}).status_code == 422
