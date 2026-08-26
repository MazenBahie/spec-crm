"""Pydantic v2 schemas for the agent-dashboard API.

Ids are ``uuid.UUID`` throughout, matching every other table in this codebase —
``agents`` was introduced by the ticket story with a uuid primary key.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.customer import NonEmptyStr

AgentTaskStatus = Literal["open", "done"]
QuickReplyScope = Literal["personal", "team"]
ActivityEventType = Literal[
    "ticket.assigned",
    "ticket.status_changed",
    "ticket.replied",
    "note.added",
    "mention",
]


# --------------------------------------------------------------------------- #
# Tasks and reminders
# --------------------------------------------------------------------------- #
class AgentTaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    notes: str | None = None
    remind_at: datetime | None = None
    ticket_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None


class AgentTaskUpdate(BaseModel):
    """Partial update. ``status`` moves the task between open and done."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = None
    remind_at: datetime | None = None
    ticket_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    status: AgentTaskStatus | None = None


class AgentTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    title: str
    notes: str | None
    status: AgentTaskStatus
    remind_at: datetime | None
    ticket_id: uuid.UUID | None
    customer_id: uuid.UUID | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Quick replies
# --------------------------------------------------------------------------- #
class QuickReplyCreate(BaseModel):
    """``owner_agent_id`` is absent by design.

    Ownership is derived from the caller: a ``personal`` reply belongs to the
    agent creating it, a ``team`` reply belongs to nobody. Letting a client
    nominate an owner would be the only way to violate the scope invariant.
    """

    scope: QuickReplyScope = "personal"
    title: str = Field(min_length=1, max_length=120)
    body: NonEmptyStr
    shortcut: str | None = Field(default=None, max_length=40)


class QuickReplyUpdate(BaseModel):
    scope: QuickReplyScope | None = None
    title: str | None = Field(default=None, min_length=1, max_length=120)
    body: NonEmptyStr | None = None
    shortcut: str | None = Field(default=None, max_length=40)


class QuickReplyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    scope: QuickReplyScope
    owner_agent_id: uuid.UUID | None
    shortcut: str | None
    title: str
    body: str
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _scope_matches_owner(self) -> QuickReplyRead:
        """Mirror of the DB CHECK, so a bad row cannot be served silently."""
        if (self.scope == "personal") != (self.owner_agent_id is not None):
            raise ValueError(
                f"quick reply {self.id} violates the scope/owner invariant"
            )
        return self


# --------------------------------------------------------------------------- #
# Internal ticket notes
# --------------------------------------------------------------------------- #
class TicketNoteCreate(BaseModel):
    body: NonEmptyStr


class TicketNoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    author_agent_id: uuid.UUID | None
    author_display_name: str | None = None
    body: str
    created_at: datetime


# --------------------------------------------------------------------------- #
# Activity feed
# --------------------------------------------------------------------------- #
class ActivityEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: ActivityEventType
    agent_id: uuid.UUID | None
    ticket_id: uuid.UUID | None
    customer_id: uuid.UUID | None
    payload: dict[str, Any] | None
    # Flattened from the activity_event_mentions join table by the ``mentions``
    # property on the model.
    mentions: list[uuid.UUID] = Field(default_factory=list)
    created_at: datetime


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
class DashboardSummary(BaseModel):
    open_assigned: int
    overdue: int
    tasks_due_today: int
    unread_mentions: int
