"""Communication-channel service layer.

Pure functions over a SQLAlchemy ``Session`` — no FastAPI imports. Callers own
the transaction boundary (the ``get_db`` dependency commits on success); these
functions ``flush`` so generated ids and server defaults are readable, but
never commit.

Sending is **best-effort by design**: the row is persisted first, then handed to
the driver, and a driver failure is recorded on the row rather than raised. A
caller therefore always gets a message back, and the thread never loses an
attempt. Retrying a failed send is not modelled — an agent re-sends, which
appends a new row, keeping the thread an honest record of what was tried.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.channel import Channel, ChannelMessage
from app.schemas.channel import (
    ChannelInboundPayload,
    ChannelMessageCreate,
    ChannelUpdate,
)
from app.services import activity
from app.services.channels.registry import get_driver
from app.services.errors import Conflict, NotFound, ServiceError
from app.services.tickets import get_ticket

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Channel catalogue
# --------------------------------------------------------------------------- #
def list_channels(db: Session, *, enabled_only: bool = False) -> list[Channel]:
    stmt = select(Channel).order_by(Channel.display_name.asc())
    if enabled_only:
        stmt = stmt.where(Channel.is_enabled.is_(True))
    return list(db.scalars(stmt))


def get_channel(db: Session, slug: str) -> Channel:
    channel = db.scalars(select(Channel).where(Channel.slug == slug)).first()
    if channel is None:
        raise NotFound(f"channel {slug!r} not found")
    return channel


def update_channel(db: Session, slug: str, payload: ChannelUpdate) -> Channel:
    """Enable/disable a channel or rewrite its provider config."""
    channel = get_channel(db, slug)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(channel, field, value)
    db.flush()
    db.refresh(channel)
    return channel


def _get_enabled_channel(db: Session, slug: str) -> Channel:
    channel = get_channel(db, slug)
    if not channel.is_enabled:
        raise Conflict(f"channel {slug!r} is disabled")
    return channel


# --------------------------------------------------------------------------- #
# Messages
# --------------------------------------------------------------------------- #
def list_messages_for_ticket(
    db: Session, ticket_id: uuid.UUID, *, limit: int = 200, offset: int = 0
) -> tuple[list[ChannelMessage], int]:
    """One page of a ticket's thread, oldest first.

    Ascending, unlike the ticket event log: this reads as a conversation, so the
    newest message belongs at the bottom next to the reply box.
    """
    get_ticket(db, ticket_id)
    where = (ChannelMessage.ticket_id == ticket_id,)
    total = db.scalar(select(func.count()).select_from(ChannelMessage).where(*where)) or 0
    rows = db.scalars(
        select(ChannelMessage)
        .where(*where)
        .options(selectinload(ChannelMessage.channel))
        .order_by(ChannelMessage.created_at.asc(), ChannelMessage.id.asc())
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total


def enqueue_outbound(
    db: Session,
    ticket_id: uuid.UUID,
    payload: ChannelMessageCreate,
    *,
    actor_agent_id: uuid.UUID | None = None,
) -> ChannelMessage:
    """Persist an outbound message, then try to send it.

    The row lands as ``queued`` before the driver is called, so a driver that
    raises — the expected outcome for every channel until its adapter story
    lands — still leaves an auditable attempt behind, marked ``failed`` with the
    reason the caller can read straight back off the response.

    ``actor_agent_id`` only decides who the team feed credits for the reply. It
    is optional, and the send DTO is unchanged: this route stays callable
    without agent context, and the feed then records the reply with no actor.
    """
    ticket = get_ticket(db, ticket_id)
    channel = _get_enabled_channel(db, payload.channel_slug)

    message = ChannelMessage(
        ticket_id=ticket.id,
        channel_id=channel.id,
        customer_id=ticket.customer_id,
        direction="outbound",
        status="queued",
        body=payload.body,
    )
    db.add(message)
    db.flush()

    # Broad by intent: "the provider did not take it" covers a stub that is not
    # written yet as much as a timeout or a rejected credential, and all three
    # belong on the row rather than as a 5xx that loses the message. Service
    # errors are re-raised — those are our own preconditions, not transport.
    try:
        result = get_driver(channel.slug).send(message)
    except ServiceError:
        raise
    except Exception as exc:
        logger.warning(
            "outbound send failed on channel %s for ticket %s: %s",
            channel.slug,
            ticket.id,
            exc,
        )
        message.status = "failed"
        message.error_reason = str(exc)
    else:
        message.status = result.status
        message.provider_message_id = result.provider_message_id

    # Recorded whatever the delivery outcome: "Omar tried to reply on #145 and
    # it bounced" is exactly the kind of thing a teammate needs to see.
    activity.record(
        db,
        event_type="ticket.replied",
        agent_id=actor_agent_id,
        ticket_id=ticket.id,
        customer_id=ticket.customer_id,
        payload={
            "channel": channel.slug,
            "status": message.status,
            "reference": ticket.reference,
        },
    )

    db.flush()
    db.refresh(message)
    return message


def ingest_inbound(
    db: Session, slug: str, payload: ChannelInboundPayload
) -> ChannelMessage:
    """Record an inbound provider payload against a ticket.

    The channel need not be enabled: disabling a channel stops agents replying
    on it, but a provider can still deliver a webhook for a conversation
    already in flight, and dropping it would lose the customer's message.
    """
    channel = get_channel(db, slug)
    raw = payload.model_dump()
    # Keys only — a payload body can carry personal data and must not reach the
    # logs.
    logger.info(
        "inbound %s payload for ticket %s, fields=%s",
        slug,
        payload.ticket_id,
        sorted(raw),
    )

    try:
        parsed = get_driver(channel.slug).parse_inbound(raw)
    except ValueError as exc:
        raise Conflict(str(exc)) from exc

    ticket = get_ticket(db, payload.ticket_id)
    message = ChannelMessage(
        ticket_id=ticket.id,
        channel_id=channel.id,
        customer_id=ticket.customer_id,
        direction="inbound",
        # Terminal on arrival: an inbound message is not going anywhere, so it
        # never passes through queued/sent.
        status="received",
        body=parsed.body,
        provider_message_id=parsed.provider_message_id,
    )
    db.add(message)
    db.flush()
    db.refresh(message)
    return message
