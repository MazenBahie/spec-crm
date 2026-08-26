"""Ticket-management HTTP routes.

Service-layer errors are translated centrally by the handlers registered in
``app.main``; these handlers keep the route bodies free of try/except noise.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
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
from app.services import tickets as svc

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
    ticket_id: uuid.UUID, payload: TicketStatusChange, db: DbDep
) -> TicketRead:
    return TicketRead.model_validate(svc.change_status(db, ticket_id, payload))


@router.post("/tickets/{ticket_id}/assignment", response_model=TicketRead)
def assign_ticket(ticket_id: uuid.UUID, payload: TicketAssignment, db: DbDep) -> TicketRead:
    return TicketRead.model_validate(svc.assign_ticket(db, ticket_id, payload))


@router.post("/tickets/{ticket_id}/escalate", response_model=TicketRead)
def escalate_ticket(
    ticket_id: uuid.UUID, payload: TicketEscalation, db: DbDep
) -> TicketRead:
    return TicketRead.model_validate(svc.escalate_ticket(db, ticket_id, payload))


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
