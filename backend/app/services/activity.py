"""Team-activity service layer.

An append-only log of "something happened on a ticket". Nothing updates a row,
and nothing deletes one except the cascade from its ticket.

Pure functions over a SQLAlchemy ``Session`` — no FastAPI imports. Callers own
the transaction boundary; these functions ``flush`` but never commit.

Recording is deliberately **best-effort in shape but not in failure**: a caller
records after the state change it describes has already been flushed, inside the
same transaction, so the feed can never claim something the database rolled
back.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.agent import ActivityEvent, ActivityMention
from app.models.ticket import Agent, Ticket

# Deliberately loose: an @handle is whatever a human typed. Resolution below
# drops anything that does not match an agent, so a false positive costs
# nothing.
MENTION_PATTERN = re.compile(r"@([A-Za-z0-9_.\-]+)")

# How far back "unread" reaches, standing in for a real read-state model.
MENTION_WINDOW_DAYS = 7


def record(
    db: Session,
    *,
    event_type: str,
    agent_id: uuid.UUID | None = None,
    ticket_id: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
    mentions: list[uuid.UUID] | None = None,
) -> ActivityEvent:
    """Append one event. Returns it flushed, so its id is readable."""
    event = ActivityEvent(
        event_type=event_type,
        agent_id=agent_id,
        ticket_id=ticket_id,
        customer_id=customer_id,
        payload=payload,
    )
    # Deduplicated: "@dana @dana" is one mention, and a self-mention is dropped
    # so an agent never lights up their own unread badge.
    for mentioned in dict.fromkeys(mentions or ()):
        if mentioned == agent_id:
            continue
        event.mention_rows.append(ActivityMention(agent_id=mentioned))
    db.add(event)
    db.flush()
    return event


def resolve_mentions(db: Session, body: str) -> list[uuid.UUID]:
    """Map the ``@handle``s in a note body onto agent ids.

    A handle matches an agent's email local part or their display name with
    spaces collapsed to nothing, both case-insensitively — so "Dana Support"
    answers to ``@dana`` (via dana@crm.test) and ``@danasupport``.

    An unknown handle is silently dropped rather than raised: an agent typing a
    name slightly wrong must not be blocked from posting the note.
    """
    handles = {match.lower() for match in MENTION_PATTERN.findall(body)}
    if not handles:
        return []

    resolved: list[uuid.UUID] = []
    for agent in db.scalars(select(Agent).where(Agent.is_active.is_(True))):
        local_part = (agent.email or "").split("@")[0].lower()
        collapsed = agent.display_name.replace(" ", "").lower()
        if (local_part and local_part in handles) or collapsed in handles:
            resolved.append(agent.id)
    return resolved


def _visible_to(agent_id: uuid.UUID):
    """The "events this agent should see" predicate.

    Three ways in: they did it, it happened on a ticket assigned to them, or
    they were named in it.
    """
    assigned_tickets = select(Ticket.id).where(Ticket.assignee_id == agent_id)
    mentioned_events = select(ActivityMention.event_id).where(
        ActivityMention.agent_id == agent_id
    )
    return or_(
        ActivityEvent.agent_id == agent_id,
        ActivityEvent.ticket_id.in_(assigned_tickets),
        ActivityEvent.id.in_(mentioned_events),
    )


def feed_for_agent(
    db: Session, agent_id: uuid.UUID, *, limit: int = 50
) -> list[ActivityEvent]:
    """Newest-first slice of the events this agent has a stake in."""
    return list(
        db.scalars(
            select(ActivityEvent)
            .where(_visible_to(agent_id))
            .options(selectinload(ActivityEvent.mention_rows))
            .order_by(ActivityEvent.created_at.desc(), ActivityEvent.id.desc())
            .limit(limit)
        )
    )


def count_recent_mentions(db: Session, agent_id: uuid.UUID, *, since) -> int:
    """Events naming this agent since ``since``.

    Stands in for "unread": there is no per-agent read cursor yet, so recency is
    the proxy. Swapping in a real one is a column on ``agents`` plus a
    ``>= last_read_at`` here.
    """
    return (
        db.scalar(
            select(func.count())
            .select_from(ActivityEvent)
            .join(ActivityMention, ActivityMention.event_id == ActivityEvent.id)
            .where(
                ActivityMention.agent_id == agent_id,
                ActivityEvent.created_at >= since,
            )
        )
        or 0
    )
