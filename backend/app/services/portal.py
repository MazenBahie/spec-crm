"""Customer-portal service layer.

Pure functions over a SQLAlchemy ``Session`` -- no FastAPI imports, same
contract as ``app.services.tickets``: ``flush()``/``refresh()`` but never
``commit()``.

Every ticket-scoped function here takes ``customer_id`` from the caller's
verified session (never from the request body or path) and treats a
cross-customer lookup as :class:`~app.services.errors.NotFound`, not
:class:`~app.services.errors.Forbidden` -- a deliberate divergence from
``Forbidden``'s documented reasoning for internal, trusted-staff callers
(``app/services/errors.py:18-25``). On a public surface, "not yours" and
"does not exist" must look identical, or the response leaks the existence of
another customer's ticket id.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps_portal import hash_token
from app.core.config import settings
from app.models.customer import ContactDetail, Customer
from app.models.portal import PortalSession, PortalUser, TicketFeedback
from app.models.ticket import Ticket, TicketEvent
from app.schemas.portal import PortalLogin, PortalSignup, PortalTicketCreate, TicketFeedbackCreate
from app.schemas.ticket import TicketCreate
from app.services import tickets as tickets_svc
from app.services.errors import Conflict, Forbidden, NotFound

# Only these event types are safe to show a customer: everything else is
# internal triage/routing detail (assignment, escalation, category,
# priority) or an as-yet-unclassified comment -- see list_portal_ticket_events.
CUSTOMER_VISIBLE_EVENT_TYPES = ("created", "status_changed")

_NO_MATCH = Forbidden("no matching customer account for this email")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _find_active_customer_by_email(db: Session, email: str) -> Customer | None:
    stmt = (
        select(Customer)
        .join(ContactDetail, ContactDetail.customer_id == Customer.id)
        .where(
            ContactDetail.kind == "email",
            func.lower(ContactDetail.value) == email.lower(),
            Customer.status == "active",
        )
    )
    return db.scalars(stmt).first()


def _create_session(db: Session, portal_user: PortalUser) -> tuple[str, datetime]:
    raw = secrets.token_urlsafe(32)
    expires_at = _now() + timedelta(days=settings.portal_session_ttl_days)
    session = PortalSession(
        portal_user_id=portal_user.id,
        token_hash=hash_token(raw),
        expires_at=expires_at,
    )
    db.add(session)
    db.flush()
    return raw, expires_at


def signup(db: Session, payload: PortalSignup) -> tuple[PortalUser, str, datetime]:
    customer = _find_active_customer_by_email(db, payload.email)
    if customer is None:
        # Same message as "matched an archived customer" -- collapsing the
        # two cases avoids confirming to an outsider that the email exists.
        raise _NO_MATCH

    existing = db.scalars(
        select(PortalUser).where(func.lower(PortalUser.email) == payload.email.lower())
    ).first()
    if existing is not None:
        raise Conflict("an account with this email already exists")

    password_hash = bcrypt.hashpw(payload.password.encode(), bcrypt.gensalt()).decode()
    portal_user = PortalUser(
        customer_id=customer.id,
        email=payload.email,
        password_hash=password_hash,
        display_name=payload.display_name,
    )
    db.add(portal_user)
    db.flush()
    db.refresh(portal_user)

    raw, expires_at = _create_session(db, portal_user)
    return portal_user, raw, expires_at


def login(db: Session, payload: PortalLogin) -> tuple[PortalUser, str, datetime]:
    portal_user = db.scalars(
        select(PortalUser).where(func.lower(PortalUser.email) == payload.email.lower())
    ).first()
    if (
        portal_user is None
        or not portal_user.is_active
        or not bcrypt.checkpw(
            payload.password.encode(), portal_user.password_hash.encode()
        )
    ):
        # One branch, mirroring get_current_agent's design (deps.py:51-56):
        # unknown email, wrong password, and a deactivated account all read
        # the same to the caller.
        raise _NO_MATCH
    raw, expires_at = _create_session(db, portal_user)
    return portal_user, raw, expires_at


def logout(db: Session, portal_user_id: uuid.UUID, raw_token: str) -> None:
    """Idempotent: revoking an already-revoked or unknown token is a no-op."""
    token_hash = hash_token(raw_token)
    session = db.scalars(
        select(PortalSession).where(
            PortalSession.portal_user_id == portal_user_id,
            PortalSession.token_hash == token_hash,
            PortalSession.revoked_at.is_(None),
        )
    ).first()
    if session is None:
        return
    session.revoked_at = _now()
    db.flush()


# --------------------------------------------------------------------------- #
# Tickets -- every function below is scoped to `customer_id` from the caller's
# verified session, never a request-supplied value.
# --------------------------------------------------------------------------- #
def list_portal_tickets(
    db: Session, customer_id: uuid.UUID, *, limit: int = 20, offset: int = 0
) -> tuple[list[Ticket], int]:
    return tickets_svc.list_customer_tickets(db, customer_id, limit=limit, offset=offset)


def get_portal_ticket(db: Session, customer_id: uuid.UUID, ticket_id: uuid.UUID) -> Ticket:
    ticket = tickets_svc.get_ticket(db, ticket_id)
    if ticket.customer_id != customer_id:
        # Same message shape as a genuinely missing ticket -- see module
        # docstring: "not yours" must look identical to "does not exist".
        raise NotFound(f"ticket {ticket_id} not found")
    return ticket


def create_portal_ticket(
    db: Session, customer_id: uuid.UUID, payload: PortalTicketCreate
) -> Ticket:
    ticket_create = TicketCreate(
        customer_id=customer_id,
        subject=payload.subject,
        description=payload.description,
        category_id=payload.category_id,
        priority=None,
        assignee_id=None,
        due_at=None,
    )
    return tickets_svc.create_ticket(db, ticket_create)


def list_portal_ticket_events(
    db: Session, customer_id: uuid.UUID, ticket_id: uuid.UUID
) -> list[TicketEvent]:
    get_portal_ticket(db, customer_id, ticket_id)  # ownership + existence
    events, _total = tickets_svc.list_events(db, ticket_id, limit=200, offset=0)
    # Internal-only types (priority_changed, category_changed, assigned,
    # unassigned, escalated, commented) never reach the portal. `commented`
    # is excluded too: TicketEvent has no visibility flag yet to distinguish
    # an internal comment from a customer-facing reply, so until two-way
    # messaging lands (with a real visibility concept, or replies routed
    # through ChannelMessage instead), the safe default is to show none.
    return [e for e in events if e.event_type in CUSTOMER_VISIBLE_EVENT_TYPES]


def submit_feedback(
    db: Session, customer_id: uuid.UUID, ticket_id: uuid.UUID, payload: TicketFeedbackCreate
) -> TicketFeedback:
    ticket = get_portal_ticket(db, customer_id, ticket_id)
    if not ticket.is_terminal:
        raise Conflict("feedback can only be submitted once a ticket is resolved or closed")

    feedback = db.scalars(
        select(TicketFeedback).where(TicketFeedback.ticket_id == ticket_id)
    ).first()
    if feedback is None:
        feedback = TicketFeedback(ticket_id=ticket_id, rating=payload.rating, comment=payload.comment)
        db.add(feedback)
    else:
        feedback.rating = payload.rating
        feedback.comment = payload.comment
    db.flush()
    db.refresh(feedback)
    return feedback


def get_feedback(
    db: Session, customer_id: uuid.UUID, ticket_id: uuid.UUID
) -> TicketFeedback | None:
    get_portal_ticket(db, customer_id, ticket_id)  # ownership + existence
    return db.scalars(
        select(TicketFeedback).where(TicketFeedback.ticket_id == ticket_id)
    ).first()
