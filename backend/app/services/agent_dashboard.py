"""Agent-dashboard read models.

Read-only aggregation over tickets, customers, tasks and activity for the one
screen an agent opens at the start of a shift. Nothing here writes.

Pure functions over a SQLAlchemy ``Session`` — no FastAPI imports.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.agent import AgentTask
from app.models.customer import Customer
from app.models.ticket import Ticket
from app.schemas.agent import DashboardSummary
from app.services import activity
from app.services.tickets import OPEN_STATUSES, priority_rank

# How far back "recently helped" reaches on the customer snapshot.
RECENT_CUSTOMER_DAYS = 14


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _my_open_tickets(agent_id: uuid.UUID):
    """The "in my queue" predicate: mine, and not finished with."""
    return (
        Ticket.assignee_id == agent_id,
        Ticket.status.in_(OPEN_STATUSES),
    )


def list_my_queue(
    db: Session, agent_id: uuid.UUID, *, limit: int = 50
) -> list[Ticket]:
    """This agent's open tickets, most pressing first.

    Sorted urgent-first, then by soonest due date, then most recently touched.
    Tickets with no ``due_at`` sort after every dated one via an explicit
    "is null" key rather than NULLS LAST, which SQLite does not support — the
    same trick as :func:`app.services.tasks.list_tasks`.
    """
    return list(
        db.scalars(
            select(Ticket)
            .where(*_my_open_tickets(agent_id))
            .order_by(
                priority_rank().desc(),
                Ticket.due_at.is_(None).asc(),
                Ticket.due_at.asc(),
                Ticket.updated_at.desc(),
            )
            .limit(limit)
        )
    )


def recent_customers(
    db: Session, agent_id: uuid.UUID, *, limit: int = 10
) -> list[Customer]:
    """Customers this agent has touched lately, most recent first.

    "Touched" means holding a ticket assigned to this agent that has been
    updated inside the window — including resolved and closed ones, since
    "who did I just finish with" is exactly what this panel is for.

    Interactions are not consulted: ``Interaction.author`` is still free text
    with no agent id behind it, so it cannot be attributed reliably. The auth
    story that reconciles the two should widen this.
    """
    cutoff = _now() - timedelta(days=RECENT_CUSTOMER_DAYS)
    last_touch = func.max(Ticket.updated_at).label("last_touch")

    rows = db.execute(
        select(Customer, last_touch)
        .join(Ticket, Ticket.customer_id == Customer.id)
        .where(Ticket.assignee_id == agent_id, Ticket.updated_at >= cutoff)
        .group_by(Customer.id)
        .order_by(last_touch.desc())
        .limit(limit)
    ).all()
    return [row[0] for row in rows]


def dashboard_summary(db: Session, agent_id: uuid.UUID) -> DashboardSummary:
    """The four numbers along the top of the dashboard."""
    now = _now()

    open_assigned = (
        db.scalar(
            select(func.count())
            .select_from(Ticket)
            .where(*_my_open_tickets(agent_id))
        )
        or 0
    )
    overdue = (
        db.scalar(
            select(func.count())
            .select_from(Ticket)
            .where(
                *_my_open_tickets(agent_id),
                Ticket.due_at.is_not(None),
                Ticket.due_at < now,
            )
        )
        or 0
    )
    # Day boundaries in UTC, not the agent's local zone: the server has no idea
    # where they are sitting. The frontend renders the underlying timestamps in
    # the browser's zone, so a reminder near midnight can read as "tomorrow"
    # next to a count that says today — the cost of not modelling an agent
    # timezone yet.
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tasks_due_today = (
        db.scalar(
            select(func.count())
            .select_from(AgentTask)
            .where(
                AgentTask.agent_id == agent_id,
                AgentTask.status == "open",
                AgentTask.remind_at.is_not(None),
                AgentTask.remind_at >= day_start,
                AgentTask.remind_at < day_start + timedelta(days=1),
            )
        )
        or 0
    )
    unread_mentions = activity.count_recent_mentions(
        db, agent_id, since=now - timedelta(days=activity.MENTION_WINDOW_DAYS)
    )

    return DashboardSummary(
        open_assigned=open_assigned,
        overdue=overdue,
        tasks_due_today=tasks_due_today,
        unread_mentions=unread_mentions,
    )
