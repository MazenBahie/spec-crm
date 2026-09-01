"""Ticket-management ORM models.

``tickets`` cascades from ``customers.id`` (deleting a customer removes its
tickets and their events). ``ticket_events`` is append-only: every mutation of
a ticket writes a new row via ``app.services.tickets._record`` rather than
updating an existing one, so the full history is always reconstructable.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.customer import _pk

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.portal import TicketFeedback

TICKET_STATUSES = (
    "open",
    "triaged",
    "in_progress",
    "waiting_customer",
    "resolved",
    "closed",
)
TICKET_PRIORITIES = ("low", "normal", "high", "urgent")
TICKET_EVENT_TYPES = (
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
)

ticket_status_enum = Enum(*TICKET_STATUSES, name="ticket_status")
ticket_priority_enum = Enum(*TICKET_PRIORITIES, name="ticket_priority")
ticket_event_type_enum = Enum(*TICKET_EVENT_TYPES, name="ticket_event_type")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = _pk()
    display_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    is_active: Mapped[bool] = mapped_column(
        nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TicketCategory(Base):
    __tablename__ = "ticket_categories"

    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    default_priority: Mapped[str] = mapped_column(
        ticket_priority_enum, nullable=False, server_default="normal"
    )
    is_active: Mapped[bool] = mapped_column(
        nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        Index("ix_tickets_status_priority", "status", "priority"),
        Index("ix_tickets_customer_created", "customer_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = _pk()
    reference: Mapped[str] = mapped_column(String(24), nullable=False, unique=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ticket_categories.id", ondelete="SET NULL"), index=True
    )
    ai_suggested_category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ticket_categories.id", ondelete="SET NULL"), index=True
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), index=True
    )
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    status: Mapped[str] = mapped_column(
        ticket_status_enum, nullable=False, server_default="open"
    )
    priority: Mapped[str] = mapped_column(
        ticket_priority_enum, nullable=False, server_default="normal"
    )
    escalation_level: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ai_summary: Mapped[str | None] = mapped_column(Text)
    ai_summary_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    customer: Mapped[Customer] = relationship(back_populates="tickets")
    category: Mapped[TicketCategory | None] = relationship(foreign_keys=[category_id])
    ai_suggested_category: Mapped[TicketCategory | None] = relationship(
        foreign_keys=[ai_suggested_category_id]
    )
    assignee: Mapped[Agent | None] = relationship()
    events: Mapped[list[TicketEvent]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TicketEvent.created_at",
    )
    feedback: Mapped[TicketFeedback | None] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def is_terminal(self) -> bool:
        return self.status in ("resolved", "closed")

    @property
    def is_overdue(self) -> bool:
        """True when a still-open ticket has passed its due date.

        Computed on read only. There is no background job that acts on this —
        time-based auto-escalation is out of scope for this story.
        """
        if self.due_at is None or self.is_terminal:
            return False
        due = self.due_at
        now = datetime.now(due.tzinfo) if due.tzinfo else datetime.utcnow()
        return due < now


class TicketEvent(Base):
    __tablename__ = "ticket_events"
    __table_args__ = (
        Index("ix_ticket_events_ticket_created", "ticket_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = _pk()
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(ticket_event_type_enum, nullable=False)
    field: Mapped[str | None] = mapped_column(String(64))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    # Free text, deliberately not an FK — mirrors Interaction.author, since
    # there is no authentication yet to attach a real user id to.
    actor: Mapped[str | None] = mapped_column(String(255))
    # Stamped in Python, not by the server: SQLite's CURRENT_TIMESTAMP has only
    # second resolution, so several events appended within one request would
    # share a timestamp and the history order would come down to the random
    # uuid4 tie-break. server_default stays as a backstop for rows inserted
    # outside the ORM. Same reasoning as ChannelMessage.created_at.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )

    ticket: Mapped[Ticket] = relationship(back_populates="events")
