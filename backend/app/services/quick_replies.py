"""Quick-reply (canned response) service layer.

Two scopes: ``personal`` replies belong to one agent, ``team`` replies belong to
nobody and are visible to everyone. The invariant "personal ⇔ has an owner" is
enforced in three places — the DB CHECK constraint, this module, and the read
schema — because a violated row would make a personal reply visible team-wide.

Pure functions over a SQLAlchemy ``Session`` — no FastAPI imports. Callers own
the transaction boundary; these functions ``flush`` but never commit.
"""

from __future__ import annotations

import uuid

from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session

from app.models.agent import QuickReply
from app.schemas.agent import QuickReplyCreate, QuickReplyUpdate
from app.services.errors import Conflict, Forbidden, NotFound


def _scope_rank():
    """SQL expression ordering team(0) before personal(1).

    A CASE rather than the raw column for the same reason as
    :func:`app.services.tickets.priority_rank`: Postgres would sort the native
    enum by declaration order (personal, team) while SQLite sorts its VARCHAR
    alphabetically — and here the two happen to agree on the *wrong* answer.
    """
    return case((QuickReply.scope == "team", 0), else_=1)


def _owner_for(scope: str, agent_id: uuid.UUID) -> uuid.UUID | None:
    """The owner a reply of this scope must have. The invariant, in one place."""
    if scope == "personal":
        return agent_id
    if scope == "team":
        return None
    raise Conflict(f"unknown quick-reply scope {scope!r}")


def list_visible(db: Session, agent_id: uuid.UUID) -> list[QuickReply]:
    """Team replies plus this agent's own — never another agent's personal ones.

    Team first so the shared library heads the picker, then alphabetically, so
    the list is stable between renders.
    """
    return list(
        db.scalars(
            select(QuickReply)
            .where(
                or_(
                    QuickReply.scope == "team",
                    QuickReply.owner_agent_id == agent_id,
                )
            )
            .order_by(_scope_rank().asc(), QuickReply.title.asc())
        )
    )


def get_quick_reply(db: Session, reply_id: uuid.UUID) -> QuickReply:
    reply = db.get(QuickReply, reply_id)
    if reply is None:
        raise NotFound(f"quick reply {reply_id} not found")
    return reply


def _assert_may_mutate(reply: QuickReply, agent_id: uuid.UUID) -> None:
    """Only the owner may touch a personal reply.

    Team replies are mutable by any agent for now — the library is small and
    shared, and there are no roles yet to say who curates it. Policy hardening
    (owner/editor roles on team replies) is a follow-up.
    """
    if reply.scope == "personal" and reply.owner_agent_id != agent_id:
        raise Forbidden("that quick reply belongs to another agent")


def create(
    db: Session, agent_id: uuid.UUID, payload: QuickReplyCreate
) -> QuickReply:
    data = payload.model_dump()
    scope = data.pop("scope")
    reply = QuickReply(scope=scope, owner_agent_id=_owner_for(scope, agent_id), **data)
    db.add(reply)
    db.flush()
    db.refresh(reply)
    return reply


def update(
    db: Session,
    reply_id: uuid.UUID,
    agent_id: uuid.UUID,
    payload: QuickReplyUpdate,
) -> QuickReply:
    """Partial update. Changing ``scope`` rewrites ``owner_agent_id`` with it.

    Promoting a personal reply to the team clears its owner; demoting a team
    reply makes the agent doing so its owner. Either way the pair stays
    consistent — the CHECK constraint would reject anything else.
    """
    reply = get_quick_reply(db, reply_id)
    _assert_may_mutate(reply, agent_id)

    data = payload.model_dump(exclude_unset=True)
    scope = data.pop("scope", None)
    for field, value in data.items():
        setattr(reply, field, value)
    if scope is not None and scope != reply.scope:
        reply.scope = scope
        reply.owner_agent_id = _owner_for(scope, agent_id)

    db.flush()
    db.refresh(reply)
    return reply


def delete(db: Session, reply_id: uuid.UUID, agent_id: uuid.UUID) -> None:
    reply = get_quick_reply(db, reply_id)
    _assert_may_mutate(reply, agent_id)
    db.delete(reply)
    db.flush()
