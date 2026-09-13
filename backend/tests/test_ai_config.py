"""Persistence of the AI-configuration tables.

`AIProviderConfig` holds one row per provider (write-only key, display order,
usable model list); `AITaskAssignment` holds the explicit (role, provider, model)
rows, with an ordered sequence for the recipe-ingredient role. The data migration
itself is covered in test_ai_config_migration.py.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai_config import AIProviderConfig, AITaskAssignment
from app.models.enums import AIProvider, ModelRole
from app.services.ai import (
    ai_ready,
    ocr_ready,
    resolve_embeddings,
    resolve_ingredient_chain,
    resolve_task,
    set_task_assignment,
    upsert_provider_config,
)


def test_provider_config_round_trip(session: Session) -> None:
    session.add(
        AIProviderConfig(
            provider=AIProvider.GEMINI,
            api_key="sk-gemini",
            display_order=0,
            model_ids=["gemini-2.5-flash", "gemini-2.5-flash-lite"],
        )
    )
    session.commit()

    row = session.get(AIProviderConfig, AIProvider.GEMINI)
    assert row is not None
    assert row.api_key == "sk-gemini"
    assert row.display_order == 0
    assert row.model_ids == ["gemini-2.5-flash", "gemini-2.5-flash-lite"]


def test_provider_config_key_is_nullable_for_unconfigured_providers(
    session: Session,
) -> None:
    session.add(AIProviderConfig(provider=AIProvider.ANTHROPIC, display_order=1, model_ids=[]))
    session.commit()

    row = session.get(AIProviderConfig, AIProvider.ANTHROPIC)
    assert row is not None
    assert row.api_key is None


def test_task_assignment_ordering_for_ingredient_fallbacks(session: Session) -> None:
    session.add_all(
        [
            AITaskAssignment(
                role=ModelRole.RECIPE_INGREDIENTS,
                position=0,
                provider=AIProvider.GEMINI,
                model_id="gemini-2.5-flash-lite",
            ),
            AITaskAssignment(
                role=ModelRole.RECIPE_INGREDIENTS,
                position=1,
                provider=AIProvider.ANTHROPIC,
                model_id="claude-haiku-4-5-20251001",
            ),
            AITaskAssignment(
                role=ModelRole.ASSISTANT,
                position=0,
                provider=AIProvider.ANTHROPIC,
                model_id="claude-sonnet-5",
            ),
        ]
    )
    session.commit()

    chain = session.scalars(
        select(AITaskAssignment)
        .where(AITaskAssignment.role == ModelRole.RECIPE_INGREDIENTS)
        .order_by(AITaskAssignment.position)
    ).all()
    assert [(row.provider, row.model_id) for row in chain] == [
        (AIProvider.GEMINI, "gemini-2.5-flash-lite"),
        (AIProvider.ANTHROPIC, "claude-haiku-4-5-20251001"),
    ]


def _keyed(session: Session, provider: AIProvider, key: str = "k") -> None:
    upsert_provider_config(session, provider, api_key=key)
    session.commit()


def test_unassigned_task_uses_first_eligible_provider_in_order(session: Session) -> None:
    _keyed(session, AIProvider.OPENROUTER)
    _keyed(session, AIProvider.GEMINI)

    resolved = resolve_task(session, ModelRole.ASSISTANT)
    assert resolved is not None
    # Catalogue order (Anthropic, Gemini, OpenRouter) — Anthropic is keyless, so
    # Gemini (order 1) beats OpenRouter (order 2).
    assert resolved.provider.name == "GEMINI"
    assert resolved.model == "gemini-2.5-flash"


def test_explicit_assignment_beats_default_order(session: Session) -> None:
    _keyed(session, AIProvider.GEMINI)
    _keyed(session, AIProvider.ANTHROPIC)
    set_task_assignment(
        session,
        ModelRole.ASSISTANT,
        [(AIProvider.ANTHROPIC, "claude-sonnet-5")],
    )
    session.commit()

    resolved = resolve_task(session, ModelRole.ASSISTANT)
    assert resolved is not None
    assert resolved.provider.name == "ANTHROPIC"
    assert resolved.model == "claude-sonnet-5"


def test_assignment_to_a_keyless_provider_falls_back_to_default(
    session: Session,
) -> None:
    _keyed(session, AIProvider.GEMINI)
    upsert_provider_config(session, AIProvider.ANTHROPIC)
    set_task_assignment(
        session,
        ModelRole.ASSISTANT,
        [(AIProvider.ANTHROPIC, "claude-sonnet-5")],
    )
    session.commit()

    resolved = resolve_task(session, ModelRole.ASSISTANT)
    assert resolved is not None
    assert resolved.provider.name == "GEMINI"


def test_unresolvable_task_returns_none(session: Session) -> None:
    assert resolve_task(session, ModelRole.ASSISTANT) is None
    assert resolve_ingredient_chain(session) == []
    assert resolve_embeddings(session) is None
    assert ai_ready(session) is False
    assert ocr_ready(session) is False


def test_ocr_defaults_to_gemini(session: Session) -> None:
    _keyed(session, AIProvider.ANTHROPIC)
    _keyed(session, AIProvider.GEMINI)

    resolved = resolve_task(session, ModelRole.OCR)
    assert resolved is not None
    assert resolved.provider.name == "GEMINI"
    assert ocr_ready(session) is True


def test_ingredient_chain_returns_the_ordered_fallback_list(
    session: Session,
) -> None:
    _keyed(session, AIProvider.GEMINI)
    _keyed(session, AIProvider.ANTHROPIC)
    set_task_assignment(
        session,
        ModelRole.RECIPE_INGREDIENTS,
        [
            (AIProvider.GEMINI, "gemini-2.5-flash-lite"),
            (AIProvider.ANTHROPIC, "claude-haiku-4-5-20251001"),
        ],
    )
    session.commit()

    chain = resolve_ingredient_chain(session)
    assert [(entry.provider.name, entry.model) for entry in chain] == [
        ("GEMINI", "gemini-2.5-flash-lite"),
        ("ANTHROPIC", "claude-haiku-4-5-20251001"),
    ]


def test_ingredient_chain_without_assignment_is_the_single_default(
    session: Session,
) -> None:
    _keyed(session, AIProvider.GEMINI)

    chain = resolve_ingredient_chain(session)
    assert len(chain) == 1
    assert chain[0].provider.name == "GEMINI"
    assert chain[0].model == "gemini-2.5-flash-lite"


def test_embeddings_need_an_embedding_capable_provider(session: Session) -> None:
    _keyed(session, AIProvider.ANTHROPIC)
    assert resolve_embeddings(session) is None

    _keyed(session, AIProvider.GEMINI)
    assert resolve_embeddings(session) is not None
    assert resolve_embeddings(session).name == "GEMINI"


def test_ai_ready_needs_a_key(session: Session) -> None:
    upsert_provider_config(session, AIProvider.GEMINI)
    session.commit()
    assert ai_ready(session) is False

    _keyed(session, AIProvider.GEMINI)
    assert ai_ready(session) is True
