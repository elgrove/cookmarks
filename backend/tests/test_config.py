"""Behaviour of the AI configuration endpoints (GET/PATCH /api/config, GET /api/ai/readiness).

The defining contracts: API keys are write-only (set, rotate, clear — never
serialised, only an `api_key_set` flag per provider), partial updates leave
untouched sections alone, task assignments validate against the providers' usable
model lists, and a model in use cannot be removed.
"""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai_config import AIProviderConfig, AITaskAssignment
from app.models.enums import AIProvider, ModelRole


def _providers(body: dict) -> dict:
    return {row["provider"]: row for row in body["providers"]}


def test_read_config_seeds_providers_without_keys(client: TestClient) -> None:
    body = client.get("/api/config").json()
    providers = _providers(body)
    assert set(providers) == {"ANTHROPIC", "GEMINI", "OPENROUTER"}
    assert all(row["api_key_set"] is False for row in providers.values())
    assert all(row["model_ids"] for row in providers.values())
    assert [row["display_order"] for row in body["providers"]] == [0, 1, 2]
    assert body["task_assignments"] == []
    assert body["recommendations"]["GEMINI"]["ocr"] == "gemini-2.5-flash"
    assert body["extraction_rate_limit_per_minute"] == 256
    # No key material anywhere in the response.
    assert "api_key" not in str(body).replace("api_key_set", "")


def test_setting_a_provider_key_flips_the_flag_but_never_echoes_it(
    client: TestClient, session: Session
) -> None:
    body = client.patch(
        "/api/config",
        json={"provider_configs": [{"provider": "GEMINI", "api_key": "sk-secret"}]},
    ).json()
    assert _providers(body)["GEMINI"]["api_key_set"] is True
    assert "sk-secret" not in str(body)

    assert session.get(AIProviderConfig, AIProvider.GEMINI).api_key == "sk-secret"
    assert client.get("/api/config").json()["providers"][1]["api_key_set"] is True


def test_clearing_a_key_with_empty_string_or_null(client: TestClient, session: Session) -> None:
    client.patch(
        "/api/config",
        json={"provider_configs": [{"provider": "GEMINI", "api_key": "sk-secret"}]},
    )
    for clear in ("", None):
        body = client.patch(
            "/api/config",
            json={"provider_configs": [{"provider": "GEMINI", "api_key": clear}]},
        ).json()
        assert _providers(body)["GEMINI"]["api_key_set"] is False
    assert session.get(AIProviderConfig, AIProvider.GEMINI).api_key is None


def test_omitting_a_key_leaves_it_unchanged(client: TestClient, session: Session) -> None:
    client.patch(
        "/api/config",
        json={"provider_configs": [{"provider": "GEMINI", "api_key": "sk-secret"}]},
    )
    body = client.patch(
        "/api/config", json={"extraction_rate_limit_per_minute": 64}
    ).json()
    assert _providers(body)["GEMINI"]["api_key_set"] is True
    assert body["extraction_rate_limit_per_minute"] == 64
    assert session.get(AIProviderConfig, AIProvider.GEMINI).api_key == "sk-secret"


def test_rate_limit_below_one_is_rejected(client: TestClient) -> None:
    assert (
        client.patch("/api/config", json={"extraction_rate_limit_per_minute": 0}).status_code
        == 422
    )


def test_unknown_provider_is_rejected(client: TestClient) -> None:
    assert (
        client.patch(
            "/api/config", json={"provider_configs": [{"provider": "NOPE"}]}
        ).status_code
        == 422
    )


def test_duplicate_provider_entries_are_rejected(client: TestClient) -> None:
    response = client.patch(
        "/api/config",
        json={
            "provider_configs": [
                {"provider": "GEMINI", "api_key": "one"},
                {"provider": "GEMINI", "api_key": "two"},
            ]
        },
    )
    assert response.status_code == 422


def test_stub_provider_is_not_configurable(client: TestClient) -> None:
    assert (
        client.patch(
            "/api/config", json={"provider_configs": [{"provider": "STUB"}]}
        ).status_code
        == 422
    )


def test_provider_order_is_persisted(client: TestClient, session: Session) -> None:
    body = client.patch(
        "/api/config", json={"provider_order": ["OPENROUTER", "GEMINI", "ANTHROPIC"]}
    ).json()
    assert [row["provider"] for row in body["providers"]] == [
        "OPENROUTER",
        "GEMINI",
        "ANTHROPIC",
    ]
    orders = {
        row.provider: row.display_order
        for row in session.scalars(select(AIProviderConfig)).all()
    }
    assert orders == {
        AIProvider.OPENROUTER: 0,
        AIProvider.GEMINI: 1,
        AIProvider.ANTHROPIC: 2,
    }


def test_custom_model_can_be_added_and_assigned(client: TestClient, session: Session) -> None:
    client.patch(
        "/api/config",
        json={"provider_configs": [{"provider": "GEMINI", "add_models": ["gemini-x"]}]},
    )
    body = client.patch(
        "/api/config",
        json={
            "task_assignments": [
                {
                    "role": "assistant",
                    "entries": [{"provider": "GEMINI", "model_id": "gemini-x"}],
                }
            ]
        },
    ).json()
    assert body["task_assignments"] == [
        {"role": "assistant", "position": 0, "provider": "GEMINI", "model_id": "gemini-x"}
    ]
    stored = session.scalars(select(AITaskAssignment)).all()
    assert [(row.role, row.provider, row.model_id) for row in stored] == [
        (ModelRole.ASSISTANT, AIProvider.GEMINI, "gemini-x")
    ]


def test_assignment_to_an_unlisted_model_is_rejected(client: TestClient) -> None:
    response = client.patch(
        "/api/config",
        json={
            "task_assignments": [
                {
                    "role": "assistant",
                    "entries": [{"provider": "GEMINI", "model_id": "nope"}],
                }
            ]
        },
    )
    assert response.status_code == 422


def test_duplicate_model_removals_are_rejected(client: TestClient) -> None:
    assert (
        client.patch(
            "/api/config",
            json={
                "provider_configs": [
                    {
                        "provider": "GEMINI",
                        "remove_models": ["gemini-2.5-flash", "gemini-2.5-flash"],
                    }
                ]
            },
        ).status_code
        == 422
    )


def test_whitespace_key_is_not_a_configuration(client: TestClient, session: Session) -> None:
    body = client.patch(
        "/api/config",
        json={"provider_configs": [{"provider": "GEMINI", "api_key": "   "}]},
    ).json()
    assert _providers(body)["GEMINI"]["api_key_set"] is False
    assert session.get(AIProviderConfig, AIProvider.GEMINI).api_key is None
    assert client.get("/api/ai/readiness").json()["extraction_available"] is False


def test_key_whitespace_is_stripped(client: TestClient, session: Session) -> None:
    body = client.patch(
        "/api/config",
        json={"provider_configs": [{"provider": "GEMINI", "api_key": "  sk-secret  "}]},
    ).json()
    assert _providers(body)["GEMINI"]["api_key_set"] is True
    assert session.get(AIProviderConfig, AIProvider.GEMINI).api_key == "sk-secret"


def test_blank_and_duplicate_model_additions_are_rejected(client: TestClient) -> None:
    assert (
        client.patch(
            "/api/config",
            json={"provider_configs": [{"provider": "GEMINI", "add_models": ["  "]}]},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            "/api/config",
            json={
                "provider_configs": [
                    {"provider": "GEMINI", "add_models": ["gemini-2.5-flash"]}
                ]
            },
        ).status_code
        == 422
    )


def test_removing_a_model_in_use_is_rejected_until_reassigned(
    client: TestClient,
) -> None:
    client.patch(
        "/api/config",
        json={
            "task_assignments": [
                {
                    "role": "assistant",
                    "entries": [
                        {"provider": "GEMINI", "model_id": "gemini-2.5-flash-lite"}
                    ],
                }
            ]
        },
    )
    assert (
        client.patch(
            "/api/config",
            json={
                "provider_configs": [
                    {"provider": "GEMINI", "remove_models": ["gemini-2.5-flash-lite"]}
                ]
            },
        ).status_code
        == 422
    )
    # Reassigning frees the model for removal.
    client.patch(
        "/api/config",
        json={
            "task_assignments": [
                {
                    "role": "assistant",
                    "entries": [{"provider": "GEMINI", "model_id": "gemini-2.5-flash"}],
                }
            ]
        },
    )
    body = client.patch(
        "/api/config",
        json={
            "provider_configs": [
                {"provider": "GEMINI", "remove_models": ["gemini-2.5-flash-lite"]}
            ]
        },
    ).json()
    assert "gemini-2.5-flash-lite" not in _providers(body)["GEMINI"]["model_ids"]


def test_fallbacks_only_for_ingredient_parsing(client: TestClient) -> None:
    assert (
        client.patch(
            "/api/config",
            json={
                "task_assignments": [
                    {
                        "role": "assistant",
                        "entries": [
                            {"provider": "GEMINI", "model_id": "gemini-2.5-flash"},
                            {"provider": "ANTHROPIC", "model_id": "claude-sonnet-5"},
                        ],
                    }
                ]
            },
        ).status_code
        == 422
    )
    body = client.patch(
        "/api/config",
        json={
            "task_assignments": [
                {
                    "role": "recipe_ingredients",
                    "entries": [
                        {"provider": "GEMINI", "model_id": "gemini-2.5-flash-lite"},
                        {"provider": "ANTHROPIC", "model_id": "claude-haiku-4-5-20251001"},
                    ],
                }
            ]
        },
    ).json()
    ingredients = [
        row for row in body["task_assignments"] if row["role"] == "recipe_ingredients"
    ]
    assert [(row["position"], row["provider"]) for row in ingredients] == [
        (0, "GEMINI"),
        (1, "ANTHROPIC"),
    ]


def test_ocr_cannot_be_assigned_away_from_gemini(client: TestClient) -> None:
    assert (
        client.patch(
            "/api/config",
            json={
                "task_assignments": [
                    {
                        "role": "ocr",
                        "entries": [
                            {"provider": "ANTHROPIC", "model_id": "claude-sonnet-5"}
                        ],
                    }
                ]
            },
        ).status_code
        == 422
    )


def test_empty_entries_remove_an_assignment(client: TestClient, session: Session) -> None:
    client.patch(
        "/api/config",
        json={
            "task_assignments": [
                {
                    "role": "assistant",
                    "entries": [{"provider": "GEMINI", "model_id": "gemini-2.5-flash"}],
                }
            ]
        },
    )
    body = client.patch(
        "/api/config", json={"task_assignments": [{"role": "assistant", "entries": []}]}
    ).json()
    assert body["task_assignments"] == []
    assert session.scalars(select(AITaskAssignment)).all() == []


def test_readiness_tracks_keys(client: TestClient) -> None:
    assert client.get("/api/ai/readiness").json() == {
        "extraction_available": False,
        "assistant_available": False,
        "ocr_available": False,
    }
    client.patch(
        "/api/config",
        json={"provider_configs": [{"provider": "ANTHROPIC", "api_key": "sk-a"}]},
    )
    assert client.get("/api/ai/readiness").json() == {
        "extraction_available": True,
        "assistant_available": True,
        "ocr_available": False,
    }
    client.patch(
        "/api/config",
        json={"provider_configs": [{"provider": "GEMINI", "api_key": "sk-g"}]},
    )
    assert client.get("/api/ai/readiness").json() == {
        "extraction_available": True,
        "assistant_available": True,
        "ocr_available": True,
    }
