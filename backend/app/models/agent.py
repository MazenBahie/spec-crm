"""Agent-dashboard ORM models.

Everything an individual agent owns or collaborates through: their personal
task list, the quick-reply library (personal + team), the internal note thread
on a ticket, and the append-only activity log the dashboard feed reads.

The ``agents`` table itself is **not** defined here — it already exists in
``app.models.ticket``, introduced by the ticket-assignment story, and is keyed
by ``uuid``. This module only hangs new tables off it.

Internal notes live in their own ``ticket_notes`` table rather than as a flag on
``channel_messages``. That table is provider transport: ``channel_id``,
``direction`` and ``status`` are all NOT NULL and describe a delivery attempt. A
note has no channel, no direction and is never delivered, so putting it there
would mean nullable columns, misleading enum values, and an ``is_internal``
filter on every existing query — one missed filter being a customer-visible
leak. A separate table makes the leak structurally impossible: no driver code
path reaches it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.customer import _pk
from app.models.ticket import Agent

AGENT_TASK_STATUSES = ("open", "done")
QUICK_REPLY_SCOPES = ("personal", "team")

# Deliberately a plain string column rather than a named enum: the feed is a
# lightweight log and new event types are expected to arrive with later
# stories, which would each need an `ALTER TYPE` migration otherwise. The
# Literal in app.schemas.agent is what keeps the API honest.
ACTIVITY_EVENT_TYPES = (
    "ticket.assigned",
    "ticket.status_changed",
    "ticket.replied",
    "note.added",
    "mention",
)

agent_task_status_enum = Enum(*AGENT_TASK_STATUSES, name="agent_task_status")
quick_reply_scope_enum = Enum(*QUICK_REPLY_SCOPES, name="quick_reply_scope")

# Same variant pair as Channel.config: JSONB on Postgres, plain JSON on the
# SQLite test database.
activity_payload_type = JSON(none_as_null=True).with_variant(
    JSONB(none_as_null=True), "postgresql"
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgentTask(Base):
    """A personal to-do item. Only its owning agent ever sees or mutates it."""

    __tablename__ = "agent_tasks"
    __table_args__ = (
        Index("ix_agent_tasks_agent_status", "agent_id", "status"),
    )

    id: Mapped[uuid.UUID] = _pk()
    agent_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        agent_task_status_enum, nullable=False, default="open", server_default="open"
    )
    remind_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    # SET NULL, not CASCADE: a task survives the ticket or customer it was
    # filed against — the agent still has to do the thing.
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tickets.id", ondelete="SET NULL"), index=True
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("customers.id", ondelete="SET NULL"), index=True
    )
    # Stamped in Python for the same reason as ticket_events.created_at:
    # SQLite's CURRENT_TIMESTAMP has second resolution, so several tasks added
    # in one request would tie and order by the random uuid4 primary key.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
        onupdate=_utcnow,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QuickReply(Base):
    """A reusable canned response, either personal to one agent or team-wide.

    ``body`` holds the *template* — ``{{customer.first_name}}`` and friends are
    rendered by the picker at insert time and never persisted rendered, so
    editing a reply changes every future insertion.
    """

    __tablename__ = "quick_replies"
    __table_args__ = (
        # The scope invariant, in the database as well as in the service layer:
        # a personal reply always has an owner, a team reply never does.
        CheckConstraint(
            "(scope = 'personal' AND owner_agent_id IS NOT NULL)"
            " OR (scope = 'team' AND owner_agent_id IS NULL)",
            name="ck_quick_replies_scope_owner",
        ),
        Index("ix_quick_replies_owner_shortcut", "owner_agent_id", "shortcut"),
    )

    id: Mapped[uuid.UUID] = _pk()
    scope: Mapped[str] = mapped_column(quick_reply_scope_enum, nullable=False)
    owner_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("agents.id", ondelete="CASCADE")
    )
    shortcut: Mapped[str | None] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
        onupdate=_utcnow,
    )


class TicketNote(Base):
    """An internal note on a ticket. Never delivered to a customer.

    Append-only, like ``ticket_events``: there is no edit or delete path, so a
    note another agent has already read cannot be rewritten under them.
    """

    __tablename__ = "ticket_notes"
    __table_args__ = (
        Index("ix_ticket_notes_ticket_created", "ticket_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _pk()
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # SET NULL so deactivating-then-deleting an agent does not erase the thread.
    author_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("agents.id", ondelete="SET NULL"), index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )

    author: Mapped[Agent | None] = relationship()


class ActivityEvent(Base):
    """One line of the team feed. Append-only; nothing updates a row."""

    __tablename__ = "activity_events"
    __table_args__ = (
        Index("ix_activity_events_created_desc", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = _pk()
    # Nullable: the actor may be the system, or an unauthenticated path such as
    # an inbound webhook.
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("agents.id", ondelete="SET NULL"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tickets.id", ondelete="CASCADE"), index=True
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    payload: Mapped[dict | None] = mapped_column(activity_payload_type)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
        index=True,
    )

    mention_rows: Mapped[list[ActivityMention]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    @property
    def mentions(self) -> list[uuid.UUID]:
        """The join rows flattened, so the API serves a plain list of agent ids."""
        return [row.agent_id for row in self.mention_rows]


class ActivityMention(Base):
    """Join row: "this event mentions this agent".

    A normalised table rather than a JSON array on the event, so "events that
    mention me" is an indexed join on both Postgres and the SQLite test
    database. A JSON array would only be queryable through dialect-specific
    containment operators.
    """

    __tablename__ = "activity_event_mentions"

    event_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("activity_events.id", ondelete="CASCADE"),
        primary_key=True,
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("agents.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )

    event: Mapped[ActivityEvent] = relationship(back_populates="mention_rows")
