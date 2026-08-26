"""Ticket-management service layer.

Pure functions over a SQLAlchemy ``Session`` -- no FastAPI imports. Callers own
the transaction boundary (the ``get_db`` dependency commits on success); these
functions ``flush`` so generated ids and server defaults are readable, but
never commit.

Concurrency: every update is last-write-wins. Optimistic locking is out of
scope, so two overlapping PATCHes silently keep the later one — but every
status/priority/category/assignment/escalation change still appends a
ticket_events row, so the full history survives even when one write wins the
row.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.ticket import (
    TICKET_PRIORITIES,
    TICKET_STATUSES,
    Agent,
    Ticket,
    TicketCategory,
    TicketEvent,
)
from app.schemas.ticket import (
    AgentCreate,
    AgentUpdate,
    TicketAssignment,
    TicketCategoryCreate,
    TicketCategoryUpdate,
    TicketCommentCreate,
    TicketCreate,
    TicketEscalation,
    TicketStatusChange,
    TicketUpdate,
)
from app.services import activity
from app.services.customers import _require_active, get_customer
from app.services.errors import Conflict, NotFound

MAX_ESCALATION_LEVEL = 3

# The terminal pair, matching Ticket.is_terminal. "In an agent's queue" is
# everything else, derived rather than listed again so a status added later
# counts as open until someone says otherwise.
TERMINAL_STATUSES: tuple[str, ...] = ("resolved", "closed")
OPEN_STATUSES: tuple[str, ...] = tuple(
    status for status in TICKET_STATUSES if status not in TERMINAL_STATUSES
)

# Permitted status moves. A move not listed here (including onto the current
# status, handled separately) is rejected with 409.
ALLOWED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "open": ("triaged", "in_progress", "closed"),
    "triaged": ("in_progress", "open", "closed"),
    "in_progress": ("waiting_customer", "resolved", "triaged", "closed"),
    "waiting_customer": ("in_progress", "resolved", "closed"),
    "resolved": ("closed", "in_progress"),  # reopen
    "closed": ("open",),  # reopen
}

_PRIORITY_ORDER = {value: index for index, value in enumerate(TICKET_PRIORITIES)}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def build_reference(ticket_id: uuid.UUID) -> str:
    """Human-quotable ticket reference, e.g. "TCK-3F9A21C4".

    Derived from the ticket's own UUID rather than a counter: identical on
    Postgres and on the SQLite test database, and safe under concurrent
    inserts with no locking. Uniqueness is backed by the unique index on
    `tickets.reference`. Strictly sequential numbering would need a Postgres
    SEQUENCE (and a SQLite fallback) — deliberately deferred.
    """
    return f"TCK-{ticket_id.hex[:8].upper()}"


def _stringify(value: object) -> str | None:
    return None if value is None else str(value)


def priority_rank():
    """SQL expression ranking `tickets.priority` low(0) → urgent(3).

    Postgres would sort the `priority` enum column by declaration order, but
    SQLite stores it as VARCHAR and would sort alphabetically — so every
    priority ordering in the codebase goes through this CASE, not the raw
    column.

    Compares `Ticket.priority` via `==` rather than a dict-form CASE so
    SQLAlchemy binds each literal with the column's own type. A dict-form CASE
    casts its bind params as VARCHAR, which Postgres refuses to compare against
    an enum column ("operator does not exist: ticket_priority = character
    varying") even though SQLite's untyped columns accept it.
    """
    return case(
        *[(Ticket.priority == value, index) for value, index in _PRIORITY_ORDER.items()],
        else_=0,
    )


def _record(
    db: Session,
    ticket: Ticket,
    event_type: str,
    *,
    field: str | None = None,
    old_value: object = None,
    new_value: object = None,
    comment: str | None = None,
    actor: str | None = None,
) -> TicketEvent:
    """Append one immutable history row. Never updates an existing event."""
    event = TicketEvent(
        ticket_id=ticket.id,
        event_type=event_type,
        field=field,
        old_value=_stringify(old_value),
        new_value=_stringify(new_value),
        comment=comment,
        actor=actor,
    )
    db.add(event)
    db.flush()
    return event


# --------------------------------------------------------------------------- #
# Agents
# --------------------------------------------------------------------------- #
def list_agents(db: Session, *, active_only: bool = False) -> list[Agent]:
    stmt = select(Agent).order_by(Agent.display_name.asc())
    if active_only:
        stmt = stmt.where(Agent.is_active.is_(True))
    return list(db.scalars(stmt))


def get_agent(db: Session, agent_id: uuid.UUID) -> Agent:
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise NotFound(f"agent {agent_id} not found")
    return agent


def create_agent(db: Session, payload: AgentCreate) -> Agent:
    agent = Agent(**payload.model_dump())
    db.add(agent)
    db.flush()
    db.refresh(agent)
    return agent


def update_agent(db: Session, agent_id: uuid.UUID, payload: AgentUpdate) -> Agent:
    agent = get_agent(db, agent_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(agent, field, value)
    db.flush()
    db.refresh(agent)
    return agent


def deactivate_agent(db: Session, agent_id: uuid.UUID) -> Agent:
    """Agents are never hard-deleted, so assignment history stays readable."""
    agent = get_agent(db, agent_id)
    agent.is_active = False
    db.flush()
    db.refresh(agent)
    return agent


# --------------------------------------------------------------------------- #
# Ticket categories
# --------------------------------------------------------------------------- #
def _assert_category_name_free(
    db: Session, name: str, *, exclude: uuid.UUID | None = None
) -> None:
    stmt = select(func.count()).select_from(TicketCategory).where(
        func.lower(TicketCategory.name) == name.strip().lower()
    )
    if exclude is not None:
        stmt = stmt.where(TicketCategory.id != exclude)
    if (db.scalar(stmt) or 0) > 0:
        raise Conflict(f"a category named {name!r} already exists")


def list_categories(db: Session, *, active_only: bool = False) -> list[TicketCategory]:
    stmt = select(TicketCategory).order_by(TicketCategory.name.asc())
    if active_only:
        stmt = stmt.where(TicketCategory.is_active.is_(True))
    return list(db.scalars(stmt))


def get_category(db: Session, category_id: uuid.UUID) -> TicketCategory:
    category = db.get(TicketCategory, category_id)
    if category is None:
        raise NotFound(f"category {category_id} not found")
    return category


def create_category(db: Session, payload: TicketCategoryCreate) -> TicketCategory:
    _assert_category_name_free(db, payload.name)
    category = TicketCategory(**payload.model_dump())
    db.add(category)
    db.flush()
    db.refresh(category)
    return category


def update_category(
    db: Session, category_id: uuid.UUID, payload: TicketCategoryUpdate
) -> TicketCategory:
    category = get_category(db, category_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("name"):
        _assert_category_name_free(db, data["name"], exclude=category_id)
    for field, value in data.items():
        setattr(category, field, value)
    db.flush()
    db.refresh(category)
    return category


def delete_category(db: Session, category_id: uuid.UUID) -> None:
    category = get_category(db, category_id)
    in_use = db.scalar(
        select(func.count()).select_from(Ticket).where(Ticket.category_id == category_id)
    ) or 0
    if in_use > 0:
        raise Conflict(f"category is in use by {in_use} ticket(s)")
    db.delete(category)
    db.flush()


# --------------------------------------------------------------------------- #
# Tickets
# --------------------------------------------------------------------------- #
def list_tickets(
    db: Session,
    *,
    q: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    customer_id: uuid.UUID | None = None,
    assignee_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    unassigned: bool | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Ticket], int]:
    """Return one page of tickets plus the total matching the filters.

    Ordered urgent-first then newest-first, via :func:`priority_rank`.
    """
    filters = []
    if q and q.strip():
        pattern = f"%{q.strip().lower()}%"
        filters.append(
            or_(
                func.lower(Ticket.reference).like(pattern),
                func.lower(Ticket.subject).like(pattern),
                func.lower(Ticket.description).like(pattern),
            )
        )
    if status:
        filters.append(Ticket.status == status)
    if priority:
        filters.append(Ticket.priority == priority)
    if customer_id is not None:
        filters.append(Ticket.customer_id == customer_id)
    if assignee_id is not None:
        filters.append(Ticket.assignee_id == assignee_id)
    if category_id is not None:
        filters.append(Ticket.category_id == category_id)
    if unassigned:
        filters.append(Ticket.assignee_id.is_(None))

    total = db.scalar(select(func.count()).select_from(Ticket).where(*filters)) or 0
    rows = db.scalars(
        select(Ticket)
        .where(*filters)
        .order_by(priority_rank().desc(), Ticket.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total


def list_customer_tickets(
    db: Session, customer_id: uuid.UUID, *, limit: int = 20, offset: int = 0
) -> tuple[list[Ticket], int]:
    get_customer(db, customer_id)
    return list_tickets(db, customer_id=customer_id, limit=limit, offset=offset)


def get_ticket(
    db: Session, ticket_id: uuid.UUID, *, with_relations: bool = False
) -> Ticket:
    stmt = select(Ticket).where(Ticket.id == ticket_id)
    if with_relations:
        stmt = stmt.options(
            selectinload(Ticket.customer),
            selectinload(Ticket.category),
            selectinload(Ticket.assignee),
        )
    ticket = db.scalars(stmt).first()
    if ticket is None:
        raise NotFound(f"ticket {ticket_id} not found")
    return ticket


def _get_active_category(db: Session, category_id: uuid.UUID) -> TicketCategory:
    category = get_category(db, category_id)
    if not category.is_active:
        raise Conflict(f"category {category_id} is not active")
    return category


def _get_active_agent(db: Session, agent_id: uuid.UUID) -> Agent:
    agent = get_agent(db, agent_id)
    if not agent.is_active:
        raise Conflict(f"agent {agent_id} is not active")
    return agent


def create_ticket(db: Session, payload: TicketCreate) -> Ticket:
    customer = get_customer(db, payload.customer_id)
    _require_active(customer)

    category = None
    if payload.category_id is not None:
        category = _get_active_category(db, payload.category_id)

    assignee = None
    if payload.assignee_id is not None:
        assignee = _get_active_agent(db, payload.assignee_id)

    if payload.priority is not None:
        priority = payload.priority
    elif category is not None:
        priority = category.default_priority
    else:
        priority = "normal"

    ticket_id = uuid.uuid4()
    ticket = Ticket(
        id=ticket_id,
        reference=build_reference(ticket_id),
        customer_id=payload.customer_id,
        category_id=payload.category_id,
        assignee_id=payload.assignee_id,
        subject=payload.subject,
        description=payload.description,
        priority=priority,
        due_at=payload.due_at,
    )
    db.add(ticket)
    db.flush()

    _record(db, ticket, "created", actor=None)
    if assignee is not None:
        _record(db, ticket, "assigned", field="assignee_id", new_value=assignee.id)
        # A ticket created already assigned is still an assignment, and the
        # assignee should hear about it the same way they would a hand-over.
        activity.record(
            db,
            event_type="ticket.assigned",
            ticket_id=ticket.id,
            customer_id=ticket.customer_id,
            payload={
                "from": None,
                "to": _stringify(assignee.id),
                "reference": ticket.reference,
            },
        )

    db.flush()
    db.refresh(ticket)
    return ticket


def update_ticket(db: Session, ticket_id: uuid.UUID, payload: TicketUpdate) -> Ticket:
    """Partial update of the editable fields. Allowed even on a terminal ticket."""
    ticket = get_ticket(db, ticket_id)
    data = payload.model_dump(exclude_unset=True)

    if "category_id" in data and data["category_id"] is not None:
        _get_active_category(db, data["category_id"])

    old_priority = ticket.priority
    old_category_id = ticket.category_id

    for field, value in data.items():
        setattr(ticket, field, value)

    if "priority" in data and data["priority"] != old_priority:
        _record(
            db, ticket, "priority_changed", field="priority",
            old_value=old_priority, new_value=data["priority"],
        )
    if "category_id" in data and data["category_id"] != old_category_id:
        _record(
            db, ticket, "category_changed", field="category_id",
            old_value=old_category_id, new_value=data["category_id"],
        )

    db.flush()
    db.refresh(ticket)
    return ticket


def change_status(
    db: Session,
    ticket_id: uuid.UUID,
    payload: TicketStatusChange,
    *,
    actor_agent_id: uuid.UUID | None = None,
) -> Ticket:
    """Move a ticket through the workflow.

    ``actor_agent_id`` is who to credit in the team activity feed, and is
    optional because this route predates the agent-context dependency and stays
    callable without one — the event is then recorded with no actor rather than
    not recorded at all.
    """
    ticket = get_ticket(db, ticket_id)
    current = ticket.status
    target = payload.status

    if target == current:
        return ticket

    allowed = ALLOWED_TRANSITIONS.get(current, ())
    if target not in allowed:
        raise Conflict(f"cannot move ticket from {current} to {target}")

    ticket.status = target
    if target == "resolved":
        ticket.resolved_at = _now()
    elif target == "closed":
        ticket.closed_at = _now()
    else:
        # Reopening (or any non-terminal move) clears both terminal stamps.
        ticket.resolved_at = None
        ticket.closed_at = None

    _record(
        db, ticket, "status_changed", field="status",
        old_value=current, new_value=target,
        comment=payload.comment, actor=payload.actor,
    )
    activity.record(
        db,
        event_type="ticket.status_changed",
        agent_id=actor_agent_id,
        ticket_id=ticket.id,
        customer_id=ticket.customer_id,
        payload={"from": current, "to": target, "reference": ticket.reference},
    )

    db.flush()
    db.refresh(ticket)
    return ticket


def assign_ticket(
    db: Session,
    ticket_id: uuid.UUID,
    payload: TicketAssignment,
    *,
    actor_agent_id: uuid.UUID | None = None,
) -> Ticket:
    """(Re)assign a ticket. See :func:`change_status` on ``actor_agent_id``."""
    ticket = get_ticket(db, ticket_id)
    if ticket.is_terminal:
        raise Conflict("cannot reassign a resolved or closed ticket")

    old_assignee_id = ticket.assignee_id
    new_assignee_id = payload.assignee_id

    if new_assignee_id == old_assignee_id:
        return ticket

    if new_assignee_id is not None:
        _get_active_agent(db, new_assignee_id)

    ticket.assignee_id = new_assignee_id

    event_type = "unassigned" if new_assignee_id is None else "assigned"
    _record(
        db, ticket, event_type, field="assignee_id",
        old_value=old_assignee_id, new_value=new_assignee_id,
        actor=payload.actor,
    )
    # One feed event covers both directions — "took #145" and "released #145"
    # are the same kind of news to the team; the payload says which.
    activity.record(
        db,
        event_type="ticket.assigned",
        agent_id=actor_agent_id,
        ticket_id=ticket.id,
        customer_id=ticket.customer_id,
        payload={
            "from": _stringify(old_assignee_id),
            "to": _stringify(new_assignee_id),
            "reference": ticket.reference,
        },
        # No mention row: the new assignee already sees this through the feed's
        # assignee rule, and `unread_mentions` is meant to count someone
        # deliberately naming you, not every routine queue move.
    )

    db.flush()
    db.refresh(ticket)
    return ticket


def escalate_ticket(
    db: Session, ticket_id: uuid.UUID, payload: TicketEscalation
) -> Ticket:
    ticket = get_ticket(db, ticket_id)
    if ticket.is_terminal:
        raise Conflict("cannot escalate a resolved or closed ticket")
    if ticket.escalation_level >= MAX_ESCALATION_LEVEL:
        raise Conflict("ticket is already at the maximum escalation level")

    old_level = ticket.escalation_level
    ticket.escalation_level = old_level + 1
    ticket.escalated_at = _now()

    _record(
        db, ticket, "escalated", field="escalation_level",
        old_value=old_level, new_value=ticket.escalation_level,
        comment=payload.comment, actor=payload.actor,
    )

    if payload.raise_priority:
        old_priority = ticket.priority
        next_index = min(
            _PRIORITY_ORDER[old_priority] + 1, len(TICKET_PRIORITIES) - 1
        )
        new_priority = TICKET_PRIORITIES[next_index]
        if new_priority != old_priority:
            ticket.priority = new_priority
            _record(
                db, ticket, "priority_changed", field="priority",
                old_value=old_priority, new_value=new_priority,
                actor=payload.actor,
            )

    db.flush()
    db.refresh(ticket)
    return ticket


def delete_ticket(db: Session, ticket_id: uuid.UUID) -> None:
    """Hard delete. Events cascade; there are no attachments to clean up."""
    ticket = get_ticket(db, ticket_id)
    db.delete(ticket)
    db.flush()


# --------------------------------------------------------------------------- #
# Ticket events
# --------------------------------------------------------------------------- #
def list_events(
    db: Session, ticket_id: uuid.UUID, *, limit: int = 200, offset: int = 0
) -> tuple[list[TicketEvent], int]:
    get_ticket(db, ticket_id)
    where = (TicketEvent.ticket_id == ticket_id,)
    total = db.scalar(select(func.count()).select_from(TicketEvent).where(*where)) or 0
    rows = db.scalars(
        select(TicketEvent)
        .where(*where)
        .order_by(TicketEvent.created_at.desc(), TicketEvent.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total


def add_comment(
    db: Session, ticket_id: uuid.UUID, payload: TicketCommentCreate
) -> TicketEvent:
    """The only way a client writes a ticket_events row directly."""
    ticket = get_ticket(db, ticket_id)
    event = _record(
        db, ticket, "commented", comment=payload.comment, actor=payload.actor
    )
    return event
