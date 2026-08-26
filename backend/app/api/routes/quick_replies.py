"""Quick-reply (canned response) HTTP routes.

Agent-scoped at router level. The list is the union of the team library and the
caller's own personal replies; another agent's personal replies are never
returned, and mutating one is a 403.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentAgent, get_current_agent
from app.db.session import get_db
from app.schemas.agent import QuickReplyCreate, QuickReplyRead, QuickReplyUpdate
from app.services import quick_replies as svc

router = APIRouter(tags=["quick-replies"], dependencies=[Depends(get_current_agent)])

DbDep = Annotated[Session, Depends(get_db)]


@router.get("/quick-replies", response_model=list[QuickReplyRead])
def list_quick_replies(db: DbDep, agent: CurrentAgent) -> list[QuickReplyRead]:
    return [QuickReplyRead.model_validate(r) for r in svc.list_visible(db, agent.id)]


@router.post(
    "/quick-replies", response_model=QuickReplyRead, status_code=status.HTTP_201_CREATED
)
def create_quick_reply(
    payload: QuickReplyCreate, db: DbDep, agent: CurrentAgent
) -> QuickReplyRead:
    """Create a reply. Ownership follows ``scope`` and is never client-supplied."""
    return QuickReplyRead.model_validate(svc.create(db, agent.id, payload))


@router.patch("/quick-replies/{reply_id}", response_model=QuickReplyRead)
def update_quick_reply(
    reply_id: uuid.UUID, payload: QuickReplyUpdate, db: DbDep, agent: CurrentAgent
) -> QuickReplyRead:
    return QuickReplyRead.model_validate(svc.update(db, reply_id, agent.id, payload))


@router.delete("/quick-replies/{reply_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_quick_reply(
    reply_id: uuid.UUID, db: DbDep, agent: CurrentAgent
) -> Response:
    svc.delete(db, reply_id, agent.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
