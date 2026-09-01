# Story 15 — Staff Authentication, Users & Roles

## Prerequisites

- Story 03 (Ticket Management) completed: `Agent` (`backend/app/models/ticket.py:66-77`) is the staff-identity table this story extends **in place** — `password_hash` and `role_id` are added as new nullable columns rather than introducing a separate `users` table. This means `tickets.assignee_id`, `agent_tasks.agent_id`, `quick_replies.owner_agent_id`, `activity_events.agent_id`, and every other existing FK to `agents.id` needs **no migration at all** — every current reference keeps working unchanged.
- Story 05 (Agent Dashboard), Story 08-13 (AI features), Story 14 (Reports): every agent-scoped router in these stories already declares `Depends(get_current_agent)` (router-level or per-route via the `CurrentAgent`/`CurrentAgentId` type aliases in `backend/app/api/deps.py:83-85`). This story changes **only the verification mechanism** inside `get_current_agent` — the function name, its `Annotated` aliases, and every call site in `dashboard.py`, `tasks.py`, `quick_replies.py`, `ai.py`, `reports.py` (per `.squad/plans/checkout/00-overview.md` lines 9, 57 `dependencies=[Depends(get_current_agent)]`) stay untouched.
- Story 06 (Customer Portal) completed: this story's entire design — `PortalUser`/`PortalSession` (`backend/app/models/portal.py:33-95`), `backend/app/api/deps_portal.py`, `backend/app/services/portal.py`'s `login`/`signup`/`_create_session`/`logout` functions — is the literal template mirrored here for the staff side, substituting `Agent`/`AgentSession` for `PortalUser`/`PortalSession`. `bcrypt>=4.1` is already a dependency (`backend/pyproject.toml`, added in Story 06) — no new dependency needed.
- **No prior story has ever removed or replaced a dependency's verification mechanism while keeping its name.** This story is the first to do so: `get_current_agent` keeps its name and signature shape (`Agent` in, `Agent` out) so that Stories 05/08-14's route code needs zero changes, but everything *inside* it changes from "trust a header" to "verify a bearer token against a database row" — see Backend Tasks §4.
- Coordinate with Story 16 (Permissions & Access Control): this story ships **no permission enforcement**. Every successfully-authenticated agent can call every endpoint any agent could call before (including the new `/roles` and `/agents/{id}/set-password` endpoints this story adds) — Story 16 is the one that restricts those to specific roles via a new `require_permission(...)` dependency this story does not define.

---

## Story Goal

Replace the `X-Agent-Id` trusted-header placeholder (`backend/app/api/deps.py`, documented at lines 1-12 as exactly that: "any caller who knows an agent's uuid is that agent") with real, credential-based staff authentication, and let an admin assign a named role to each agent:

1. **Login/logout** — `POST /api/auth/login` (email + password → bearer token), `POST /api/auth/logout` (revokes the current session). Modeled byte-for-byte on the portal's own `/api/portal/auth/*` flow (Story 06).
2. **Sessions** — a new `agent_sessions` table, structurally identical to `portal_sessions`: the raw token is never stored, only its SHA-256 hash; a session is soft-revoked, never deleted.
3. **Roles** — a new `roles` table (not an enum: an admin can add a role later with no migration) seeded with three rows (`admin`, `manager`, `agent`) and a nullable `agents.role_id` FK to it.
4. **Password management** — `POST /api/agents/{id}/set-password`, so an admin can give an existing (or newly created) agent login access, and `PATCH /api/agents/{id}/role` to assign a role.
5. **A working staff login screen** — replaces `DashboardPage.tsx`'s `AgentPicker` (`frontend/src/pages/DashboardPage.tsx:56-99`, explicitly commented today as *"the placeholder for a sign-in screen"*) with a real `LoginPage`, and gates every staff route behind it.

**Bootstrap problem, and how this story resolves it:** every new write endpoint this story adds (`set-password`, role CRUD/assignment) requires a valid session — but the very first login needs *someone* to already have a password. This story's migration seeds exactly one real, credentialed `admin` account (`admin@crm.local`, role `admin`, see Backend Tasks §1) so the very first login after this migration runs is always possible. Its password **must be rotated immediately after first deploy** — see Edge Cases.

**Out of scope (explicit, deferred to named follow-up stories):**
- Any permission/role-based *restriction* on what an authenticated agent can do — every agent can do everything an agent could do before, plus call the new endpoints this story adds. Story 16 (Permissions & Access Control) is the only place enforcement is added.
- Gating the pre-existing, still-open `customers.router`/`tickets.router`/`channels.router` — unchanged by this story; see `00-overview.md`'s "Known cross-story gap" (updated by Story 16, not this one).
- Self-service password reset / "forgot password" email flow — no email-sending infrastructure exists anywhere in this codebase (channel providers are all stubbed, see Story 04's arc). Only an already-authenticated agent can set another agent's password.
- Converting `TicketEvent.actor`/`Interaction.author` from free text to a real FK — both remain free-text strings, as documented in `deps.py`'s own pre-existing module docstring; not part of this intake.

---

## Context — Read These Files First

1. `backend/app/api/deps_portal.py` (read in full, 93 lines) — the exact mechanism this story ports to the staff side: `hash_token()` (lines 33-34), `_lookup()` (37-56, token-hash match + `revoked_at IS NULL` + `expires_at > now()` + `is_active`), `get_current_portal_user()` (59-72, one 401 branch for every failure mode), `bearer_scheme = HTTPBearer(auto_error=False)` (line 26).
2. `backend/app/api/deps.py` (read in full, 86 lines) — the module to rewrite. Its current docstring (lines 1-12) is the "placeholder" language to remove. `_lookup()` (33-44), `get_current_agent()` (47-60), `get_optional_agent()` (63-73, **must keep its no-raise contract** — `backend/app/api/routes/channels.py:69-92`'s `send_ticket_message` depends on `OptionalAgent` staying optional), `require_agent_id()` (76-80), and the three `Annotated` aliases (83-85) that every other story's route code imports by name.
3. `backend/app/models/portal.py:65-95` — `PortalSession`, the structural template for the new `AgentSession` (same columns: `token_hash` unique+indexed `String(64)`, `expires_at` indexed, `revoked_at` nullable, `created_at`).
4. `backend/app/models/ticket.py:66-77` — the exact `Agent` class to extend with `password_hash`/`role_id`/`role`. Note `email: Mapped[str | None]` is already unique (line 71) — login looks it up case-insensitively via `func.lower(Agent.email)`, mirroring `app/services/portal.py:104-106`.
5. `backend/app/services/portal.py` (read in full, 214 lines) — `_create_session()` (62-72), `signup()` (75-100), `login()` (103-119, the "one branch" collapse of unknown-email/wrong-password/deactivated), `logout()` (122-135). This story's `backend/app/services/agent_auth.py` mirrors `login`/`logout`/`_create_session` almost line for line.
6. `backend/app/core/config.py` (read in full, 28 lines) — `portal_session_ttl_days: int = 14` (line 15) is the exact shape for the new `agent_session_ttl_days` setting; insert it in the same style, before `model_config` (line 25).
7. `backend/app/models/customer.py:44-45` — `_pk()`, the uuid-primary-key helper every new table in this story uses.
8. `backend/app/models/__init__.py` (read in full, 68 lines) — the re-export list every new model must be added to, or Alembic autogenerate and `Base.metadata.create_all` (used by the SQLite test DB) never see the new tables.
9. `backend/app/schemas/ticket.py:31-54` — `AgentBase`/`AgentCreate`/`AgentUpdate`/`AgentRead`. `AgentRead` (50-54) gains `role_id: uuid.UUID | None`; `AgentUpdate` (44-47) gains the same, optional.
10. `backend/app/schemas/portal.py` (read in full, 82 lines) — `PortalLogin`/`PortalAuthResponse` (37-56) are the schema shapes `StaffLogin`/`StaffAuthResponse` in the new `backend/app/schemas/security.py` mirror. Note `NonEmptyStr` import from `app.schemas.customer` (line 16) — reuse it, don't redefine it.
11. `backend/app/main.py` (read in full, 83 lines) — `include_router` block (32-56) and the router import list (5-18) to extend with the new `auth` router. No new exception handler needed: this story raises only `Forbidden` (login failure) and `NotFound` (bad agent/role id in an admin action), both already centrally mapped (`main.py:71-72`).
12. `backend/alembic/versions/0009_ai_chatbot.py:26-27` — confirms `revision = '0009'` is head; the new migration sets `down_revision = '0009'`.
13. `backend/alembic/versions/0001_customer_management.py` (read in full) — the `op.create_table`/`op.add_column`/`op.create_foreign_key`/`downgrade()` idiom this migration follows; note it has **no named Postgres enum** to drop in `downgrade()` (unlike `0001`), since `roles.name` is a plain unique string, not an enum.
14. `backend/tests/conftest.py` (read in full, 239 lines) — `agent`/`inactive_agent`/`other_agent` fixtures (121-151) and `agent_client`/`other_agent_client` (154-169) are rewritten in this story (see Backend Tasks §7); `portal_auth`/`portal_client` (183-208) are the bearer-token-fixture template to mirror. **Every other existing test file that uses `agent_client`/`other_agent_client` needs zero changes** — that is the entire point of keeping these fixtures' external shape (a `TestClient` that successfully authenticates as a given agent dict) identical.
15. `frontend/src/api/portalAuth.ts` (read in full, 85 lines) — the exact external-store shape (`TOKEN_KEY`/`USER_KEY` in `localStorage`, `getX`/`setXSession`/`clearXSession`/`subscribeXToken`/`xAuthHeaders`) the new `frontend/src/api/staffAuth.ts` mirrors, substituting `staffToken`/`staffUser` for `portalToken`/`portalUser` and `Agent` for `PortalUser`.
16. `frontend/src/api/agentContext.ts` (read in full, 69 lines) — the placeholder module being retired. Confirmed via grep to have exactly three non-test importers: `frontend/src/api/client.ts:3`, `frontend/src/pages/DashboardPage.tsx:5`, plus its own test file — all three are updated in this story, then the file is deleted.
17. `frontend/src/api/client.ts` (read in full, 80 lines) — `request()` (35-56) imports `agentHeaders`/`clearAgentId` (line 3) and calls them at lines 39 and 51; both calls switch to `staffAuthHeaders`/`clearStaffSession`.
18. `frontend/src/PortalApp.tsx` (read in full, 93 lines) — `usePortalToken()` (60-62) and `PortalProtectedRoute()` (64-68) are the exact `useSyncExternalStore` + layout-route-guard pattern the new `StaffProtectedRoute` in `App.tsx` copies.
19. `frontend/src/pages/portal/PortalLoginPage.tsx` (read in full, 76 lines) — the form shape `LoginPage.tsx` mirrors (email/password controlled inputs, `ErrorBanner`, `navigate()` on success).
20. `frontend/src/App.tsx` (read in full, 99 lines) — `NAV` (19-25), `Nav()` (27-63, already special-cases `/portal` at line 31), and the `<Routes>` block (69-95) to restructure behind a `StaffProtectedRoute` layout route.
21. `frontend/src/pages/DashboardPage.tsx:1-99` — `useAgentId()` (19-21) and `AgentPicker()` (56-99), both removed; `agentId` is read again in the component body below line 115 (not pasted here) — grep for every remaining use of `agentId`/`getAgentId`/`setAgentId`/`subscribeAgentId` in this file before deleting the import, and replace the "no agent chosen" branch with nothing (the route is never reached unauthenticated once `StaffProtectedRoute` wraps it).
22. `frontend/src/pages/TicketSetupPage.tsx` (read in full, 255 lines) — the agents `<table>` (193-252) and its `createAgent`/`updateAgent`/`deactivateAgent` calls (imported from `frontend/src/api/tickets.ts`) are extended, not replaced, with a role column and a "Set password" action.

Grep before editing:
- `` grep -rn "X-Agent-Id" backend/ frontend/src `` — every remaining reference must be either removed or (for historical/comment purposes only) clearly marked as describing the old, now-replaced mechanism.
- `` grep -rn "agentContext" frontend/src `` — confirms the three importers in item 16 before deleting the file.
- `` grep -n "AGENT_HEADER" backend/app `` — confirms nothing outside `deps.py` referenced the header constant directly.

---

## Backend Tasks

### 1 — Migration

**Create file:** `backend/alembic/versions/0010_staff_authentication.py`

```python
"""staff authentication, users and roles

Adds real, credential-based staff authentication on top of the existing
``agents`` table (Story 03), replacing the ``X-Agent-Id`` trusted-header
placeholder documented in ``backend/app/api/deps.py``. Extends ``agents`` in
place rather than introducing a separate ``users`` table, so
``tickets.assignee_id`` and every other existing FK to ``agents.id`` needs no
migration at all.

Seeds one real admin account (email ``admin@crm.local``) so the very first
login after this migration is always possible -- see this story's own Edge
Cases for why its password must be rotated immediately after first deploy.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-02

"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

import bcrypt
from alembic import op
import sqlalchemy as sa


revision: str = '0010'
down_revision: Union[str, None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Fixed ids so this migration and the test suite agree on them, mirroring
# the hard-coded-row-id seeding precedent used for `channels` (Story 04).
ROLE_ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
ROLE_MANAGER_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
ROLE_AGENT_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")

# Seeded so the first login after this migration is always possible --
# ROTATE IMMEDIATELY. This is a bootstrap credential, not a production
# secret; see this story's Edge Cases & Failure Modes.
DEFAULT_ADMIN_EMAIL = "admin@crm.local"
DEFAULT_ADMIN_PASSWORD = "ChangeMe123!"


def upgrade() -> None:
    op.create_table(
        'roles',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=60), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_roles_name'),
    )

    op.add_column('agents', sa.Column('password_hash', sa.String(length=255), nullable=True))
    op.add_column('agents', sa.Column('role_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(
        'fk_agents_role_id_roles', 'agents', 'roles', ['role_id'], ['id'], ondelete='SET NULL'
    )
    op.create_index(op.f('ix_agents_role_id'), 'agents', ['role_id'], unique=False)

    op.create_table(
        'agent_sessions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('agent_id', sa.Uuid(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_agent_sessions_agent_id'), 'agent_sessions', ['agent_id'], unique=False)
    op.create_index(op.f('ix_agent_sessions_token_hash'), 'agent_sessions', ['token_hash'], unique=True)
    op.create_index(op.f('ix_agent_sessions_expires_at'), 'agent_sessions', ['expires_at'], unique=False)

    roles = sa.table(
        'roles',
        sa.column('id', sa.Uuid()),
        sa.column('name', sa.String()),
        sa.column('description', sa.Text()),
    )
    op.bulk_insert(
        roles,
        [
            {
                'id': ROLE_ADMIN_ID,
                'name': 'admin',
                'description': 'Full access, including user, role, audit-log and system-configuration management.',
            },
            {
                'id': ROLE_MANAGER_ID,
                'name': 'manager',
                'description': 'Reporting and read-only oversight; no user, role or system-configuration management.',
            },
            {
                'id': ROLE_AGENT_ID,
                'name': 'agent',
                'description': 'Day-to-day ticket and customer work; the default role for a new staff account.',
            },
        ],
    )

    agents = sa.table(
        'agents',
        sa.column('id', sa.Uuid()),
        sa.column('display_name', sa.String()),
        sa.column('email', sa.String()),
        sa.column('is_active', sa.Boolean()),
        sa.column('password_hash', sa.String()),
        sa.column('role_id', sa.Uuid()),
    )
    op.bulk_insert(
        agents,
        [
            {
                'id': uuid.uuid4(),
                'display_name': 'Administrator',
                'email': DEFAULT_ADMIN_EMAIL,
                'is_active': True,
                'password_hash': bcrypt.hashpw(
                    DEFAULT_ADMIN_PASSWORD.encode(), bcrypt.gensalt()
                ).decode(),
                'role_id': ROLE_ADMIN_ID,
            }
        ],
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM agents WHERE email = :email").bindparams(email=DEFAULT_ADMIN_EMAIL))

    op.drop_index(op.f('ix_agent_sessions_expires_at'), table_name='agent_sessions')
    op.drop_index(op.f('ix_agent_sessions_token_hash'), table_name='agent_sessions')
    op.drop_index(op.f('ix_agent_sessions_agent_id'), table_name='agent_sessions')
    op.drop_table('agent_sessions')

    op.drop_index(op.f('ix_agents_role_id'), table_name='agents')
    op.drop_constraint('fk_agents_role_id_roles', 'agents', type_='foreignkey')
    op.drop_column('agents', 'role_id')
    op.drop_column('agents', 'password_hash')

    op.drop_table('roles')
    # No named Postgres enum introduced by this migration -- `roles.name` is
    # a plain unique string, not an Enum, so there is nothing to drop the way
    # `0001_customer_management.py`'s downgrade() does for its three enums.
```

### 2 — Settings

**File:** `backend/app/core/config.py` — insert after `portal_session_ttl_days: int = 14` (line 15):

```python
    agent_session_ttl_days: int = 14
```

### 3 — Models

**File:** `backend/app/models/ticket.py` — extend `Agent` (lines 66-77):

```python
class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = _pk()
    display_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    is_active: Mapped[bool] = mapped_column(
        nullable=False, default=True, server_default=text("true")
    )
    # Staff authentication (Story 15). Nullable: an agent created only for
    # ticket assignment has no password and cannot log in until an admin
    # calls POST /agents/{id}/set-password.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    role_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("roles.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    role: Mapped["Role | None"] = relationship(back_populates="agents")
```

Add `if TYPE_CHECKING: from app.models.security import Role` near the top of `ticket.py` (alongside its existing imports) — a string-annotated forward reference, so no runtime circular import with the new `app/models/security.py` (which itself only imports `Agent` under `TYPE_CHECKING`).

**Create file:** `backend/app/models/security.py`

```python
"""Staff authentication and role-based access control.

`Role` and `AgentSession` extend the identity already established by `Agent`
(`app.models.ticket`) rather than replacing it -- see this story's own
Prerequisites: `tickets.assignee_id` and every other existing FK to
`agents.id` needs no migration at all this way.

`AgentSession` is a structural mirror of `PortalSession`
(`app.models.portal`): the raw bearer token is never stored, only the
SHA-256 hex digest of it (`app.api.deps.hash_token`), and a session is
soft-revoked (`revoked_at`), never deleted, so session lifetime stays
auditable.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.customer import _pk

if TYPE_CHECKING:
    from app.models.ticket import Agent


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    agents: Mapped[list["Agent"]] = relationship(back_populates="role")


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id: Mapped[uuid.UUID] = _pk()
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    agent: Mapped["Agent"] = relationship()
```

**File:** `backend/app/models/__init__.py` — add `from app.models.security import AgentSession, Role` to the import block and `"AgentSession"`, `"Role"` to `__all__` (alphabetical, matching the existing ordering).

### 4 — `deps.py`: replace the header-trust mechanism

**File:** `backend/app/api/deps.py` — full replacement:

```python
"""Shared FastAPI dependencies.

Real, credential-based staff authentication (Story 15). `get_current_agent`
verifies a bearer token against `agent_sessions`, replacing the
`X-Agent-Id` trusted-header placeholder this module previously documented.
Mirrors `app.api.deps_portal`'s exact shape -- same hash-and-compare
mechanism, same one-branch-for-every-failure design -- so a real credential
model now exists on both the staff and portal sides.

Kept out of `app.services` on purpose: the service layer stays FastAPI-free
and takes an `agent_id` argument instead.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.security import AgentSession
from app.models.ticket import Agent

bearer_scheme = HTTPBearer(auto_error=False)

_UNAUTHORISED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="a valid staff session token is required",
)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _lookup(db: Session, credentials: HTTPAuthorizationCredentials | None) -> Agent | None:
    """Resolve a bearer token to an active agent, or None."""
    if credentials is None or not credentials.credentials.strip():
        return None
    token_hash = hash_token(credentials.credentials.strip())
    session = db.scalars(
        select(AgentSession).where(
            AgentSession.token_hash == token_hash,
            AgentSession.revoked_at.is_(None),
            AgentSession.expires_at > datetime.now(timezone.utc),
        )
    ).first()
    if session is None:
        return None
    agent = db.get(Agent, session.agent_id)
    if agent is None or not agent.is_active:
        return None
    return agent


def get_current_agent(
    db: Annotated[Session, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> Agent:
    """The agent making this request, or 401.

    A missing token, an unknown/expired/revoked one, and a deactivated agent
    are all the same answer -- 401 -- so the frontend has one branch to
    handle: clear the stored session and send the caller back to /login.
    """
    agent = _lookup(db, credentials)
    if agent is None:
        raise _UNAUTHORISED
    return agent


def get_optional_agent(
    db: Annotated[Session, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> Agent | None:
    """The agent making this request, or None -- never raises.

    For pre-existing routes that must keep working unauthenticated (replying
    on a ticket, changing its status) but can attribute the activity-feed
    entry to a real agent when the caller does present a valid session.
    """
    return _lookup(db, credentials)


def require_agent_id(
    agent: Annotated[Agent, Depends(get_current_agent)],
) -> uuid.UUID:
    """Just the id, for handlers that never touch the rest of the row."""
    return agent.id


CurrentAgent = Annotated[Agent, Depends(get_current_agent)]
OptionalAgent = Annotated[Agent | None, Depends(get_optional_agent)]
CurrentAgentId = Annotated[uuid.UUID, Depends(require_agent_id)]
```

Every existing importer of `CurrentAgent`/`OptionalAgent`/`CurrentAgentId`/`get_current_agent`/`get_optional_agent` (dashboard.py, tasks.py, quick_replies.py, ai.py, reports.py, channels.py) needs **no changes** — same names, same shapes.

### 5 — Schemas

**Create file:** `backend/app/schemas/security.py`

```python
"""Pydantic v2 schemas for staff authentication, users and roles."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.customer import NonEmptyStr
from app.schemas.ticket import AgentRead


def _validate_email(value: str) -> str:
    value = value.strip()
    if "@" not in value or value.startswith("@") or value.endswith("@"):
        raise ValueError("not a valid email address")
    return value.lower()


class RoleCreate(BaseModel):
    name: NonEmptyStr = Field(max_length=60)
    description: str | None = None


class RoleUpdate(BaseModel):
    name: NonEmptyStr | None = Field(default=None, max_length=60)
    description: str | None = None


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime


class StaffLogin(BaseModel):
    email: NonEmptyStr
    password: NonEmptyStr

    _normalize_email = field_validator("email")(_validate_email)


class StaffAuthResponse(BaseModel):
    token: str
    expires_at: datetime
    agent: AgentRead


class SetPasswordRequest(BaseModel):
    password: str = Field(min_length=8)


class AssignRoleRequest(BaseModel):
    role_id: uuid.UUID | None
```

**File:** `backend/app/schemas/ticket.py` — extend `AgentUpdate` (lines 44-47) and `AgentRead` (50-54):

```python
class AgentUpdate(BaseModel):
    display_name: NonEmptyStr | None = None
    email: str | None = None
    is_active: bool | None = None
    role_id: uuid.UUID | None = None


class AgentRead(AgentBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role_id: uuid.UUID | None
    created_at: datetime
```

`AgentCreate` is unchanged — creating an agent still needs no password; login access is a separate, explicit step (`set-password`).

### 6 — Service layer

**Create file:** `backend/app/services/agent_auth.py`

```python
"""Staff authentication and role-management service layer.

Pure functions over a SQLAlchemy Session -- no FastAPI imports, same shape
as `app.services.portal`. Session creation/verification mirrors
`app.services.portal._create_session` exactly, but keyed to `agent_sessions`
and `app.api.deps.hash_token` instead of the portal equivalents.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import hash_token
from app.core.config import settings
from app.models.security import AgentSession, Role
from app.models.ticket import Agent
from app.services.errors import Conflict, Forbidden, NotFound

_NO_MATCH = Forbidden("invalid email or password")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _create_session(db: Session, agent: Agent) -> tuple[str, datetime]:
    raw = secrets.token_urlsafe(32)
    expires_at = _now() + timedelta(days=settings.agent_session_ttl_days)
    session = AgentSession(agent_id=agent.id, token_hash=hash_token(raw), expires_at=expires_at)
    db.add(session)
    db.flush()
    return raw, expires_at


def login(db: Session, email: str, password: str) -> tuple[Agent, str, datetime]:
    agent = db.scalars(select(Agent).where(func.lower(Agent.email) == email.lower())).first()
    if (
        agent is None
        or not agent.is_active
        or agent.password_hash is None
        or not bcrypt.checkpw(password.encode(), agent.password_hash.encode())
    ):
        # One branch, mirroring get_current_agent's design and
        # app.services.portal.login's own precedent: unknown email, wrong
        # password, a deactivated account, and an account with no password
        # set yet all read the same to the caller.
        raise _NO_MATCH
    raw, expires_at = _create_session(db, agent)
    return agent, raw, expires_at


def logout(db: Session, agent_id: uuid.UUID, raw_token: str) -> None:
    """Idempotent: revoking an already-revoked or unknown token is a no-op."""
    token_hash = hash_token(raw_token)
    session = db.scalars(
        select(AgentSession).where(
            AgentSession.agent_id == agent_id,
            AgentSession.token_hash == token_hash,
            AgentSession.revoked_at.is_(None),
        )
    ).first()
    if session is None:
        return
    session.revoked_at = _now()
    db.flush()


def set_password(db: Session, agent_id: uuid.UUID, new_password: str) -> Agent:
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise NotFound(f"agent {agent_id} not found")
    agent.password_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    db.flush()
    db.refresh(agent)
    return agent


def list_roles(db: Session) -> list[Role]:
    return list(db.scalars(select(Role).order_by(Role.name)))


def create_role(db: Session, *, name: str, description: str | None) -> Role:
    existing = db.scalars(select(Role).where(func.lower(Role.name) == name.lower())).first()
    if existing is not None:
        raise Conflict(f"a role named {name!r} already exists")
    role = Role(name=name, description=description)
    db.add(role)
    db.flush()
    db.refresh(role)
    return role


def update_role(db: Session, role_id: uuid.UUID, *, name: str | None, description: str | None) -> Role:
    role = db.get(Role, role_id)
    if role is None:
        raise NotFound(f"role {role_id} not found")
    if name is not None:
        role.name = name
    if description is not None:
        role.description = description
    db.flush()
    db.refresh(role)
    return role


def assign_role(db: Session, agent_id: uuid.UUID, role_id: uuid.UUID | None) -> Agent:
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise NotFound(f"agent {agent_id} not found")
    if role_id is not None and db.get(Role, role_id) is None:
        raise NotFound(f"role {role_id} not found")
    agent.role_id = role_id
    db.flush()
    db.refresh(agent)
    return agent
```

### 7 — Routes

**Create file:** `backend/app/api/routes/auth.py`

```python
"""Staff authentication and role-management HTTP routes.

Distinct from `/portal/auth/*` (`app.api.routes.portal`): this is the staff
side, backed by `agent_sessions` rather than `portal_sessions`. Login is
open (nobody is authenticated yet when calling it); every other route here
requires a valid session via `CurrentAgent`, taken as an explicit parameter
rather than a router-level dependency so `login` alone can stay unauthenticated.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.api.deps import CurrentAgent, bearer_scheme
from app.db.session import get_db
from app.schemas.security import (
    AssignRoleRequest,
    RoleCreate,
    RoleRead,
    RoleUpdate,
    SetPasswordRequest,
    StaffAuthResponse,
    StaffLogin,
)
from app.schemas.ticket import AgentRead
from app.services import agent_auth as svc

router = APIRouter(tags=["auth"])

DbDep = Annotated[Session, Depends(get_db)]


@router.post("/auth/login", response_model=StaffAuthResponse)
def login(payload: StaffLogin, db: DbDep) -> StaffAuthResponse:
    agent, token, expires_at = svc.login(db, payload.email, payload.password)
    return StaffAuthResponse(token=token, expires_at=expires_at, agent=AgentRead.model_validate(agent))


@router.post("/auth/logout", status_code=204)
def logout(
    db: DbDep,
    agent: CurrentAgent,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> None:
    svc.logout(db, agent.id, credentials.credentials)


@router.post("/agents/{agent_id}/set-password", response_model=AgentRead)
def set_password(agent_id: uuid.UUID, payload: SetPasswordRequest, db: DbDep, _: CurrentAgent) -> AgentRead:
    return AgentRead.model_validate(svc.set_password(db, agent_id, payload.password))


@router.get("/roles", response_model=list[RoleRead])
def list_roles(db: DbDep, _: CurrentAgent) -> list[RoleRead]:
    return [RoleRead.model_validate(r) for r in svc.list_roles(db)]


@router.post("/roles", response_model=RoleRead, status_code=201)
def create_role(payload: RoleCreate, db: DbDep, _: CurrentAgent) -> RoleRead:
    return RoleRead.model_validate(svc.create_role(db, name=payload.name, description=payload.description))


@router.patch("/roles/{role_id}", response_model=RoleRead)
def update_role(role_id: uuid.UUID, payload: RoleUpdate, db: DbDep, _: CurrentAgent) -> RoleRead:
    return RoleRead.model_validate(
        svc.update_role(db, role_id, name=payload.name, description=payload.description)
    )


@router.patch("/agents/{agent_id}/role", response_model=AgentRead)
def assign_role(agent_id: uuid.UUID, payload: AssignRoleRequest, db: DbDep, _: CurrentAgent) -> AgentRead:
    return AgentRead.model_validate(svc.assign_role(db, agent_id, payload.role_id))
```

### 8 — Wiring

**File:** `backend/app/main.py`

- Add `auth` to the `from app.api.routes import (...)` block, alphabetically first: `ai, auth, channels, customers, dashboard, health, knowledge_base, portal, portal_chat, portal_kb, quick_replies, reports, tasks, tickets`.
- Add `app.include_router(auth.router, prefix=settings.api_prefix)` next to the other routers (position does not matter — nothing else depends on router registration order).
- No new exception handler: `Forbidden` (login failure) and `NotFound` (bad id) are already mapped at lines 71-72.

### 9 — Test fixtures

**File:** `backend/tests/conftest.py` — this is the seam that keeps every other test file unchanged. Add:

```python
@pytest.fixture()
def admin_client(app: FastAPI, client: TestClient) -> Iterator[TestClient]:
    """A client authenticated as the seeded default admin account (migration 0010)."""
    res = client.post("/api/auth/login", json={"email": "admin@crm.local", "password": "ChangeMe123!"})
    assert res.status_code == 200, res.text
    token = res.json()["token"]
    with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as test_client:
        yield test_client
```

Rewrite `agent`/`other_agent` (lines 121-128, 144-151) to give the new agent a real password via `admin_client`, and `agent_client`/`other_agent_client` (154-169) to log in as that agent rather than sending `X-Agent-Id`:

```python
@pytest.fixture()
def agent(client: TestClient, admin_client: TestClient) -> dict:
    """One active agent with a login password set."""
    res = client.post("/api/agents", json={"display_name": "Dana Support", "email": "dana@crm.test"})
    assert res.status_code == 201, res.text
    created = res.json()
    set_res = admin_client.post(f"/api/agents/{created['id']}/set-password", json={"password": "hunter2pass"})
    assert set_res.status_code == 200, set_res.text
    return created


@pytest.fixture()
def other_agent(client: TestClient, admin_client: TestClient) -> dict:
    """A second active agent, for "not yours" and mention assertions."""
    res = client.post("/api/agents", json={"display_name": "Omar Night", "email": "omar@crm.test"})
    assert res.status_code == 201, res.text
    created = res.json()
    set_res = admin_client.post(f"/api/agents/{created['id']}/set-password", json={"password": "hunter2pass"})
    assert set_res.status_code == 200, set_res.text
    return created


@pytest.fixture()
def agent_client(app: FastAPI, agent: dict) -> Iterator[TestClient]:
    """A client authenticated as `agent`, via a real login session."""
    with TestClient(app) as bootstrap:
        res = bootstrap.post("/api/auth/login", json={"email": agent["email"], "password": "hunter2pass"})
        assert res.status_code == 200, res.text
        token = res.json()["token"]
    with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as test_client:
        yield test_client


@pytest.fixture()
def other_agent_client(app: FastAPI, other_agent: dict) -> Iterator[TestClient]:
    """A client authenticated as `other_agent`."""
    with TestClient(app) as bootstrap:
        res = bootstrap.post("/api/auth/login", json={"email": other_agent["email"], "password": "hunter2pass"})
        assert res.status_code == 200, res.text
        token = res.json()["token"]
    with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as test_client:
        yield test_client
```

`inactive_agent` (131-141) is unchanged — it is deactivated before ever needing to log in. **No other test file changes** — every test built on `agent`/`other_agent`/`agent_client`/`other_agent_client` (dashboard, tasks, quick_replies, ai, reports, and more) keeps working because these fixtures' external shape (a dict with `id`/`email`/etc., and a `TestClient` that successfully authenticates as that agent) is unchanged.

---

## Frontend Tasks

### 10 — Staff session store

**Create file:** `frontend/src/api/staffAuth.ts` — full mirror of `frontend/src/api/portalAuth.ts`, substituting `staffToken`/`staffUser` for the storage keys and `Agent` (from `../types/ticket`) for `PortalUser`:

```ts
/**
 * Staff identity.
 *
 * Mirrors `portalAuth.ts`'s storage/listener shape: a real bearer token,
 * returned by `POST /api/auth/login`, stored in `localStorage` under its own
 * key, and sent as `Authorization: Bearer <token>` by `client.ts`. Replaces
 * `agentContext.ts`'s trusted, unverified `X-Agent-Id` placeholder.
 */

import type { Agent } from "../types/ticket";

const TOKEN_KEY = "staffToken";
const USER_KEY = "staffUser";

const listeners = new Set<() => void>();

let currentToken: string | null = readToken();
let currentUser: Agent | null = readUser();

function readToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function readUser(): Agent | null {
  try {
    const raw = window.localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as Agent) : null;
  } catch {
    return null;
  }
}

function emit(): void {
  for (const listener of listeners) listener();
}

export function getStaffToken(): string | null {
  return currentToken;
}

export function getStaffUser(): Agent | null {
  return currentUser;
}

export function setStaffSession(token: string, user: Agent): void {
  currentToken = token;
  currentUser = user;
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
    window.localStorage.setItem(USER_KEY, JSON.stringify(user));
  } catch {
    // Not persisted across reloads, but usable for this session.
  }
  emit();
}

export function clearStaffSession(): void {
  currentToken = null;
  currentUser = null;
  try {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(USER_KEY);
  } catch {
    // Nothing to clean up.
  }
  emit();
}

export function subscribeStaffToken(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function staffAuthHeaders(): Record<string, string> {
  return currentToken ? { Authorization: `Bearer ${currentToken}` } : {};
}
```

**Delete file:** `frontend/src/api/agentContext.ts` (and its test file) once `client.ts` and `DashboardPage.tsx` no longer import it.

### 11 — API client

**Create file:** `frontend/src/api/auth.ts`

```ts
import { request } from "./client";
import type { Agent } from "../types/ticket";

export interface StaffAuthResponse {
  token: string;
  expires_at: string;
  agent: Agent;
}

export function login(payload: { email: string; password: string }): Promise<StaffAuthResponse> {
  return request<StaffAuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function logout(): Promise<void> {
  return request<void>("/auth/logout", { method: "POST" });
}

export function setAgentPassword(agentId: string, password: string): Promise<Agent> {
  return request<Agent>(`/agents/${agentId}/set-password`, {
    method: "POST",
    body: JSON.stringify({ password }),
  });
}
```

**File:** `frontend/src/api/client.ts` — line 3 becomes `import { clearStaffSession, staffAuthHeaders } from "./staffAuth";`; line 39 becomes `const identity = staffAuthHeaders();`; line 51 becomes `clearStaffSession();`.

### 12 — Login page and route guard

**Create file:** `frontend/src/pages/LoginPage.tsx` (mirrors `frontend/src/pages/portal/PortalLoginPage.tsx`):

```tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { login } from "../api/auth";
import { setStaffSession } from "../api/staffAuth";
import { ErrorBanner, styles } from "../components/ui";

export default function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const { token, agent } = await login({ email, password });
      setStaffSession(token, agent);
      navigate("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <main style={styles.page}>
      <h1 style={styles.h1}>Staff log in</h1>
      <ErrorBanner message={error} />
      <form onSubmit={handleSubmit} style={{ maxWidth: 400 }}>
        <div style={{ marginBottom: "1rem" }}>
          <label htmlFor="email" style={styles.label}>Email</label>
          <input
            id="email"
            type="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            style={{ ...styles.input, width: "100%" }}
          />
        </div>
        <div style={{ marginBottom: "1rem" }}>
          <label htmlFor="password" style={styles.label}>Password</label>
          <input
            id="password"
            type="password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            style={{ ...styles.input, width: "100%" }}
          />
        </div>
        <button type="submit" style={styles.button} disabled={saving}>
          {saving ? "Logging in…" : "Log in"}
        </button>
      </form>
    </main>
  );
}
```

**File:** `frontend/src/App.tsx` — restructure to guard every existing staff route behind a login check, following `PortalApp.tsx`'s `PortalProtectedRoute` pattern exactly:

```tsx
import { useSyncExternalStore } from "react";
import { Link, Navigate, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";

import { logout as apiLogout } from "./api/auth";
import { clearStaffSession, getStaffToken, getStaffUser, subscribeStaffToken } from "./api/staffAuth";
import CustomerDetailPage from "./pages/CustomerDetailPage";
import CustomerEditPage from "./pages/CustomerEditPage";
import CustomersListPage from "./pages/CustomersListPage";
import DashboardPage from "./pages/DashboardPage";
import HealthPage from "./pages/HealthPage";
import KnowledgeBaseEditPage from "./pages/KnowledgeBaseEditPage";
import KnowledgeBaseListPage from "./pages/KnowledgeBaseListPage";
import LoginPage from "./pages/LoginPage";
import TicketDetailPage from "./pages/TicketDetailPage";
import TicketEditPage from "./pages/TicketEditPage";
import TicketSetupPage from "./pages/TicketSetupPage";
import TicketsListPage from "./pages/TicketsListPage";
import PortalApp from "./PortalApp";
import { tokens, styles } from "./components/ui";

const NAV = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/customers", label: "Customers" },
  { to: "/tickets", label: "Tickets" },
  { to: "/kb", label: "Knowledge Base" },
  { to: "/health", label: "Health" },
];

function useStaffToken(): string | null {
  return useSyncExternalStore(subscribeStaffToken, getStaffToken, () => null);
}

function StaffProtectedRoute() {
  const token = useStaffToken();
  if (!token) return <Navigate to="/login" replace />;
  return <Outlet />;
}

function Nav() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const token = useStaffToken();
  if (pathname.startsWith("/portal") || pathname === "/login") return null;

  async function handleLogout() {
    try {
      await apiLogout();
    } catch {
      // Best-effort -- clear the local session regardless.
    }
    clearStaffSession();
    navigate("/login");
  }

  return (
    <nav style={{ fontFamily: tokens.font, borderBottom: `1px solid ${tokens.border}`, padding: "0.75rem 1rem", display: "flex", gap: "1rem", alignItems: "center", justifyContent: "space-between" }}>
      <span style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
        <strong style={{ marginRight: "0.5rem" }}>CRM</strong>
        {NAV.map((item) => {
          const active = pathname.startsWith(item.to);
          return (
            <Link key={item.to} to={item.to} aria-current={active ? "page" : undefined} style={{ textDecoration: "none", color: active ? tokens.accent : tokens.muted, fontWeight: active ? 600 : 400 }}>
              {item.label}
            </Link>
          );
        })}
      </span>
      {token && (
        <span style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
          <span style={{ color: tokens.muted }}>{getStaffUser()?.display_name}</span>
          <button type="button" style={styles.button} onClick={() => void handleLogout()}>Log out</button>
        </span>
      )}
    </nav>
  );
}

export default function App() {
  return (
    <>
      <Nav />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/portal/*" element={<PortalApp />} />
        <Route element={<StaffProtectedRoute />}>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/health" element={<HealthPage />} />
          <Route path="/customers" element={<CustomersListPage />} />
          <Route path="/customers/new" element={<CustomerEditPage />} />
          <Route path="/customers/:id" element={<CustomerDetailPage />} />
          <Route path="/customers/:id/edit" element={<CustomerEditPage />} />
          <Route path="/tickets" element={<TicketsListPage />} />
          <Route path="/tickets/new" element={<TicketEditPage />} />
          <Route path="/tickets/setup" element={<TicketSetupPage />} />
          <Route path="/tickets/:id" element={<TicketDetailPage />} />
          <Route path="/tickets/:id/edit" element={<TicketEditPage />} />
          <Route path="/kb" element={<KnowledgeBaseListPage />} />
          <Route path="/kb/new" element={<KnowledgeBaseEditPage />} />
          <Route path="/kb/:id" element={<KnowledgeBaseEditPage />} />
        </Route>
        <Route path="*" element={<main style={{ fontFamily: tokens.font, padding: "2rem" }}><h1>Not found</h1><Link to="/">Go home</Link></main>} />
      </Routes>
    </>
  );
}
```

### 13 — `DashboardPage.tsx` cleanup

**File:** `frontend/src/pages/DashboardPage.tsx` — remove the `agentContext` import (line 5), `useAgentId()` (19-21), and the entire `AgentPicker()` component (56-99) along with whatever branch in `DashboardPage()`'s render currently returns `<AgentPicker />` when `agentId` is null (below line 115 — grep `agentId` in this file to find every remaining reference before deleting). The component may now assume it only ever mounts with a valid session, since `StaffProtectedRoute` redirects to `/login` first. The `agents` state (fetched via `listAgents` from `api/tickets.ts`, used to turn ids into display names in the activity feed) is unrelated to identity and stays.

### 14 — `TicketSetupPage.tsx`: role assignment and password

**File:** `frontend/src/pages/TicketSetupPage.tsx` — extend the agents table (193-252): add a "Role" `<th>`/`<td>` per row (a `<select>` bound to `agent.role_id`, calling a new `assignAgentRole(agentId, roleId)` helper in `frontend/src/api/tickets.ts` that `PATCH`es `/agents/{id}/role`), populated from a new `listRoles()` call (`GET /roles`) fetched alongside `categories`/`agents` in the existing `load()`. Add a "Set password" button per row opening a small inline form (email already known; one password input) that calls `setAgentPassword` (`frontend/src/api/auth.ts`, §11).

### 15 — Types

**File:** `frontend/src/types/ticket.ts` — extend the `Agent` interface with `role_id: string | null`. **Create file:** `frontend/src/types/security.ts` — `Role` interface mirroring `RoleRead` (`id`, `name`, `description`, `created_at`).

---

## Edge Cases & Failure Modes

- **The seeded default admin credential (`admin@crm.local` / `ChangeMe123!`) is a bootstrap secret, not a production one.** It is created by the migration itself (Backend Tasks §1) so the very first login is always possible on a fresh database. **It must be rotated (via `set_password`, once logged in) immediately after the first real deploy** — this is a manual operational step, not something this story automates (there is no CLI or admin-onboarding-wizard story yet). Document this prominently in the migration's own docstring and in this section, since it is the single most important thing an executor or operator must not skip.
- **An agent with no `password_hash` tries to log in.** `login()` (`app/services/agent_auth.py`) treats `password_hash is None` identically to "wrong password" — one `Forbidden` message, never a distinct "this account has no password yet" hint (would leak which emails exist).
- **A deactivated agent's existing session.** `_lookup()` in `deps.py` re-checks `agent.is_active` on every request (not just at login) — deactivating an agent immediately invalidates every live session of theirs on their next request, with no background job needed, matching `require_active_portal_customer`'s "computed on read" precedent (`deps_portal.py:75-89`).
- **A revoked or expired session token presented again.** Same 401 as a token that never existed — `_lookup()`'s `WHERE` clause excludes both `revoked_at IS NOT NULL` and `expires_at <= now()` rows identically.
- **Deleting a `Role` that agents are still assigned to.** `role_id` is `ON DELETE SET NULL` (`agents.role_id` FK) — those agents silently become role-less (equivalent to the `agent` default in Story 16's permission model, since role-less means "no permissions" there), never a foreign-key error. This story does not add a role-delete endpoint (only create/update) precisely to avoid needing to decide this now beyond the FK's own `SET NULL` behavior — a future story can add deletion once Story 16's permission-catalog implications are clear.
- **Creating a role with a name that only differs by case from an existing one** (e.g. `Admin` vs `admin`) — `create_role()` checks `func.lower(Role.name) == name.lower()` and raises `Conflict` (409), not a raw unique-constraint 500.
- **`agent_session_ttl_days` — no session-cleanup job.** Expired rows are never deleted, only excluded from `_lookup()`'s query, exactly matching `PortalSession`'s own documented precedent (`app/models/portal.py:88-90`) of favoring auditability over table size.
- **`GET /api/auth/login` versus `POST`** — only `POST` exists; the endpoint takes a request body (email+password), never query parameters, so credentials never appear in a URL or a server access log.
- **`OptionalAgent`-gated routes (`channels.py`'s `send_ticket_message`) with an invalid-but-present bearer token.** `get_optional_agent()` never raises — an invalid token is treated identically to no token at all (returns `None`), so the write still succeeds, just unattributed. This is unchanged behavior from before this story, only the underlying mechanism (bearer token vs. header) changed.
- **A test or script still sends `X-Agent-Id`.** It is now silently ignored — `get_current_agent`/`get_optional_agent` no longer read that header at all, so a caller relying on the old mechanism gets a 401 (for `CurrentAgent`) or is treated as anonymous (for `OptionalAgent`), never a confusing partial-auth state.

---

## Test Plan

Backend (`backend/tests/`):

1. **Create `backend/tests/test_staff_auth.py`**:
   - `test_login_succeeds_with_correct_credentials` — using `admin_client`'s bootstrap flow directly (`client.post("/api/auth/login", ...)` with the seeded admin), assert `200` and a response shaped like `StaffAuthResponse` (`token`, `expires_at`, `agent`).
   - `test_login_rejects_wrong_password`, `test_login_rejects_unknown_email`, `test_login_rejects_agent_with_no_password_set`, `test_login_rejects_deactivated_agent` — each asserts the same `403` (`Forbidden`) with the same generic message, never a distinguishing one.
   - `test_current_agent_requires_bearer_token` — hitting any `CurrentAgent`-gated route (e.g. `GET /api/dashboard/summary`) with `client` (no auth) returns `401`; with `agent_client` returns `200`.
   - `test_deactivating_agent_invalidates_live_session` — log in as `agent`, then `admin_client.delete(f"/api/agents/{agent['id']}")` (deactivate), then re-use the original token — asserts `401`.
   - `test_logout_revokes_session` — log in, call `/api/auth/logout`, re-use the same token — asserts `401`; calling `/api/auth/logout` a second time with the same (now-revoked) token is idempotent (no error raised server-side, though the route itself requires a still-valid token to reach the handler at all — assert this via a still-valid *second* session for the same agent, logging out one session does not affect the other).
   - `test_x_agent_id_header_no_longer_trusted` — a request with `X-Agent-Id: <real agent id>` and no `Authorization` header gets `401` on a `CurrentAgent`-gated route.
2. **Create `backend/tests/test_roles.py`** — `test_create_role`, `test_create_role_rejects_duplicate_name_case_insensitive`, `test_update_role`, `test_assign_role_to_agent`, `test_assign_role_rejects_unknown_role_id` (404), `test_deleting_role_sets_agent_role_id_null` (delete via direct `db` fixture manipulation + `db.commit()`, since no delete endpoint exists yet — or skip if Role deletion truly has no code path; assert via ORM-level `SET NULL` behavior using the `db` fixture directly).
3. **Create `backend/tests/test_set_password.py`** — `test_admin_sets_password_for_new_agent`, `test_agent_can_then_log_in_with_new_password`, `test_set_password_requires_authentication` (`client.post(...)` with no auth → `401`), `test_set_password_rejects_short_password` (422, `Field(min_length=8)`).
4. **Regression:** run the full existing suite unmodified except `conftest.py` — every file using `agent`/`other_agent`/`agent_client`/`other_agent_client` (dashboard, tasks, quick_replies, ai, reports tests) must still pass with zero changes to their own bodies.

Frontend (`frontend/src/`):

5. **Create `frontend/src/pages/__tests__/LoginPage.test.tsx`** — mocks `POST /auth/login`; asserts a successful submit calls `setStaffSession` and navigates to `/dashboard`; asserts a `403` response renders the error banner.
6. **Update `frontend/src/pages/__tests__/DashboardPage.test.tsx`** — remove any `AgentPicker`/`setAgentId`/`getAgentId` setup and replace with `setStaffSession`/`clearStaffSession` (mirroring `PortalTicketsPage.test.tsx`'s pattern for portal auth) in `beforeEach`/`afterEach`.
7. **Update `frontend/src/__tests__/navigation.test.tsx`** — add assertions that an unauthenticated visit to `/dashboard` (or any staff route) redirects to `/login`, and that `/login` never renders `<Nav>`.
8. **Delete `frontend/src/api/__tests__/agentContext.test.tsx`** (if it exists) once the module itself is deleted; its coverage is superseded by a new `frontend/src/api/__tests__/staffAuth.test.ts` mirroring whatever test (if any) exists for `portalAuth.ts`.

---

## Verification Steps

1. **Backend migrates:** `cd backend && uv run alembic upgrade head` — confirms `0010_staff_authentication` applies cleanly on top of `0009`.
2. **Backend tests:** `cd backend && uv run pytest -q` — full suite green, including the new `test_staff_auth.py`/`test_roles.py`/`test_set_password.py`.
3. **Backend serves and the bootstrap admin works:** `cd backend && uv run uvicorn app.main:app --reload`; `curl -X POST localhost:8000/api/auth/login -H "Content-Type: application/json" -d '{"email":"admin@crm.local","password":"ChangeMe123!"}'` returns a `200` with a token; the same request with `X-Agent-Id` instead of a bearer token on any protected route returns `401`.
4. **Frontend type-checks:** `cd frontend && npx tsc -b --noEmit`.
5. **Frontend tests:** `cd frontend && npm test`.
6. **Manual smoke:** `cd frontend && npm run dev` — visiting `/dashboard` while logged out redirects to `/login`; logging in as the seeded admin lands on the dashboard with a working "Log out" button; creating a new agent under Ticket Setup, setting its password, then logging in as that agent in a private window, works end to end.
7. **Regression:** re-run `pytest -q` and `npm test` in full — no existing test file outside `conftest.py` and the files listed in Test Plan items 6-8 should need any change.

---

## Done Criteria

- [ ] Migration `0010_staff_authentication.py` adds `roles`, `agent_sessions`, `agents.password_hash`/`agents.role_id`, and seeds three roles plus one bootstrap admin account.
- [ ] `backend/app/api/deps.py`'s `get_current_agent`/`get_optional_agent` verify a real bearer token against `agent_sessions`; the `X-Agent-Id` header is no longer read anywhere.
- [ ] `POST /api/auth/login`, `POST /api/auth/logout`, `POST /api/agents/{id}/set-password`, `GET/POST /api/roles`, `PATCH /api/roles/{id}`, `PATCH /api/agents/{id}/role` all exist and behave per this story's Backend Tasks.
- [ ] Every pre-existing agent-scoped route (dashboard, tasks, quick_replies, ai, reports) still works, now via real bearer-token auth, with zero changes to their own route/service code.
- [ ] `backend/tests/conftest.py`'s `agent`/`other_agent`/`agent_client`/`other_agent_client` fixtures are updated; **no other existing backend test file needs any change**.
- [ ] Frontend: `LoginPage`, `StaffProtectedRoute` in `App.tsx`, and `staffAuth.ts` replace `agentContext.ts`/`AgentPicker` entirely; `agentContext.ts` is deleted.
- [ ] `TicketSetupPage.tsx` can assign a role and set a password for an agent.
- [ ] No permission enforcement exists yet — that is Story 16.
- [ ] `pytest -q`, `npm test`, and `npx tsc -b --noEmit` are all green.

**STOP HERE. Report to the user and wait for confirmation before proceeding to Story 16.**
