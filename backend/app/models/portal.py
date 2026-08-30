"""Customer-portal ORM models.

``portal_users`` cascades from ``customers.id`` (deleting a customer removes
its portal logins and their sessions). A ``Customer`` may hold many
``PortalUser`` rows -- one per contact person -- all scoped to the same
customer's data.

Unlike the ``Agent``/``X-Agent-Id`` placeholder (``app.api.deps``), a
``PortalUser`` is real, credential-based auth: ``password_hash`` is a bcrypt
hash, and a login session is a ``PortalSession`` row whose ``token_hash`` is
the SHA-256 digest of an opaque bearer token -- the raw token itself is never
stored anywhere.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.customer import _pk

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.ticket import Ticket


class PortalUser(Base):
    __tablename__ = "portal_users"

    id: Mapped[uuid.UUID] = _pk()
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    customer: Mapped[Customer] = relationship(back_populates="portal_users")
    sessions: Mapped[list[PortalSession]] = relationship(
        back_populates="portal_user", cascade="all, delete-orphan", passive_deletes=True
    )


class PortalSession(Base):
    __tablename__ = "portal_sessions"
    __table_args__ = (
        Index(
            "ix_portal_sessions_portal_user_created",
            "portal_user_id",
            text("created_at DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    portal_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portal_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Hex-encoded SHA-256 digest of the raw bearer token. The raw token is
    # returned to the client exactly once (the login/signup response) and
    # never persisted.
    token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    # Set on logout. A session row is soft-revoked, never deleted, so session
    # lifetime stays auditable.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    portal_user: Mapped[PortalUser] = relationship(back_populates="sessions")


class TicketFeedback(Base):
    __tablename__ = "ticket_feedback"
    __table_args__ = (Index("ix_ticket_feedback_ticket_id", "ticket_id"),)

    id: Mapped[uuid.UUID] = _pk()
    # Unique: one feedback row per ticket. A second submission updates this
    # row rather than creating another one (see app.services.portal).
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    # SET NULL, not CASCADE, matching Ticket.assignee_id's reasoning: if the
    # PortalUser row is later deleted, the feedback itself survives -- only
    # the attribution is lost.
    portal_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("portal_users.id", ondelete="SET NULL")
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    ticket: Mapped[Ticket] = relationship(back_populates="feedback")
