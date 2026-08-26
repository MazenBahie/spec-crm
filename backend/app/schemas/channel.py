"""Pydantic v2 schemas for the communication-channel API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.customer import NonEmptyStr

# Kept in lockstep with app.models.channel.CHANNEL_SLUGS. Declaring it as a
# Literal is what turns an unknown channel into a 422 at the edge, before any
# service or driver code runs.
ChannelSlug = Literal["email", "whatsapp", "live_chat", "sms", "web_form"]
MessageDirection = Literal["inbound", "outbound"]
MessageStatus = Literal["queued", "sent", "delivered", "failed", "received"]


# --------------------------------------------------------------------------- #
# Channels
# --------------------------------------------------------------------------- #
class ChannelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: ChannelSlug
    display_name: str
    is_enabled: bool
    config: dict[str, Any] | None
    created_at: datetime


class ChannelUpdate(BaseModel):
    """The only mutable parts of a catalogue row.

    ``slug`` and ``display_name`` are absent by design — drivers are registered
    against the slug, so renaming one would orphan its transport code.
    """

    is_enabled: bool | None = None
    config: dict[str, Any] | None = None


# --------------------------------------------------------------------------- #
# Messages
# --------------------------------------------------------------------------- #
class ChannelMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    channel_id: uuid.UUID
    channel_slug: ChannelSlug
    customer_id: uuid.UUID | None
    direction: MessageDirection
    status: MessageStatus
    body: str
    provider_message_id: str | None
    error_reason: str | None
    created_at: datetime


class ChannelMessageCreate(BaseModel):
    channel_slug: ChannelSlug
    body: NonEmptyStr


class ChannelInboundPayload(BaseModel):
    """A provider webhook body.

    ``extra="allow"`` so provider-shaped JSON survives intact for the driver's
    ``parse_inbound`` to read. Only the routing key is required here: real
    routing (match by sender address, thread id, or reply token) is a follow-up
    story, so the foundation asks the caller for the ticket outright.

    ``body`` is optional because it is the *driver* that decides where the text
    lives in a payload; the stub drivers read this field, and adapters in
    stories 21-25 will read their own.
    """

    model_config = ConfigDict(extra="allow")

    ticket_id: uuid.UUID
    body: str | None = None
