"""Communication-channel HTTP routes.

Service-layer errors are translated centrally by the handlers registered in
``app.main``; these handlers keep the route bodies free of try/except noise.

An unknown channel slug is rejected as a 422 by the ``ChannelSlug`` literal in
``app.schemas.channel`` before any handler body runs — hence no 404 path for it
here.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import OptionalAgent
from app.db.session import get_db
from app.schemas.channel import (
    ChannelInboundPayload,
    ChannelMessageCreate,
    ChannelMessageRead,
    ChannelRead,
    ChannelSlug,
    ChannelUpdate,
)
from app.schemas.customer import Page
from app.services.channels import service as svc

router = APIRouter(tags=["channels"])

DbDep = Annotated[Session, Depends(get_db)]


# --------------------------------------------------------------------------- #
# Channel catalogue (fixed five rows — no create or delete)
# --------------------------------------------------------------------------- #
@router.get("/channels", response_model=list[ChannelRead])
def list_channels(db: DbDep, enabled_only: bool = False) -> list[ChannelRead]:
    return [
        ChannelRead.model_validate(c)
        for c in svc.list_channels(db, enabled_only=enabled_only)
    ]


@router.patch("/channels/{slug}", response_model=ChannelRead)
def update_channel(slug: ChannelSlug, payload: ChannelUpdate, db: DbDep) -> ChannelRead:
    return ChannelRead.model_validate(svc.update_channel(db, slug, payload))


# --------------------------------------------------------------------------- #
# Ticket message thread
# --------------------------------------------------------------------------- #
@router.get("/tickets/{ticket_id}/messages", response_model=Page[ChannelMessageRead])
def list_ticket_messages(
    ticket_id: uuid.UUID,
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ChannelMessageRead]:
    items, total = svc.list_messages_for_ticket(db, ticket_id, limit=limit, offset=offset)
    return Page[ChannelMessageRead](
        items=[ChannelMessageRead.model_validate(m) for m in items], total=total
    )


@router.post(
    "/tickets/{ticket_id}/messages",
    response_model=ChannelMessageRead,
    status_code=status.HTTP_201_CREATED,
)
def send_ticket_message(
    ticket_id: uuid.UUID,
    payload: ChannelMessageCreate,
    db: DbDep,
    agent: OptionalAgent,
) -> ChannelMessageRead:
    """Send an outbound reply on one of the ticket's channels.

    201 even when the send fails: the message row was created, and its
    ``status``/``error_reason`` carry the delivery outcome.

    ``X-Agent-Id`` is optional and does not touch the send DTO — it only names
    the actor on the resulting team-activity entry.
    """
    return ChannelMessageRead.model_validate(
        svc.enqueue_outbound(
            db, ticket_id, payload, actor_agent_id=agent.id if agent else None
        )
    )


# --------------------------------------------------------------------------- #
# Inbound webhooks
# --------------------------------------------------------------------------- #
@router.post(
    "/channels/{slug}/inbound",
    response_model=ChannelMessageRead,
    status_code=status.HTTP_201_CREATED,
)
def ingest_channel_inbound(
    slug: ChannelSlug, payload: ChannelInboundPayload, db: DbDep
) -> ChannelMessageRead:
    """Accept a provider payload and append it to a ticket's thread.

    Unauthenticated and unverified: signature checks belong with the adapter
    that knows how its provider signs, in stories 21-25.
    """
    return ChannelMessageRead.model_validate(svc.ingest_inbound(db, slug, payload))
