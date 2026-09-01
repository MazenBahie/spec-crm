"""AI-feature HTTP routes (stories 10 and 12 share this file).

Every route here returns a value for an agent to review -- none of them
create, update, or send anything. Agent-scoped at router level, like
quick_replies.py: every route is 401 without a valid X-Agent-Id.

Grouped under their own router rather than folded into tickets.py for the
same reason /tickets/{ticket_id}/messages lives in channels.py, not
tickets.py: the sub-resource is a distinct domain concern from core ticket
CRUD, and multiple AI endpoints landing here across stories would otherwise
keep growing an already-large tickets.py.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import CurrentAgent, get_current_agent
from app.db.session import get_db
from app.schemas.ai import SuggestedReplyRead
from app.schemas.knowledge_base import ArticleSummary
from app.services.ai import suggested_replies as suggested_replies_svc
from app.services.ai import suggested_solutions as suggested_solutions_svc

router = APIRouter(
    prefix="/tickets/{ticket_id}/ai",
    tags=["ai"],
    dependencies=[Depends(get_current_agent)],
)

DbDep = Annotated[Session, Depends(get_db)]


@router.post("/suggested-reply", response_model=SuggestedReplyRead)
def suggest_reply(
    ticket_id: uuid.UUID, db: DbDep, agent: CurrentAgent
) -> SuggestedReplyRead:
    """Draft a reply from the ticket + thread. Never persisted, never sent."""
    return SuggestedReplyRead(draft=suggested_replies_svc.suggest_reply(db, ticket_id))


@router.get("/suggested-solutions", response_model=list[ArticleSummary])
def get_suggested_solutions(
    ticket_id: uuid.UUID,
    db: DbDep,
    agent: CurrentAgent,
    limit: Annotated[int, Query(ge=1, le=10)] = 5,
) -> list[ArticleSummary]:
    """Up to `limit` published KB articles that might resolve this ticket.

    Read-only and side-effect-free, so GET (not POST): every input fits in
    the path/query string, matching GET /api/kb/articles?q=....
    """
    articles = suggested_solutions_svc.suggest_solutions(db, ticket_id, limit=limit)
    return [ArticleSummary.model_validate(a) for a in articles]
