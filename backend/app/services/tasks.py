"""Agent task and reminder service layer.

Every function takes the calling agent's id and scopes to it: a task belongs to
exactly one agent and no other agent may read, change, complete or delete it.
The ownership check lives here rather than in the route so it cannot be skipped
by a new caller.

Pure functions over a SQLAlchemy ``Session`` — no FastAPI imports. Callers own
the transaction boundary; these functions ``flush`` but never commit.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent import AgentTask
from app.schemas.agent import AgentTaskCreate, AgentTaskUpdate
from app.services.customers import get_customer
from app.services.errors import Forbidden, NotFound
from app.services.tickets import get_ticket


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_links(
    db: Session, ticket_id: uuid.UUID | None, customer_id: uuid.UUID | None
) -> None:
    """404 early rather than letting the FK reject the insert.

    A task may link to a ticket, a customer, both, or neither — but a link that
    is set must point at something that exists.
    """
    if ticket_id is not None:
        get_ticket(db, ticket_id)
    if customer_id is not None:
        get_customer(db, customer_id)


def _owned(db: Session, task_id: uuid.UUID, agent_id: uuid.UUID) -> AgentTask:
    task = db.get(AgentTask, task_id)
    if task is None:
        raise NotFound(f"task {task_id} not found")
    if task.agent_id != agent_id:
        raise Forbidden("that task belongs to another agent")
    return task


def list_tasks(
    db: Session,
    agent_id: uuid.UUID,
    *,
    status: str | None = None,
    due_before: datetime | None = None,
    limit: int = 100,
) -> list[AgentTask]:
    """This agent's tasks, soonest reminder first.

    Tasks with no ``remind_at`` sort after the ones that have one — an
    un-dated task is not urgent — using an explicit "is null" key rather than
    NULLS LAST, which SQLite does not support.
    """
    filters = [AgentTask.agent_id == agent_id]
    if status:
        filters.append(AgentTask.status == status)
    if due_before is not None:
        # An un-dated task is never "due before" anything.
        filters.append(AgentTask.remind_at.is_not(None))
        filters.append(AgentTask.remind_at < due_before)

    return list(
        db.scalars(
            select(AgentTask)
            .where(*filters)
            .order_by(
                AgentTask.remind_at.is_(None).asc(),
                AgentTask.remind_at.asc(),
                AgentTask.created_at.desc(),
            )
            .limit(limit)
        )
    )


def get_task(db: Session, task_id: uuid.UUID, agent_id: uuid.UUID) -> AgentTask:
    return _owned(db, task_id, agent_id)


def create_task(
    db: Session, agent_id: uuid.UUID, payload: AgentTaskCreate
) -> AgentTask:
    _validate_links(db, payload.ticket_id, payload.customer_id)
    task = AgentTask(agent_id=agent_id, **payload.model_dump())
    db.add(task)
    db.flush()
    db.refresh(task)
    return task


def update_task(
    db: Session, task_id: uuid.UUID, agent_id: uuid.UUID, payload: AgentTaskUpdate
) -> AgentTask:
    task = _owned(db, task_id, agent_id)
    data = payload.model_dump(exclude_unset=True)
    _validate_links(db, data.get("ticket_id"), data.get("customer_id"))

    status = data.pop("status", None)
    for field, value in data.items():
        setattr(task, field, value)
    if status is not None:
        _set_status(task, status)

    db.flush()
    db.refresh(task)
    return task


def _set_status(task: AgentTask, status: str) -> None:
    """Move a task between open and done, keeping ``completed_at`` honest.

    Idempotent in both directions: re-completing an already-done task leaves the
    original ``completed_at`` alone, so "when was this finished" does not drift
    every time a double-clicked checkbox fires twice.
    """
    if status == "done":
        if task.status != "done":
            task.status = "done"
            task.completed_at = _now()
    else:
        task.status = status
        task.completed_at = None


def complete_task(db: Session, task_id: uuid.UUID, agent_id: uuid.UUID) -> AgentTask:
    task = _owned(db, task_id, agent_id)
    _set_status(task, "done")
    db.flush()
    db.refresh(task)
    return task


def reopen_task(db: Session, task_id: uuid.UUID, agent_id: uuid.UUID) -> AgentTask:
    task = _owned(db, task_id, agent_id)
    _set_status(task, "open")
    db.flush()
    db.refresh(task)
    return task


def delete_task(db: Session, task_id: uuid.UUID, agent_id: uuid.UUID) -> None:
    task = _owned(db, task_id, agent_id)
    db.delete(task)
    db.flush()
