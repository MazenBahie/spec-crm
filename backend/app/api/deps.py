"""Shared FastAPI dependencies.

**Placeholder for real authentication.** ``get_current_agent`` trusts an
``X-Agent-Id`` header outright — any caller who knows an agent's uuid is that
agent. This exists only so the dashboard, task, quick-reply and note endpoints
have a "who am I" to scope by; a follow-up auth story replaces the header with a
verified session or token and reconciles it with ``Interaction.author`` and
``TicketEvent.actor``, which are still free text.

Kept out of ``app.services`` on purpose: the service layer stays FastAPI-free
and takes an ``agent_id`` argument instead.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.ticket import Agent

AGENT_HEADER = "X-Agent-Id"

_UNAUTHORISED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail=f"a valid {AGENT_HEADER} header is required",
)


def _lookup(db: Session, raw: str | None) -> Agent | None:
    """Resolve a header value to an active agent, or None."""
    if raw is None or not raw.strip():
        return None
    try:
        agent_id = uuid.UUID(raw.strip())
    except ValueError:
        return None
    agent = db.get(Agent, agent_id)
    if agent is None or not agent.is_active:
        return None
    return agent


def get_current_agent(
    db: Annotated[Session, Depends(get_db)],
    x_agent_id: Annotated[str | None, Header(alias=AGENT_HEADER)] = None,
) -> Agent:
    """The agent making this request, or 401.

    A missing header, an unparseable id, an unknown agent and a deactivated
    agent are all the same answer — 401 — so the frontend has one branch to
    handle: clear the cached id and ask who is at the keyboard.
    """
    agent = _lookup(db, x_agent_id)
    if agent is None:
        raise _UNAUTHORISED
    return agent


def get_optional_agent(
    db: Annotated[Session, Depends(get_db)],
    x_agent_id: Annotated[str | None, Header(alias=AGENT_HEADER)] = None,
) -> Agent | None:
    """The agent making this request, or None — never raises.

    For pre-existing routes that must keep working unauthenticated (replying on
    a ticket, changing its status) but can attribute the activity-feed entry to
    a real agent when the caller does identify itself.
    """
    return _lookup(db, x_agent_id)


def require_agent_id(
    agent: Annotated[Agent, Depends(get_current_agent)],
) -> uuid.UUID:
    """Just the id, for handlers that never touch the rest of the row."""
    return agent.id


CurrentAgent = Annotated[Agent, Depends(get_current_agent)]
OptionalAgent = Annotated[Agent | None, Depends(get_optional_agent)]
CurrentAgentId = Annotated[uuid.UUID, Depends(require_agent_id)]
