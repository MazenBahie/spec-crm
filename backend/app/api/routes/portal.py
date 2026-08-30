"""Customer-portal HTTP routes.

Service-layer errors are translated centrally by the handlers registered in
``app.main``; these handlers keep the route bodies free of try/except noise.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.api.deps_portal import CurrentPortalUser, bearer_scheme, get_current_portal_user
from app.db.session import get_db
from app.models.portal import PortalUser
from app.schemas.customer import Page
from app.schemas.portal import (
    PortalAuthResponse,
    PortalLogin,
    PortalSignup,
    PortalTicketCreate,
    PortalUserRead,
    TicketFeedbackCreate,
    TicketFeedbackRead,
)
from app.schemas.ticket import TicketEventRead, TicketRead
from app.services import portal as svc

router = APIRouter(prefix="/portal", tags=["portal"])

DbDep = Annotated[Session, Depends(get_db)]


def _auth_response(portal_user, raw_token: str, expires_at) -> PortalAuthResponse:
    return PortalAuthResponse(
        token=raw_token,
        expires_at=expires_at,
        portal_user=PortalUserRead.model_validate(portal_user),
    )


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
@router.post(
    "/auth/signup", response_model=PortalAuthResponse, status_code=status.HTTP_201_CREATED
)
def signup(payload: PortalSignup, db: DbDep) -> PortalAuthResponse:
    portal_user, raw_token, expires_at = svc.signup(db, payload)
    return _auth_response(portal_user, raw_token, expires_at)


@router.post("/auth/login", response_model=PortalAuthResponse)
def login(payload: PortalLogin, db: DbDep) -> PortalAuthResponse:
    portal_user, raw_token, expires_at = svc.login(db, payload)
    return _auth_response(portal_user, raw_token, expires_at)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    db: DbDep,
    portal_user: Annotated[PortalUser, Depends(get_current_portal_user)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> Response:
    """Revokes the caller's own session.

    Depends on ``get_current_portal_user``, not ``CurrentPortalUser`` --
    logging out must succeed even if the customer has since been archived
    (that check only guards data-access routes, not "please stop trusting
    this token").
    """
    svc.logout(db, portal_user.id, credentials.credentials)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/auth/me", response_model=PortalUserRead)
def get_me(portal_user: CurrentPortalUser) -> PortalUserRead:
    return PortalUserRead.model_validate(portal_user)


# --------------------------------------------------------------------------- #
# Tickets
# --------------------------------------------------------------------------- #
@router.get("/tickets", response_model=Page[TicketRead])
def list_tickets(
    db: DbDep,
    portal_user: CurrentPortalUser,
    limit: int = 20,
    offset: int = 0,
) -> Page[TicketRead]:
    items, total = svc.list_portal_tickets(
        db, portal_user.customer_id, limit=limit, offset=offset
    )
    return Page[TicketRead](items=[TicketRead.model_validate(t) for t in items], total=total)


@router.post("/tickets", response_model=TicketRead, status_code=status.HTTP_201_CREATED)
def create_ticket(
    payload: PortalTicketCreate, db: DbDep, portal_user: CurrentPortalUser
) -> TicketRead:
    ticket = svc.create_portal_ticket(db, portal_user.customer_id, payload)
    return TicketRead.model_validate(ticket)


@router.get("/tickets/{ticket_id}", response_model=TicketRead)
def get_ticket(ticket_id: uuid.UUID, db: DbDep, portal_user: CurrentPortalUser) -> TicketRead:
    ticket = svc.get_portal_ticket(db, portal_user.customer_id, ticket_id)
    return TicketRead.model_validate(ticket)


@router.get("/tickets/{ticket_id}/events", response_model=list[TicketEventRead])
def list_ticket_events(
    ticket_id: uuid.UUID, db: DbDep, portal_user: CurrentPortalUser
) -> list[TicketEventRead]:
    events = svc.list_portal_ticket_events(db, portal_user.customer_id, ticket_id)
    return [TicketEventRead.model_validate(e) for e in events]


# --------------------------------------------------------------------------- #
# Feedback
# --------------------------------------------------------------------------- #
@router.get("/tickets/{ticket_id}/feedback", response_model=TicketFeedbackRead | None)
def get_feedback(
    ticket_id: uuid.UUID, db: DbDep, portal_user: CurrentPortalUser
) -> TicketFeedbackRead | None:
    feedback = svc.get_feedback(db, portal_user.customer_id, ticket_id)
    return TicketFeedbackRead.model_validate(feedback) if feedback else None


@router.post("/tickets/{ticket_id}/feedback", response_model=TicketFeedbackRead)
def submit_feedback(
    ticket_id: uuid.UUID,
    payload: TicketFeedbackCreate,
    db: DbDep,
    portal_user: CurrentPortalUser,
) -> TicketFeedbackRead:
    feedback = svc.submit_feedback(db, portal_user.customer_id, ticket_id, payload)
    return TicketFeedbackRead.model_validate(feedback)
