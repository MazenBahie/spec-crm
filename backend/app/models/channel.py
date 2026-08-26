"""Communication-channel ORM models.

``channels`` is a fixed catalogue, not user-authored data: exactly the five rows
in :data:`CHANNEL_CATALOGUE` exist, each keyed by a stable ``slug`` that a
driver in ``app.services.channels`` is registered against. Only ``is_enabled``
and ``config`` are mutable. The rows are written by Alembic revision
``0003_communication_channels`` in production and by the ``after_create`` hook
at the bottom of this module on a ``metadata.create_all`` database (the test
suite), so "the catalogue is always there" holds in both places. The ids are
hard-coded rather than generated so both paths produce identical rows.

``channel_messages`` cascades from ``tickets.id``. A row is effectively
append-only apart from its delivery fields (``status``,
``provider_message_id``, ``error_reason``), which the send path in
``app.services.channels.service`` updates once the driver has answered.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    event,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.customer import _pk
from app.models.ticket import Ticket

# (id, slug, display_name). Mirrored verbatim by the seed in
# alembic/versions/0003_communication_channels.py — that migration is frozen in
# time and deliberately does not import this module.
CHANNEL_CATALOGUE: tuple[tuple[uuid.UUID, str, str], ...] = (
    (uuid.UUID("c8a1c0de-0000-4000-8000-000000000001"), "email", "Email"),
    (uuid.UUID("c8a1c0de-0000-4000-8000-000000000002"), "whatsapp", "WhatsApp"),
    (uuid.UUID("c8a1c0de-0000-4000-8000-000000000003"), "live_chat", "Live chat"),
    (uuid.UUID("c8a1c0de-0000-4000-8000-000000000004"), "sms", "SMS"),
    (uuid.UUID("c8a1c0de-0000-4000-8000-000000000005"), "web_form", "Web forms"),
)

CHANNEL_SLUGS: tuple[str, ...] = tuple(slug for _, slug, _ in CHANNEL_CATALOGUE)

MESSAGE_DIRECTIONS = ("inbound", "outbound")
# ``queued`` is the state a row is born in; the driver moves it to ``sent`` /
# ``delivered`` / ``failed``. ``received`` is the terminal state of an inbound
# message, which is never sent anywhere.
MESSAGE_STATUSES = ("queued", "sent", "delivered", "failed", "received")

message_direction_enum = Enum(*MESSAGE_DIRECTIONS, name="channel_message_direction")
message_status_enum = Enum(*MESSAGE_STATUSES, name="channel_message_status")

# Postgres gets JSONB (indexable, deduplicated keys); SQLite gets plain JSON.
# none_as_null so an unconfigured channel is SQL NULL rather than the JSON
# document `null` — the two are indistinguishable once read back into Python,
# but only the former answers `config IS NULL`.
channel_config_type = JSON(none_as_null=True).with_variant(
    JSONB(none_as_null=True), "postgresql"
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[uuid.UUID] = _pk()
    slug: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(
        nullable=False, default=True, server_default=text("true")
    )
    # Provider credentials and per-channel settings. Empty until the matching
    # adapter story (21-25) defines what its driver needs.
    config: Mapped[dict | None] = mapped_column(channel_config_type)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ChannelMessage(Base):
    __tablename__ = "channel_messages"
    __table_args__ = (
        Index("ix_channel_messages_ticket_created", "ticket_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _pk()
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # RESTRICT, not CASCADE: the catalogue is fixed, so a channel row being
    # deleted underneath its messages is a bug, not a state to tolerate.
    channel_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("channels.id", ondelete="RESTRICT"), nullable=False
    )
    # Denormalised from the ticket so "every message from this customer" is one
    # index scan. Nullable because a later story may accept a message before it
    # has been matched to a ticket's customer.
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    direction: Mapped[str] = mapped_column(message_direction_enum, nullable=False)
    status: Mapped[str] = mapped_column(message_status_enum, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    error_reason: Mapped[str | None] = mapped_column(Text)
    # Stamped in Python rather than by the server: SQLite's CURRENT_TIMESTAMP
    # only has second resolution, which is not enough to order a thread of
    # replies posted in quick succession. server_default stays as a backstop
    # for rows inserted outside the ORM.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
        index=True,
    )

    # One-directional on purpose. A ``Ticket.messages`` backref would make
    # mapper configuration depend on this module having been imported, which
    # app.models.ticket cannot guarantee. Deletion is handled by the FK's
    # ON DELETE CASCADE instead.
    ticket: Mapped[Ticket] = relationship()
    channel: Mapped[Channel] = relationship()

    @property
    def channel_slug(self) -> str:
        """The message's channel key, so callers need not join it themselves."""
        return self.channel.slug


@event.listens_for(Channel.__table__, "after_create")
def _seed_channel_catalogue(target, connection, **_kw: object) -> None:
    """Seed the catalogue on a ``metadata.create_all`` database.

    Alembic builds its own ``Table`` object in a separate ``MetaData``, so this
    listener never fires during a migration and cannot double-insert alongside
    the seed in ``0003_communication_channels``.
    """
    connection.execute(
        target.insert(),
        [
            {"id": channel_id, "slug": slug, "display_name": display_name}
            for channel_id, slug, display_name in CHANNEL_CATALOGUE
        ],
    )
