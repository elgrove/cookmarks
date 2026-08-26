"""The assistant's chat surface: conversations, their history, and the streaming turn.

Server-side history is authoritative. The chat endpoint keeps only the newest message
off the wire and rebuilds everything before it from the stored turns, so the browser
cannot rewrite what was said (Pydantic AI's documented trust model for UI adapters).
"""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic_ai.agent import AgentRunResult
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.ui.vercel_ai.request_types import TextUIPart, UIMessage
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import CurrentUser
from app.db import SessionDep
from app.models.assistant import AssistantConversation, AssistantTurn
from app.models.base import utcnow
from app.schemas.assistant import ConversationDetail, ConversationSummary
from app.services.assistant import AssistantDeps, build_agent

router = APIRouter(tags=["assistant"])

# The Vercel AI SDK major the frontend runs (`ai` 7.x); v7's data-stream wire equals v6's.
SDK_VERSION = 7

# An untitled conversation takes its name from the opening message, trimmed to a
# glanceable length. No AI call — the first thing asked is a good enough label.
TITLE_LIMIT = 80


def _owned(session: Session, conversation_id: uuid.UUID, user_id: uuid.UUID) -> AssistantConversation:
    """A conversation the caller owns, or 404 — another user's is indistinguishable
    from one that does not exist."""
    conversation = session.scalar(
        select(AssistantConversation)
        .where(
            AssistantConversation.id == conversation_id,
            AssistantConversation.user_id == user_id,
        )
        .options(selectinload(AssistantConversation.turns))
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return conversation


def _history(conversation: AssistantConversation) -> list[ModelMessage]:
    """Every stored turn, concatenated back into one Pydantic AI message history."""
    stored: list[Any] = []
    for turn in conversation.turns:
        stored.extend(turn.messages)
    return ModelMessagesTypeAdapter.validate_python(stored)


def _first_text(message: UIMessage) -> str:
    return " ".join(part.text for part in message.parts if isinstance(part, TextUIPart)).strip()


@router.post(
    "/assistant/conversations",
    response_model=ConversationSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(session: SessionDep, user: CurrentUser) -> ConversationSummary:
    conversation = AssistantConversation(user_id=user.id)
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return ConversationSummary.model_validate(conversation)


@router.get("/assistant/conversations", response_model=list[ConversationSummary])
def list_conversations(session: SessionDep, user: CurrentUser) -> list[ConversationSummary]:
    rows = session.scalars(
        select(AssistantConversation)
        .where(AssistantConversation.user_id == user.id)
        .order_by(AssistantConversation.updated_at.desc())
    ).all()
    return [ConversationSummary.model_validate(row) for row in rows]


@router.get("/assistant/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> ConversationDetail:
    conversation = _owned(session, conversation_id, user.id)
    messages = VercelAIAdapter.dump_messages(_history(conversation))
    return ConversationDetail(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[m.model_dump(mode="json", by_alias=True) for m in messages],
    )


@router.delete(
    "/assistant/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_conversation(
    conversation_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> Response:
    session.delete(_owned(session, conversation_id, user.id))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/assistant/conversations/{conversation_id}/chat")
async def chat(
    conversation_id: uuid.UUID, request: Request, session: SessionDep, user: CurrentUser
) -> Response:
    conversation = _owned(session, conversation_id, user.id)
    agent = build_agent(session)
    if agent is None:
        raise HTTPException(
            status_code=409,
            detail="no AI provider is configured — set one up in Admin Settings",
        )
    adapter = await VercelAIAdapter[AssistantDeps, str].from_request(
        request, agent=agent, sdk_version=SDK_VERSION
    )
    # Server-side history is authoritative: everything but the newest message is
    # dropped on the floor and replaced by what we stored.
    adapter.run_input.messages = adapter.run_input.messages[-1:]
    history = _history(conversation)
    if conversation.title is None and adapter.run_input.messages:
        conversation.title = _first_text(adapter.run_input.messages[0])[:TITLE_LIMIT] or None
        session.commit()

    async def persist(result: AgentRunResult[Any]) -> None:
        # Everything the run added on top of the history we loaded — which includes the
        # incoming user message, since the adapter feeds that in as history too, so
        # `new_messages()` would leave it out and the question would vanish from the record.
        added = result.all_messages()[len(history) :]
        usage = result.usage
        session.add(
            AssistantTurn(
                conversation_id=conversation.id,
                messages=ModelMessagesTypeAdapter.dump_python(added, mode="json"),
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cost_usd=usage.cost,
            )
        )
        conversation.updated_at = utcnow()
        session.commit()

    return adapter.streaming_response(
        adapter.run_stream(
            message_history=history,
            deps=AssistantDeps(session=session, user_id=user.id),
            on_complete=persist,
        )
    )
