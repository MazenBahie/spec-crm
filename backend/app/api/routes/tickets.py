"""Ticket-management HTTP routes.

Service-layer errors are translated centrally by the handlers registered in
``app.main``; these handlers keep the route bodies free of try/except noise.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentAgent, OptionalAgent
from app.db.session import get_db
from app.schemas.agent import TicketNoteCreate, TicketNoteRead
from app.schemas.customer import Page
from app.schemas.ticket import (
    AgentCreate,
    AgentRead,
    AgentUpdate,
    TicketAssignment,
    TicketCategoryCreate,
    TicketCategoryRead,
    TicketCategoryUpdate,
    TicketCommentCreate,
    TicketCreate,
    TicketDetailRead,
    TicketEscalation,
    TicketEventRead,
    TicketPriority,
    TicketRead,
    TicketStatus,
    TicketStatusChange,
    TicketUpdate,
)
from app.services import ticket_notes as notes_svc
from app.services import tickets as svc
from app.services.ai import categorization as ai_categorization
from app.services.ai import ticket_summary as ai_summary_svc

router = APIRouter(tags=["tickets"])

DbDep = Annotated[Session, Depends(get_db)]


# --------------------------------------------------------------------------- #
# Tickets
# --------------------------------------------------------------------------- #
@router.get("/tickets", response_model=Page[TicketRead])
def list_tickets(
    db: DbDep,
    q: Annotated[str | None, Query(description="Match reference, subject, or description")] = None,
    status_filter: Annotated[TicketStatus | None, Query(alias="status")] = None,
    priority_filter: Annotated[TicketPriority | None, Query(alias="priority")] = None,
    customer_id: uuid.UUID | None = None,
    assignee_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    unassigned: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[TicketRead]:
    items, total = svc.list_tickets(
        db,
        q=q,
        status=status_filter,
        priority=priority_filter,
        customer_id=customer_id,
        assignee_id=assignee_id,
        category_id=category_id,
        unassigned=unassigned,
        limit=limit,
        offset=offset,
    )
    return Page[TicketRead](
        items=[TicketRead.model_validate(t) for t in items], total=total
    )


@router.post("/tickets", response_model=TicketRead, status_code=status.HTTP_201_CREATED)
def create_ticket(payload: TicketCreate, db: DbDep) -> TicketRead:
    return TicketRead.model_validate(svc.create_ticket(db, payload))


@router.get("/tickets/{ticket_id}", response_model=TicketDetailRead)
def get_ticket(ticket_id: uuid.UUID, db: DbDep) -> TicketDetailRead:
    ticket = svc.get_ticket(db, ticket_id, with_relations=True)
    return TicketDetailRead.model_validate(ticket)


@router.patch("/tickets/{ticket_id}", response_model=TicketRead)
def update_ticket(ticket_id: uuid.UUID, payload: TicketUpdate, db: DbDep) -> TicketRead:
    return TicketRead.model_validate(svc.update_ticket(db, ticket_id, payload))


@router.delete("/tickets/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ticket(ticket_id: uuid.UUID, db: DbDep) -> Response:
    svc.delete_ticket(db, ticket_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/tickets/{ticket_id}/status", response_model=TicketRead)
def change_ticket_status(
    ticket_id: uuid.UUID, payload: TicketStatusChange, db: DbDep, agent: OptionalAgent
) -> TicketRead:
    """Move a ticket through the workflow.

    ``X-Agent-Id`` is optional here — this route predates agent context and
    stays open. Supplying it only names the actor in the team activity feed.
    """
    return TicketRead.model_validate(
        svc.change_status(
            db, ticket_id, payload, actor_agent_id=agent.id if agent else None
        )
    )


@router.post("/tickets/{ticket_id}/assignment", response_model=TicketRead)
def assign_ticket(
    ticket_id: uuid.UUID, payload: TicketAssignment, db: DbDep, agent: OptionalAgent
) -> TicketRead:
    """(Re)assign a ticket. ``X-Agent-Id`` is optional, as on the status route."""
    return TicketRead.model_validate(
        svc.assign_ticket(
            db, ticket_id, payload, actor_agent_id=agent.id if agent else None
        )
    )


@router.post("/tickets/{ticket_id}/escalate", response_model=TicketRead)
def escalate_ticket(
    ticket_id: uuid.UUID, payload: TicketEscalation, db: DbDep
) -> TicketRead:
    return TicketRead.model_validate(svc.escalate_ticket(db, ticket_id, payload))


# --------------------------------------------------------------------------- #
# AI summary (agent-only — costs a real API call, so it is never automatic)
# --------------------------------------------------------------------------- #
@router.post("/tickets/{ticket_id}/ai/summary", response_model=TicketRead)
def regenerate_ticket_summary(
    ticket_id: uuid.UUID, db: DbDep, agent: CurrentAgent
) -> TicketRead:
    """Regenerate and persist the AI summary. Explicit action only — see
    Story Goal on why this is never triggered by a page load."""
    return TicketRead.model_validate(ai_summary_svc.generate_summary(db, ticket_id))


@router.post(
    "/tickets/{ticket_id}/ai/suggested-category", response_model=TicketDetailRead
)
def recompute_suggested_category(ticket_id: uuid.UUID, db: DbDep) -> TicketDetailRead:
    """Recompute the AI category suggestion on demand.

    Unlike the best-effort hook in create_ticket, this is an explicit,
    single-purpose agent action with nothing else at stake: if the provider
    is unavailable or misconfigured, AIProviderError is allowed to propagate
    rather than being swallowed, so the agent who clicked "Recompute" sees
    that it failed instead of silently seeing nothing change. The
    AIProviderError -> 502 handler is registered once in app.main (Story 09).
    """
    ai_categorization.suggest_category(db, ticket_id)
    ticket = svc.get_ticket(db, ticket_id, with_relations=True)
    return TicketDetailRead.model_validate(ticket)


# --------------------------------------------------------------------------- #
# Ticket events (append-only — no PATCH/DELETE)
# --------------------------------------------------------------------------- #
@router.get("/tickets/{ticket_id}/events", response_model=Page[TicketEventRead])
def list_ticket_events(
    ticket_id: uuid.UUID,
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[TicketEventRead]:
    items, total = svc.list_events(db, ticket_id, limit=limit, offset=offset)
    return Page[TicketEventRead](
        items=[TicketEventRead.model_validate(e) for e in items], total=total
    )


@router.post(
    "/tickets/{ticket_id}/events",
    response_model=TicketEventRead,
    status_code=status.HTTP_201_CREATED,
)
def add_ticket_comment(
    ticket_id: uuid.UUID, payload: TicketCommentCreate, db: DbDep
) -> TicketEventRead:
    return TicketEventRead.model_validate(svc.add_comment(db, ticket_id, payload))


# --------------------------------------------------------------------------- #
# Internal notes (agent-only — never delivered to the customer)
#
# Unlike the rest of this router these two require a valid X-Agent-Id: a note
# has an author, and "who said this" is the point of an internal thread.
# --------------------------------------------------------------------------- #
@router.get("/tickets/{ticket_id}/notes", response_model=Page[TicketNoteRead])
def list_ticket_notes(
    ticket_id: uuid.UUID,
    db: DbDep,
    agent: CurrentAgent,
    limit: Annotated[int, Query(ge=1, le=200)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[TicketNoteRead]:
    items, total = notes_svc.list_notes(db, ticket_id, limit=limit, offset=offset)
    return Page[TicketNoteRead](items=[_note_out(n) for n in items], total=total)


@router.post(
    "/tickets/{ticket_id}/notes",
    response_model=TicketNoteRead,
    status_code=status.HTTP_201_CREATED,
)
def add_ticket_note(
    ticket_id: uuid.UUID, payload: TicketNoteCreate, db: DbDep, agent: CurrentAgent
) -> TicketNoteRead:
    """Post an internal note.

    Notes live in their own table and no channel driver is reachable from this
    path, so there is no way for one to leave the building.
    """
    return _note_out(notes_svc.add_note(db, ticket_id, agent.id, payload))


def _note_out(note) -> TicketNoteRead:
    """Flatten the author relationship so the thread renders without a lookup."""
    out = TicketNoteRead.model_validate(note)
    out.author_display_name = note.author.display_name if note.author else None
    return out


# --------------------------------------------------------------------------- #
# Per-customer ticket list
# --------------------------------------------------------------------------- #
@router.get("/customers/{customer_id}/tickets", response_model=Page[TicketRead])
def list_customer_tickets(
    customer_id: uuid.UUID,
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[TicketRead]:
    items, total = svc.list_customer_tickets(db, customer_id, limit=limit, offset=offset)
    return Page[TicketRead](
        items=[TicketRead.model_validate(t) for t in items], total=total
    )


# --------------------------------------------------------------------------- #
# Ticket categories
# --------------------------------------------------------------------------- #
@router.get("/ticket-categories", response_model=list[TicketCategoryRead])
def list_ticket_categories(
    db: DbDep, active_only: bool = False
) -> list[TicketCategoryRead]:
    return [
        TicketCategoryRead.model_validate(c)
        for c in svc.list_categories(db, active_only=active_only)
    ]


@router.post(
    "/ticket-categories",
    response_model=TicketCategoryRead,
    status_code=status.HTTP_201_CREATED,
)
def create_ticket_category(
    payload: TicketCategoryCreate, db: DbDep
) -> TicketCategoryRead:
    return TicketCategoryRead.model_validate(svc.create_category(db, payload))


@router.patch("/ticket-categories/{category_id}", response_model=TicketCategoryRead)
def update_ticket_category(
    category_id: uuid.UUID, payload: TicketCategoryUpdate, db: DbDep
) -> TicketCategoryRead:
    return TicketCategoryRead.model_validate(
        svc.update_category(db, category_id, payload)
    )


@router.delete("/ticket-categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ticket_category(category_id: uuid.UUID, db: DbDep) -> Response:
    svc.delete_category(db, category_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- #
# Agents
# --------------------------------------------------------------------------- #
@router.get("/agents", response_model=list[AgentRead])
def list_agents(db: DbDep, active_only: bool = False) -> list[AgentRead]:
    return [AgentRead.model_validate(a) for a in svc.list_agents(db, active_only=active_only)]


@router.post("/agents", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
def create_agent(payload: AgentCreate, db: DbDep) -> AgentRead:
    return AgentRead.model_validate(svc.create_agent(db, payload))


@router.patch("/agents/{agent_id}", response_model=AgentRead)
def update_agent(agent_id: uuid.UUID, payload: AgentUpdate, db: DbDep) -> AgentRead:
    return AgentRead.model_validate(svc.update_agent(db, agent_id, payload))


@router.delete("/agents/{agent_id}", response_model=AgentRead)
def deactivate_agent(agent_id: uuid.UUID, db: DbDep) -> AgentRead:
    """Agents are never hard-deleted, so assignment history stays readable."""
    return AgentRead.model_validate(svc.deactivate_agent(db, agent_id))
