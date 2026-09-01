"""AI-chatbot conversation state.

A ``ChatbotSession`` is a single, long-lived conversation thread per portal
user (get-or-create, not one-per-page-load -- see
``app.services.ai.chatbot.get_or_create_session``). ``ChatbotMessage`` rows are
append-only; nothing here is ever edited in place, unlike ``TicketFeedback``.

Full history is always persisted. Only a capped, recent slice of it is ever
sent to the AI provider on a given turn -- see
``app.services.ai.chatbot.MAX_HISTORY_MESSAGES``/``MAX_HISTORY_CHARS``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.customer import _pk

if TYPE_CHECKING:
    from app.models.portal import PortalUser


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ChatbotSession(Base):
    __tablename__ = "chatbot_sessions"

    id: Mapped[uuid.UUID] = _pk()
    portal_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portal_users.id", ondelete="CASCADE"), nullable=False, index=True
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

    portal_user: Mapped[PortalUser] = relationship(back_populates="chatbot_sessions")
    messages: Mapped[list[ChatbotMessage]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ChatbotMessage.created_at",
    )


class ChatbotMessage(Base):
    __tablename__ = "chatbot_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_chatbot_messages_role"),
        Index("ix_chatbot_messages_session_created", "session_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chatbot_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Plain CHECK-constrained string, not a named Postgres enum -- matches the
    # kb_articles.kind/status precedent, so no enum-drop loop is needed in
    # downgrade().
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Set in Python (default=), not server-side -- SQLite's CURRENT_TIMESTAMP
    # has only second resolution, and two messages in the same turn (user then
    # assistant) would otherwise tie and fall back to random uuid4 ordering.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )

    session: Mapped[ChatbotSession] = relationship(back_populates="messages")
