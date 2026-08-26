"""Agent-dashboard HTTP routes.

Every route below is agent-scoped: the router itself depends on
``get_current_agent``, so a request without a valid ``X-Agent-Id`` never reaches
a handler. Nothing here takes an agent id as a parameter — an agent can only
ever read their own dashboard.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import CurrentAgent, get_current_agent
from app.db.session import get_db
from app.schemas.agent import ActivityEventRead, DashboardSummary
from app.schemas.customer import CustomerRead
from app.schemas.ticket import TicketRead
from app.services import activity
from app.services import agent_dashboard as svc

router = APIRouter(tags=["dashboard"], dependencies=[Depends(get_current_agent)])

DbDep = Annotated[Session, Depends(get_db)]


@router.get("/dashboard/summary", response_model=DashboardSummary)
def get_summary(db: DbDep, agent: CurrentAgent) -> DashboardSummary:
    return svc.dashboard_summary(db, agent.id)


@router.get("/dashboard/queue", response_model=list[TicketRead])
def get_queue(
    db: DbDep,
    agent: CurrentAgent,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[TicketRead]:
    """The caller's open tickets, most pressing first.

    A plain list rather than a `Page`: this is a shift's worth of work, capped
    at 100, not something an agent pages through.
    """
    return [TicketRead.model_validate(t) for t in svc.list_my_queue(db, agent.id, limit=limit)]


@router.get("/dashboard/recent-customers", response_model=list[CustomerRead])
def get_recent_customers(
    db: DbDep,
    agent: CurrentAgent,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> list[CustomerRead]:
    return [
        CustomerRead.model_validate(c)
        for c in svc.recent_customers(db, agent.id, limit=limit)
    ]


@router.get("/dashboard/activity", response_model=list[ActivityEventRead])
def get_activity(
    db: DbDep,
    agent: CurrentAgent,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[ActivityEventRead]:
    return [
        ActivityEventRead.model_validate(e)
        for e in activity.feed_for_agent(db, agent.id, limit=limit)
    ]
