"""Internal ticket-note service layer.

A note is a message between agents about a ticket. It is stored in its own
table and there is **no code path from here to a channel driver** — that is the
whole point. See the module docstring of ``app.models.agent`` for why this is a
separate table rather than a flag on ``channel_messages``.

Pure functions over a SQLAlchemy ``Session`` — no FastAPI imports. Callers own
the transaction boundary; these functions ``flush`` but never commit.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.agent import TicketNote
from app.schemas.agent import TicketNoteCreate
from app.services import activity
from app.services.tickets import get_ticket


def list_notes(
    db: Session, ticket_id: uuid.UUID, *, limit: int = 200, offset: int = 0
) -> tuple[list[TicketNote], int]:
    """One page of a ticket's note thread, oldest first.

    Ascending like the message thread, and for the same reason: it reads as a
    conversation, so the newest note belongs at the bottom next to the composer.
    """
    get_ticket(db, ticket_id)
    where = (TicketNote.ticket_id == ticket_id,)
    total = db.scalar(select(func.count()).select_from(TicketNote).where(*where)) or 0
    rows = db.scalars(
        select(TicketNote)
        .where(*where)
        .options(selectinload(TicketNote.author))
        .order_by(TicketNote.created_at.asc(), TicketNote.id.asc())
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total


def add_note(
    db: Session,
    ticket_id: uuid.UUID,
    author_agent_id: uuid.UUID,
    payload: TicketNoteCreate,
) -> TicketNote:
    """Append an internal note and log it to the activity feed.

    ``@handle``s in the body are resolved to agent ids and attached to the
    event, which is what puts the note in a mentioned agent's feed even when
    they are not the ticket's assignee.
    """
    ticket = get_ticket(db, ticket_id)
    note = TicketNote(
        ticket_id=ticket.id, author_agent_id=author_agent_id, body=payload.body
    )
    db.add(note)
    db.flush()

    activity.record(
        db,
        event_type="note.added",
        agent_id=author_agent_id,
        ticket_id=ticket.id,
        customer_id=ticket.customer_id,
        payload={"note_id": str(note.id), "excerpt": payload.body[:140]},
        mentions=activity.resolve_mentions(db, payload.body),
    )

    db.refresh(note)
    return note
