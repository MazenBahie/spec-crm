"""Customer-portal AI chatbot routes. Every route requires a valid, active
portal session (CurrentPortalUser) -- there is no anonymous chat."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps_portal import CurrentPortalUser
from app.db.session import get_db
from app.schemas.chatbot import (
    ChatbotMessageCreate,
    ChatbotMessageRead,
    ChatbotSessionRead,
    ChatTurnRead,
)
from app.services.ai import chatbot as svc
from app.services.ai.provider import AIProvider, get_ai_provider

router = APIRouter(prefix="/portal/chat", tags=["portal-chat"])

DbDep = Annotated[Session, Depends(get_db)]
ProviderDep = Annotated[AIProvider, Depends(get_ai_provider)]


@router.post("/sessions", response_model=ChatbotSessionRead)
def start_session(db: DbDep, portal_user: CurrentPortalUser) -> ChatbotSessionRead:
    """Get-or-create: 200 either way, since "created a new one" vs. "found the
    existing one" has no product meaning to the caller."""
    session = svc.get_or_create_session(db, portal_user.id)
    return ChatbotSessionRead.model_validate(session)


@router.get("/sessions/{session_id}/messages", response_model=list[ChatbotMessageRead])
def list_messages(
    session_id: uuid.UUID, db: DbDep, portal_user: CurrentPortalUser
) -> list[ChatbotMessageRead]:
    messages = svc.list_messages(db, session_id, portal_user.id)
    return [ChatbotMessageRead.model_validate(m) for m in messages]


@router.post("/sessions/{session_id}/messages", response_model=ChatTurnRead)
def send_message(
    session_id: uuid.UUID,
    payload: ChatbotMessageCreate,
    db: DbDep,
    portal_user: CurrentPortalUser,
    provider: ProviderDep,
) -> ChatTurnRead:
    user_message, assistant_message = svc.send_message(
        db, session_id, portal_user.id, payload.content, provider=provider
    )
    return ChatTurnRead(
        user_message=ChatbotMessageRead.model_validate(user_message),
        assistant_message=ChatbotMessageRead.model_validate(assistant_message),
    )
