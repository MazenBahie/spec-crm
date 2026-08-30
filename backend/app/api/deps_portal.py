"""Portal-user authentication.

Unlike ``app.api.deps`` (a documented placeholder that trusts a bare
``X-Agent-Id`` header), this is real bearer-token auth: the raw token is never
stored, only the SHA-256 hash of it, compared against ``portal_sessions``.
Kept in its own module rather than appended to ``deps.py`` because the trust
model is categorically different and conflating the two would blur the
placeholder-vs-real distinction that module's docstring currently signals.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.portal import PortalSession, PortalUser
from app.services.errors import Forbidden

bearer_scheme = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="a valid session token is required"
)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _lookup(
    db: Session, credentials: HTTPAuthorizationCredentials | None
) -> PortalUser | None:
    """Resolve a bearer token to an active portal user, or None."""
    if credentials is None or not credentials.credentials.strip():
        return None
    token_hash = hash_token(credentials.credentials.strip())
    session = db.scalars(
        select(PortalSession).where(
            PortalSession.token_hash == token_hash,
            PortalSession.revoked_at.is_(None),
            PortalSession.expires_at > datetime.now(timezone.utc),
        )
    ).first()
    if session is None:
        return None
    portal_user = db.get(PortalUser, session.portal_user_id)
    if portal_user is None or not portal_user.is_active:
        return None
    return portal_user


def get_current_portal_user(
    db: Annotated[Session, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> PortalUser:
    """The portal user making this request, or 401.

    A missing token, an unknown/expired/revoked one, and a deactivated portal
    user are all the same answer -- 401 -- matching get_current_agent's
    one-branch-to-handle design (app/api/deps.py:51-56).
    """
    portal_user = _lookup(db, credentials)
    if portal_user is None:
        raise _UNAUTHORIZED
    return portal_user


def require_active_portal_customer(
    portal_user: Annotated[PortalUser, Depends(get_current_portal_user)],
) -> PortalUser:
    """Same portal user, but 403s if their customer has since been archived.

    Mirrors the reasoning of ``_require_active``
    (backend/app/services/customers.py:145-147): the session token can still
    be structurally valid while the underlying account should no longer see
    or touch anything. No background job revokes the session proactively --
    every request re-checks live, matching the "computed on read" precedent
    already used for ``Ticket.is_overdue``.
    """
    if portal_user.customer.is_archived:
        raise Forbidden("customer account is not active")
    return portal_user


CurrentPortalUser = Annotated[PortalUser, Depends(require_active_portal_customer)]
