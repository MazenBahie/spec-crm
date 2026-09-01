"""Pydantic v2 schemas for the ticket-management API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.customer import CustomerRead, NonEmptyStr

TicketStatus = Literal[
    "open", "triaged", "in_progress", "waiting_customer", "resolved", "closed"
]
TicketPriority = Literal["low", "normal", "high", "urgent"]
TicketEventType = Literal[
    "created",
    "status_changed",
    "priority_changed",
    "category_changed",
    "assigned",
    "unassigned",
    "escalated",
    "commented",
    "ai_summary_generated",
    "ai_category_suggested",
]


# --------------------------------------------------------------------------- #
# Agents
# --------------------------------------------------------------------------- #
class AgentBase(BaseModel):
    display_name: NonEmptyStr
    email: str | None = None
    is_active: bool = True


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    display_name: NonEmptyStr | None = None
    email: str | None = None
    is_active: bool | None = None


class AgentRead(AgentBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime


# --------------------------------------------------------------------------- #
# Ticket categories
# --------------------------------------------------------------------------- #
class TicketCategoryBase(BaseModel):
    name: NonEmptyStr
    description: str | None = None
    default_priority: TicketPriority = "normal"
    is_active: bool = True


class TicketCategoryCreate(TicketCategoryBase):
    pass


class TicketCategoryUpdate(BaseModel):
    name: NonEmptyStr | None = None
    description: str | None = None
    default_priority: TicketPriority | None = None
    is_active: bool | None = None


class TicketCategoryRead(TicketCategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime


# --------------------------------------------------------------------------- #
# Tickets
# --------------------------------------------------------------------------- #
class TicketCreate(BaseModel):
    customer_id: uuid.UUID
    subject: NonEmptyStr
    description: str = ""
    category_id: uuid.UUID | None = None
    # None means "inherit the category's default_priority" (or "normal" with
    # no category) — resolved in app.services.tickets.create_ticket.
    priority: TicketPriority | None = None
    assignee_id: uuid.UUID | None = None
    due_at: datetime | None = None


class TicketUpdate(BaseModel):
    """Partial update of the editable fields only.

    ``status`` and ``assignee_id`` are deliberately absent here — they are
    only mutable through POST /tickets/{id}/status and
    POST /tickets/{id}/assignment, so every change to them is guaranteed to
    append a ticket_events row.
    """

    subject: NonEmptyStr | None = None
    description: str | None = None
    category_id: uuid.UUID | None = None
    priority: TicketPriority | None = None
    due_at: datetime | None = None


class TicketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reference: str
    customer_id: uuid.UUID
    category_id: uuid.UUID | None
    ai_suggested_category_id: uuid.UUID | None
    assignee_id: uuid.UUID | None
    subject: str
    description: str
    status: TicketStatus
    priority: TicketPriority
    escalation_level: int
    escalated_at: datetime | None
    due_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    is_overdue: bool
    ai_summary: str | None
    ai_summary_generated_at: datetime | None


class TicketDetailRead(TicketRead):
    """Ticket plus eagerly loaded customer, category, and assignee."""

    customer: CustomerRead
    category: TicketCategoryRead | None
    ai_suggested_category: TicketCategoryRead | None
    assignee: AgentRead | None


# --------------------------------------------------------------------------- #
# Ticket events
# --------------------------------------------------------------------------- #
class TicketEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    event_type: TicketEventType
    field: str | None
    old_value: str | None
    new_value: str | None
    comment: str | None
    actor: str | None
    created_at: datetime


class TicketCommentCreate(BaseModel):
    comment: NonEmptyStr
    actor: str | None = None


# --------------------------------------------------------------------------- #
# Action payloads
# --------------------------------------------------------------------------- #
class TicketStatusChange(BaseModel):
    status: TicketStatus
    comment: str | None = None
    actor: str | None = None


class TicketAssignment(BaseModel):
    assignee_id: uuid.UUID | None
    actor: str | None = None


class TicketEscalation(BaseModel):
    comment: str | None = None
    actor: str | None = None
    raise_priority: bool = True


TicketDetailRead.model_rebuild()
