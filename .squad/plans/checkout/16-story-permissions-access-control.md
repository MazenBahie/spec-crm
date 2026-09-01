# Story 16 — Permissions & Access Control

## Prerequisites

- [Story 15](15-story-staff-authentication-users-roles.md) completed: real, credential-based staff sessions (`Agent.password_hash`, `agent_sessions`, `backend/app/api/deps.py`'s bearer-token `get_current_agent`) and a `roles` table with three seeded rows (`admin`, `manager`, `agent` — fixed ids `ROLE_ADMIN_ID`/`ROLE_MANAGER_ID`/`ROLE_AGENT_ID` in `backend/alembic/versions/0010_staff_authentication.py`). Story 15 shipped **zero** enforcement: every authenticated agent, regardless of role, could call every endpoint including the new `/roles` and `/agents/{id}/set-password` routes. This story is what actually restricts them.
- The Alembic chain is linear: this story's migration sets `down_revision = '0010'`.
- **Explicit scope boundary, carried from Story 15's own planning discussion:** this story does **not** gate the pre-existing, still-open `customers.router`/`tickets.router`/`channels.router` (`backend/app/api/routes/customers.py`, `tickets.py`, `channels.py` — none declare any `Depends(get_current_agent)` today, confirmed by grep). Doing so would require most of `backend/tests/conftest.py`'s ~40-file-wide test suite to stop using the plain, unauthenticated `client` fixture (`conftest.py:97-100`) for its `customer`/`ticket`/`ticket_category` setup fixtures (`conftest.py:104-110`, `211-234`) — a distinct, mechanical migration out of proportion to what the "Permissions" intake bullet asks for. This story updates `.squad/plans/checkout/00-overview.md`'s "Known cross-story gap" section to record this as a deliberate, narrower remaining gap, not an oversight (see Backend Tasks §5).
- `backend/app/services/errors.py:18-25` — `Forbidden`'s docstring: *"agent-scoped entities... answer 'that is not yours' rather than pretending the row does not exist, because both agents are trusted staff."* Permission-denied responses in this story use `Forbidden` → 403, following this original, un-overridden reasoning (staff routes are not the portal's public-facing 404-obfuscation case documented separately at `00-overview.md:75`).

---

## Story Goal

Give the `roles` introduced by Story 15 actual teeth: a fixed catalog of named permissions, each role granted a subset of them, and a new `require_permission(...)` dependency that 403s a request when the current agent's role lacks the permission a route declares.

1. **Permission catalog** — a `permissions` table (`key`, `description`) and a `role_permissions` join table, seeded so `admin` has every permission, `manager` has the reporting/audit/config-viewing ones, and `agent` (the default role) has none of the admin-only ones.
2. **`require_permission(key)`** — a dependency factory in `backend/app/api/deps.py`, used exactly like `Depends(get_current_agent)` is today, but additionally checking the resolved agent's permissions.
3. **Apply it retroactively** to Story 15's own `/roles` and `/agents/{id}/set-password`/`/agents/{id}/role` endpoints (currently open to any authenticated agent) — the first real consumers of the new dependency.
4. **Expose "what can I do" to the frontend** — `GET /api/auth/me` returns the current agent plus their resolved permission-key set, so the UI can hide (not just have the server reject) admin-only controls for agents who lack them.
5. **Narrow, not close, the overview's "Known cross-story gap.`** Update `00-overview.md` to state plainly that staff identity is now real and permissioned, but `customers`/`tickets`/`channels` remain open by deliberate, documented choice.

**Out of scope (explicit):**
- Gating `customers.router`/`tickets.router`/`channels.router` — see Prerequisites.
- A UI for editing which permissions belong to which role (`role_permissions` is seed-only in this story; an admin can rename a role or reassign an agent's role via Story 15's existing endpoints, but cannot yet edit a role's permission set through the API — only by editing the seed/migration). A future story can add `PATCH /roles/{id}/permissions` once there is a concrete need.
- Any change to `Forbidden`'s existing 403 semantics or the portal's separate 404-obfuscation contract — both stay exactly as documented.

---

## Context — Read These Files First

1. [Story 15](15-story-staff-authentication-users-roles.md) — read in full, especially Backend Tasks §3 (`Role`/`Agent.role_id`) and §4 (`deps.py`'s current shape, without `require_permission`) and §7 (`auth.py`'s current routes, all gated only by `CurrentAgent`).
2. `backend/app/models/agent.py:239-262` — `ActivityMention`, the plain composite-PK join-table shape (`event_id`+`agent_id`) this story's `role_permissions` table copies (`role_id`+`permission_id`).
3. `backend/app/api/deps.py` (as left by Story 15) — `CurrentAgent`, `require_agent_id()` (the shape `require_permission()` is modeled on: a small dependency function that takes the already-resolved `Agent` and derives something from it).
4. `backend/app/services/errors.py:18-25` — `Forbidden`, mapped to 403 at `backend/app/main.py:71` (assuming Story 15 does not change this mapping).
5. `backend/app/models/customer.py:44-45` — `_pk()`.
6. `.squad/plans/checkout/00-overview.md` lines 82-90 ("Known cross-story gap") — the section this story rewrites (Backend Tasks §5).

Grep before editing:
- `` grep -rn "dependencies=\[Depends(get_current_agent)\]" backend/app/api/routes `` — every router this pattern currently appears on (`quick_replies.py`, `dashboard.py`, `tasks.py`, `reports.py` per `00-overview.md`) is a candidate for a future, per-route `require_permission` if a later story decides a specific action needs restricting beyond "any authenticated agent" — this story itself only touches the routes named in Story Goal item 3.
- `` grep -n "role_id" backend/app/models/ticket.py backend/app/schemas/ticket.py `` — confirms Story 15's exact field names before building on them.

---

## Backend Tasks

### 1 — Migration

**Create file:** `backend/alembic/versions/0011_permissions.py`, `down_revision = '0010'`.

```python
"""permissions and role-permission grants

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-02
"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0011'
down_revision: Union[str, None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLE_ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
ROLE_MANAGER_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
ROLE_AGENT_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")

# key -> description. Fixed catalog for this story; a future story may add a
# management UI for editing this set, see this story's Story Goal.
PERMISSIONS: dict[str, str] = {
    "manage_users": "Create/deactivate agents, assign roles, set passwords.",
    "manage_roles": "Create and edit roles.",
    "view_audit_log": "View the audit log.",
    "manage_system_config": "View and edit system configuration.",
}

# role name -> permission keys it is granted.
ROLE_GRANTS: dict[uuid.UUID, list[str]] = {
    ROLE_ADMIN_ID: list(PERMISSIONS),
    ROLE_MANAGER_ID: ["view_audit_log"],
    ROLE_AGENT_ID: [],
}


def upgrade() -> None:
    op.create_table(
        'permissions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('key', sa.String(length=60), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key', name='uq_permissions_key'),
    )
    op.create_table(
        'role_permissions',
        sa.Column('role_id', sa.Uuid(), nullable=False),
        sa.Column('permission_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('role_id', 'permission_id'),
    )

    permission_ids = {key: uuid.uuid4() for key in PERMISSIONS}
    permissions_table = sa.table(
        'permissions', sa.column('id', sa.Uuid()), sa.column('key', sa.String()), sa.column('description', sa.Text())
    )
    op.bulk_insert(
        permissions_table,
        [{'id': permission_ids[key], 'key': key, 'description': desc} for key, desc in PERMISSIONS.items()],
    )

    role_permissions_table = sa.table(
        'role_permissions', sa.column('role_id', sa.Uuid()), sa.column('permission_id', sa.Uuid())
    )
    grants = [
        {'role_id': role_id, 'permission_id': permission_ids[key]}
        for role_id, keys in ROLE_GRANTS.items()
        for key in keys
    ]
    if grants:
        op.bulk_insert(role_permissions_table, grants)


def downgrade() -> None:
    op.drop_table('role_permissions')
    op.drop_table('permissions')
```

### 2 — Models

**Create file:** `backend/app/models/security.py` additions (same file Story 15 created):

```python
class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = _pk()
    key: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)


role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)
```

Add `permissions: Mapped[list[Permission]] = relationship(secondary=role_permissions)` to `Role` (plain many-to-many via the association table, matching SQLAlchemy's standard `secondary=` idiom — no need for an explicit association-object class since `role_permissions` carries no extra columns, unlike `ActivityMention` which is its own mapped class because `activity_event_mentions` is queried directly elsewhere; here nothing queries `role_permissions` directly). Add the necessary `Column`, `ForeignKey`, `Table` imports at the top of `security.py`.

**File:** `backend/app/models/__init__.py` — add `Permission` to the `app.models.security` import and `__all__`.

### 3 — `require_permission`

**File:** `backend/app/api/deps.py` — append:

```python
def require_permission(key: str):
    """Dependency factory: 403s unless the current agent's role grants `key`.

    A role-less agent (role_id is NULL -- e.g. after their role was deleted,
    see Story 15's Edge Cases) is treated as having no permissions at all,
    the same as the seeded `agent` role.
    """

    def _check(agent: Annotated[Agent, Depends(get_current_agent)]) -> Agent:
        if agent.role is None or key not in {p.key for p in agent.role.permissions}:
            raise Forbidden(f"missing required permission: {key}")
        return agent

    return _check
```

Add `from app.services.errors import Forbidden` to `deps.py`'s imports (not needed by Story 15's version of this file).

### 4 — Apply to Story 15's routes; add `/auth/me`

**File:** `backend/app/api/routes/auth.py`:

- `set_password`, `create_role`, `update_role`, `assign_role` — change their trailing `_: CurrentAgent` parameter to `_: Annotated[Agent, Depends(require_permission("manage_users"))]` for `set_password`/`assign_role`, and `Depends(require_permission("manage_roles"))` for `create_role`/`update_role`. `list_roles` (`GET /roles`) stays open to any authenticated agent — every agent needs to see role names to understand the system, even if they cannot edit them.
- Add:

```python
class MeResponse(BaseModel):
    agent: AgentRead
    permissions: list[str]


@router.get("/auth/me", response_model=MeResponse)
def get_me(agent: CurrentAgent) -> MeResponse:
    keys = sorted(p.key for p in agent.role.permissions) if agent.role else []
    return MeResponse(agent=AgentRead.model_validate(agent), permissions=keys)
```

(`MeResponse` can live in `backend/app/schemas/security.py` instead of inline — final placement at the executor's discretion, following the existing one-schemas-file-per-domain convention.)

### 5 — Overview update

**File:** `.squad/plans/checkout/00-overview.md` — rewrite the "Known cross-story gap" section (lines 82-90) to read, in substance:

> Stories 15-16 replace the `X-Agent-Id` placeholder with real, credential-based staff sessions (`agent_sessions`, bcrypt-hashed passwords) and a real role/permission system (`roles`, `permissions`, `role_permissions`). `PortalUser`/`PortalSession` (Story 06) remains a structurally parallel but intentionally separate identity scheme for customers — reconciling the two into one unified login is still open, and not attempted here, since staff and customers are different trust domains with different data-access rules.
>
> **Deliberately still open, by explicit choice, not oversight:** `customers.router`/`tickets.router`/`channels.router` (except its inbound-webhook route, which must stay open for external providers) remain unauthenticated — gating them would require rewriting most of `backend/tests/conftest.py`'s test fixtures, a distinct future effort. `Interaction.author`/`TicketEvent.actor` remain free text. `unread_mentions`'s 7-day (`activity.MENTION_WINDOW_DAYS`) approximation and agent timezone (`tasks_due_today`'s UTC-day counting) are both unrelated to authentication/authorization and remain open per the original gap description.

Also add Story 15/16 rows to the Stories table and a `**15 → 16.**` dependency-notes bullet describing this story's dependence on Story 15's `Role`/`get_current_agent`.

---

## Frontend Tasks

### 6 — Permission-aware UI

**Create file:** `frontend/src/api/auth.ts` addition:

```ts
export interface MeResponse {
  agent: Agent;
  permissions: string[];
}

export function getMe(): Promise<MeResponse> {
  return request<MeResponse>("/auth/me");
}
```

**File:** `frontend/src/pages/LoginPage.tsx` — after `setStaffSession(token, agent)`, call `getMe()` and store the returned `permissions` array alongside the staff session (extend `staffAuth.ts`'s stored user shape, or add a small parallel `permissions` key in the same module — final shape at executor's discretion, following the existing `staffToken`/`staffUser` two-key pattern).

**File:** `frontend/src/pages/TicketSetupPage.tsx` — the role-selector and set-password controls added in Story 15 are now conditionally rendered only when the current agent's permission set includes `manage_users` (and role create/edit, if surfaced, behind `manage_roles`); an agent without the permission sees a read-only role column instead. This is client-side hiding only — `require_permission` on the server is the real gate, per this story's own Story Goal.

---

## Edge Cases & Failure Modes

- **A role-less agent (`role_id IS NULL`)** — `require_permission` treats this as zero permissions, never an error; `agent.role.permissions` access is guarded by the `agent.role is None` check first.
- **An agent's role is changed mid-session.** No caching of permissions on the session/token — `require_permission` re-reads `agent.role.permissions` from the database on every request (via the ORM relationship, lazy-loaded per request), so a role change takes effect on the agent's very next request, not just their next login.
- **`manager` role and `view_audit_log`** — deliberately the only permission `manager` gets in this story's seed; Story 17/18 decide whether `manager` also gets read-only visibility into system configuration when those tables exist (this story's seed only grants what already has a concrete route: `view_audit_log`, added here even though Story 17 defines the route that checks it, since the permission *key* is part of this story's fixed catalog and Story 17 only wires the check).
- **Calling `require_permission` for a key not in the seeded catalog** (a typo in a route decorator) — the check simply never matches any agent's permission set, so every request 403s; no separate "unknown permission key" error path, since a missing route access is the safe failure direction (deny, not allow).
- **A pre-existing agent from before Story 15/16 (created before `roles` existed)** has `role_id = NULL` by default (the column is nullable, added without backfill in Story 15) — treated as no permissions, same as any other role-less agent above; an admin must explicitly assign a role.

---

## Test Plan

Backend (`backend/tests/`):

1. **Create `backend/tests/test_permissions.py`**:
   - `test_admin_role_can_manage_users` — `admin_client` (Story 15 fixture, already `admin` role) succeeds at `set-password`/`assign-role`/`create-role`.
   - `test_agent_role_forbidden_from_managing_users` — `agent_client` (default `agent` role, per Story 15's `agent`/`other_agent` fixtures needing an explicit role assignment to gain any permission) gets `403` on the same actions.
   - `test_manager_role_can_view_audit_log_but_not_manage_users` — requires a new `manager_client` fixture (log in as an agent assigned the `manager` role) — add it to `conftest.py`; asserts `200` on a `view_audit_log`-gated route (stub this against Story 17's not-yet-existing route by asserting against `require_permission` directly via a throwaway test route, or defer this specific assertion to Story 17's own test suite once `/audit-log` exists — note this explicitly in the test file if deferred) and `403` on `manage_users`-gated ones.
   - `test_role_less_agent_has_no_permissions` — an agent with `role_id = None` gets `403` on every `require_permission`-gated route.
   - `test_get_me_returns_resolved_permissions` — `GET /api/auth/me` as `admin_client` returns all four permission keys; as `agent_client` (no role assigned) returns `[]`.
2. **Update `backend/tests/test_staff_auth.py` and `test_roles.py`** (from Story 15) — any assertion that `agent_client` could freely call `set-password`/role endpoints must be revised: those calls now require `manage_users`/`manage_roles`, so Story 15's own tests for those endpoints should be re-pointed at `admin_client` (already true in Story 15's Test Plan, which used `admin_client` for those exact calls — confirm no drift).
3. **Regression:** `pytest -q` full suite.

Frontend:

4. **Create `frontend/src/pages/__tests__/TicketSetupPage.test.tsx` update (or new test)** — asserts the role/password controls are hidden when the mocked `/auth/me` response has no `manage_users` permission, and shown when it does.

---

## Verification Steps

1. **Backend migrates:** `cd backend && uv run alembic upgrade head` — `0011_permissions` applies cleanly on top of `0010`.
2. **Backend tests:** `cd backend && uv run pytest -q`.
3. **Manual smoke:** log in as the seeded admin (`admin@crm.local`), confirm `GET /api/auth/me` lists all four permissions; create a second agent, assign it the `agent` role (or leave role-less), log in as it, confirm `set-password`/role endpoints return `403`.
4. **Frontend type-checks and tests:** `cd frontend && npx tsc -b --noEmit && npm test`.
5. **Regression:** full `pytest -q` and `npm test`.

---

## Done Criteria

- [ ] `permissions`/`role_permissions` tables exist, seeded with the fixed catalog and the three roles' grants from Story 15.
- [ ] `require_permission(key)` exists in `backend/app/api/deps.py` and gates Story 15's `set-password`/`assign_role`/`create_role`/`update_role` routes.
- [ ] `GET /api/auth/me` returns the current agent and their resolved permission-key list.
- [ ] `.squad/plans/checkout/00-overview.md`'s "Known cross-story gap" section is rewritten to reflect what is now closed versus deliberately still open.
- [ ] Frontend hides (does not just fail to reject) admin-only controls for agents lacking the relevant permission.
- [ ] `pytest -q`, `npm test`, and `npx tsc -b --noEmit` are all green, with no regression in Story 15's own tests.

**STOP HERE. Report to the user and wait for confirmation before proceeding to Story 17.**
