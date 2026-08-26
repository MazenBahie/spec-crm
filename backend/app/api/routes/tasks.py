"""Agent task and reminder HTTP routes.

Agent-scoped at router level. Reaching another agent's task is a 403, not a
404 — see ``app.services.errors.Forbidden``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentAgent, get_current_agent
from app.db.session import get_db
from app.schemas.agent import (
    AgentTaskCreate,
    AgentTaskRead,
    AgentTaskStatus,
    AgentTaskUpdate,
)
from app.services import tasks as svc

router = APIRouter(tags=["tasks"], dependencies=[Depends(get_current_agent)])

DbDep = Annotated[Session, Depends(get_db)]


@router.get("/tasks", response_model=list[AgentTaskRead])
def list_tasks(
    db: DbDep,
    agent: CurrentAgent,
    status_filter: Annotated[AgentTaskStatus | None, Query(alias="status")] = None,
    due_before: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[AgentTaskRead]:
    items = svc.list_tasks(
        db, agent.id, status=status_filter, due_before=due_before, limit=limit
    )
    return [AgentTaskRead.model_validate(t) for t in items]


@router.post("/tasks", response_model=AgentTaskRead, status_code=status.HTTP_201_CREATED)
def create_task(payload: AgentTaskCreate, db: DbDep, agent: CurrentAgent) -> AgentTaskRead:
    return AgentTaskRead.model_validate(svc.create_task(db, agent.id, payload))


@router.get("/tasks/{task_id}", response_model=AgentTaskRead)
def get_task(task_id: uuid.UUID, db: DbDep, agent: CurrentAgent) -> AgentTaskRead:
    return AgentTaskRead.model_validate(svc.get_task(db, task_id, agent.id))


@router.patch("/tasks/{task_id}", response_model=AgentTaskRead)
def update_task(
    task_id: uuid.UUID, payload: AgentTaskUpdate, db: DbDep, agent: CurrentAgent
) -> AgentTaskRead:
    return AgentTaskRead.model_validate(svc.update_task(db, task_id, agent.id, payload))


@router.post("/tasks/{task_id}/complete", response_model=AgentTaskRead)
def complete_task(task_id: uuid.UUID, db: DbDep, agent: CurrentAgent) -> AgentTaskRead:
    """Mark a task done. Idempotent — an already-done task keeps its original
    ``completed_at`` and answers 200, so a double-clicked checkbox is harmless.
    """
    return AgentTaskRead.model_validate(svc.complete_task(db, task_id, agent.id))


@router.post("/tasks/{task_id}/reopen", response_model=AgentTaskRead)
def reopen_task(task_id: uuid.UUID, db: DbDep, agent: CurrentAgent) -> AgentTaskRead:
    """Undo a completion. Clears ``completed_at``; also idempotent."""
    return AgentTaskRead.model_validate(svc.reopen_task(db, task_id, agent.id))


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: uuid.UUID, db: DbDep, agent: CurrentAgent) -> Response:
    svc.delete_task(db, task_id, agent.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
