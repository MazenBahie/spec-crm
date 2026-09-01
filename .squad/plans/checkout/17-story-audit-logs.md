# Story 17 — Audit Logs

## Prerequisites

- [Story 15](15-story-staff-authentication-users-roles.md) completed: real agent identity (`Agent`, `agent_sessions`) to attribute actions to.
- [Story 16](16-story-permissions-access-control.md) completed: the `view_audit_log` permission key already exists in the seeded `permissions` catalog (`backend/alembic/versions/0011_permissions.py`'s `PERMISSIONS` dict) — this story is the first to actually wire a route that checks it.
- The Alembic chain is linear: this story's migration sets `down_revision = '0011'`.
- `backend/app/services/activity.py` (read in full, 139 lines) is the direct structural precedent for everything in this story: `record()` (36-62), its "caller records after the state change it describes has already been flushed, same transaction" discipline (module docstring lines 1-13), and `ActivityEvent`'s plain-string `event_type` (not a named enum) reasoning in `backend/app/models/agent.py:49-52` ("new event types are expected to arrive with later stories, which would each need an `ALTER TYPE` migration otherwise"). This story's `audit_log_entries.action` follows the exact same reasoning.

---

## Story Goal

A queryable, append-only log of security-sensitive administrative actions — who did what, to what, and when — covering every mutation Story 15/16 introduced:

1. **`audit_log_entries` table** — actor (`agent_id`, nullable), `action` (plain string), `target_type`/`target_id` (what was acted on), a freeform `payload`, and a Python-stamped `created_at`.
2. **`app/services/audit.py::record(...)`** — the one function every other service calls after a security-sensitive mutation.
3. **Call sites added to Story 15/16's own functions**: login, logout, password set, role created/updated, role assigned to an agent.
4. **`GET /api/audit-log`** — paginated, filterable by actor/action/date range, gated by `require_permission("view_audit_log")` (Story 16).
5. **An `AuditLogPage`** for staff with that permission.

**Out of scope:**
- Auditing every mutation in the entire application (ticket edits, customer edits, etc.) — those already have their own history mechanisms (`TicketEvent`, `ActivityEvent`) that predate this story and are not being replaced or duplicated. This story's audit log is specifically for the *security-administration* actions Story 15/16 introduced, not a general-purpose change log.
- Tamper-evidence (hashing/signing log entries) — out of scope; this is a plain, trusted-staff-readable table like every other table in this codebase.
- Auditing `system_settings` changes — that call site is added by [Story 18](18-story-system-configuration.md), which depends on this story's `audit.record()` existing first.

---

## Context — Read These Files First

1. `backend/app/services/activity.py` (read in full) — `record()` (36-62) is the function signature and discipline this story's `app/services/audit.py::record()` mirrors. `resolve_mentions`/`_visible_to`/`feed_for_agent` (65-117) are *not* relevant here — this story has no mentions concept.
2. `backend/app/models/agent.py:196-236` — `ActivityEvent`: `agent_id` nullable FK `SET NULL` ("the actor may be the system, or an unauthenticated path such as an inbound webhook", lines 205-209) and `event_type: str` plain column (210, rationale 49-52) are both copied verbatim in shape for `AuditLogEntry`.
3. `backend/app/models/ticket.py:194-201` — `TicketEvent.created_at`'s comment on why timestamps are stamped in Python (`default=`) rather than relying only on `server_default`: SQLite's `CURRENT_TIMESTAMP` has second resolution, so same-second writes would tie and sort by the random uuid4 PK instead. `AuditLogEntry.created_at` follows the same pattern.
4. `backend/app/services/tickets.py:246-317` — the count+paginate `select(func.count()).select_from(...)` idiom `list_entries()` reuses, per `00-overview.md:40`'s citation of this exact pattern.
5. [Story 15](15-story-staff-authentication-users-roles.md) Backend Tasks §6 (`agent_auth.py`) and [Story 16](16-story-permissions-access-control.md) Backend Tasks §3-4 (`require_permission`, `auth.py` routes) — the exact functions this story adds `audit.record(...)` calls to.
6. `backend/app/main.py` — router registration block, for wiring the new `audit.router`.
7. `.squad/plans/checkout/14-story-reports-management.md` Backend/Frontend Tasks §7-8 (`DateRangeFilter`, plain-`<table>` report page) — the frontend precedent `AuditLogPage.tsx` follows: a date-range filter plus a plain table, no charting library.

---

## Backend Tasks

### 1 — Migration

**Create file:** `backend/alembic/versions/0012_audit_logs.py`, `down_revision = '0011'`.

```python
"""audit log entries

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-02
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0012'
down_revision: Union[str, None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_log_entries',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('agent_id', sa.Uuid(), nullable=True),
        sa.Column('action', sa.String(length=80), nullable=False),
        sa.Column('target_type', sa.String(length=60), nullable=True),
        sa.Column('target_id', sa.Uuid(), nullable=True),
        sa.Column('payload', postgresql.JSONB(none_as_null=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_audit_log_entries_agent_id'), 'audit_log_entries', ['agent_id'], unique=False)
    op.create_index(op.f('ix_audit_log_entries_action'), 'audit_log_entries', ['action'], unique=False)
    op.create_index(op.f('ix_audit_log_entries_created_at'), 'audit_log_entries', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_audit_log_entries_created_at'), table_name='audit_log_entries')
    op.drop_index(op.f('ix_audit_log_entries_action'), table_name='audit_log_entries')
    op.drop_index(op.f('ix_audit_log_entries_agent_id'), table_name='audit_log_entries')
    op.drop_table('audit_log_entries')
```

Note: unlike `ActivityEvent.payload` (`app/models/agent.py:66-68`), which uses a JSON/JSONB *variant* so the SQLite test database can create the column too, the migration itself only ever runs against Postgres (per `00-overview.md`'s "Migrations are Postgres-only" shared contract) — the SQLite-compatible variant type lives in the **model** (`app/models/security.py`, §2 below), not the migration. `postgresql.JSONB` here is correct for the real migration; the ORM model's `with_variant(...)` is what makes `Base.metadata.create_all()` (used by the SQLite test suite) work too.

### 2 — Model

**File:** `backend/app/models/security.py` — add:

```python
audit_payload_type = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")


class AuditLogEntry(Base):
    __tablename__ = "audit_log_entries"
    __table_args__ = (Index("ix_audit_log_entries_created_at", "created_at"),)

    id: Mapped[uuid.UUID] = _pk()
    # Nullable: the actor may be the system, or a bootstrap action with no
    # agent context yet -- same reasoning as ActivityEvent.agent_id
    # (app/models/agent.py:205-209).
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), index=True
    )
    # Plain string, not a named enum -- same "new actions shouldn't need
    # ALTER TYPE" reasoning as ActivityEvent.event_type (app/models/agent.py:49-52).
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(60))
    target_id: Mapped[uuid.UUID | None] = mapped_column()
    payload: Mapped[dict | None] = mapped_column(audit_payload_type)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )
```

Add the necessary `JSON`/`Index`/`Uuid` imports and a local `_utcnow()` helper (or import the one already defined in `app/models/ticket.py:62-63` if the project's convention allows cross-module reuse — check whether other model files import it or each defines its own; `app/models/agent.py` defines its own inline `datetime.now(timezone.utc)` calls rather than importing `ticket._utcnow`, so follow that same per-module convention here rather than introducing a cross-file import). Register `AuditLogEntry` in `backend/app/models/__init__.py`.

### 3 — Service

**Create file:** `backend/app/services/audit.py`

```python
"""Security-administration audit log.

An append-only log of "an admin action happened" -- who (agent_id, nullable),
what (action, a plain string), on what (target_type/target_id), with what
detail (payload). Mirrors app.services.activity's own discipline exactly: a
caller records after the state change it describes has already been flushed,
inside the same transaction (`record()` never commits).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.security import AuditLogEntry

MAX_LIMIT = 200


def record(
    db: Session,
    *,
    action: str,
    agent_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> AuditLogEntry:
    entry = AuditLogEntry(
        agent_id=agent_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        payload=payload,
    )
    db.add(entry)
    db.flush()
    return entry


def list_entries(
    db: Session,
    *,
    agent_id: uuid.UUID | None = None,
    action: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AuditLogEntry], int]:
    limit = min(limit, MAX_LIMIT)
    filters = []
    if agent_id is not None:
        filters.append(AuditLogEntry.agent_id == agent_id)
    if action is not None:
        filters.append(AuditLogEntry.action == action)
    if date_from is not None:
        filters.append(AuditLogEntry.created_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to is not None:
        filters.append(AuditLogEntry.created_at <= datetime.combine(date_to, time.max, tzinfo=timezone.utc))

    total = db.scalar(select(func.count()).select_from(AuditLogEntry).where(*filters)) or 0
    rows = list(
        db.scalars(
            select(AuditLogEntry)
            .where(*filters)
            .order_by(AuditLogEntry.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return rows, total
```

### 4 — Wire `audit.record(...)` into Story 15/16's functions

**File:** `backend/app/services/agent_auth.py` (Story 15) — add an `audit` import and a call at the end of each of these, after the existing `db.flush()`:

- `login()` — `audit.record(db, action="agent.login", agent_id=agent.id)`.
- `logout()` — only when an actual session was revoked (inside the `if session is None: return` guard's else-path) — `audit.record(db, action="agent.logout", agent_id=agent_id)`.
- `set_password()` — `audit.record(db, action="agent.password_set", agent_id=<the acting agent, threaded in as a new parameter>, target_type="agent", target_id=agent_id)`. This requires adding an `actor_agent_id: uuid.UUID` parameter to `set_password()` — update its call site in `backend/app/api/routes/auth.py` to pass the `require_permission("manage_users")`-resolved agent's id.
- `create_role()`/`update_role()` — `audit.record(db, action="role.created"/"role.updated", agent_id=<actor>, target_type="role", target_id=role.id, payload={"name": role.name})`. Same actor-threading change as `set_password`.
- `assign_role()` — `audit.record(db, action="agent.role_assigned", agent_id=<actor>, target_type="agent", target_id=agent_id, payload={"role_id": str(role_id) if role_id else None})`.

**File:** `backend/app/api/routes/auth.py` — every route calling one of the above now passes `agent.id` (the `require_permission`/`CurrentAgent`-resolved caller) as the new `actor_agent_id` argument.

### 5 — Route

**Create file:** `backend/app/api/routes/audit.py`

```python
"""Audit-log HTTP routes. Read-only -- every write happens via
app.services.audit.record(), called from other services, never from a route
handler directly."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.session import get_db
from app.schemas.customer import Page
from app.schemas.security import AuditLogEntryRead
from app.services import audit as svc

router = APIRouter(
    prefix="/audit-log", tags=["audit"], dependencies=[Depends(require_permission("view_audit_log"))]
)

DbDep = Annotated[Session, Depends(get_db)]


@router.get("", response_model=Page[AuditLogEntryRead])
def list_audit_log(
    db: DbDep,
    agent_id: uuid.UUID | None = None,
    action: str | None = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[AuditLogEntryRead]:
    items, total = svc.list_entries(
        db, agent_id=agent_id, action=action, date_from=date_from, date_to=date_to, limit=limit, offset=offset
    )
    return Page[AuditLogEntryRead](items=[AuditLogEntryRead.model_validate(e) for e in items], total=total)
```

Add `AuditLogEntryRead` to `backend/app/schemas/security.py`:

```python
class AuditLogEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID | None
    action: str
    target_type: str | None
    target_id: uuid.UUID | None
    payload: dict | None
    created_at: datetime
```

### 6 — Wiring

**File:** `backend/app/main.py` — add `audit` to the router import block (alphabetically, between `ai` and `auth`) and `app.include_router(audit.router, prefix=settings.api_prefix)`.

---

## Frontend Tasks

### 7 — Types, API client, page

**Create file:** `frontend/src/types/audit.ts`:

```ts
/** Mirrors backend Pydantic schemas in app/schemas/security.py. */
export interface AuditLogEntry {
  id: string;
  agent_id: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  payload: Record<string, unknown> | null;
  created_at: string;
}
```

**Create file:** `frontend/src/api/audit.ts`:

```ts
import { buildQuery, request } from "./client";
import type { AuditLogEntry } from "../types/audit";

interface Page<T> {
  items: T[];
  total: number;
}

export function listAuditLog(
  params: { agent_id?: string; action?: string; date_from?: string; date_to?: string; limit?: number; offset?: number } = {},
): Promise<Page<AuditLogEntry>> {
  return request<Page<AuditLogEntry>>(`/audit-log${buildQuery({ ...params })}`);
}
```

**Create file:** `frontend/src/pages/AuditLogPage.tsx`: follows `frontend/src/pages/reports/TicketReportPage.tsx`'s shape (`.squad/plans/checkout/14-story-reports-management.md` Backend/Frontend Tasks §7-8) — a `DateRangeFilter`-driven `load()` on mount/range-change, a plain `<table>` (columns: When, Agent, Action, Target). No charting library.

**File:** `frontend/src/App.tsx` — add a `{ to: "/audit-log", label: "Audit Log" }` entry to `NAV`, conditionally rendered only when `getMe()`'s permissions (Story 16) include `view_audit_log` (same conditional-nav pattern as Story 16's Frontend Tasks §6), and a corresponding `<Route path="/audit-log" element={<AuditLogPage />} />` inside the `StaffProtectedRoute` layout route (Story 15).

---

## Edge Cases & Failure Modes

- **An agent is deleted after being logged as an actor.** `agent_id` is `ON DELETE SET NULL` — historical entries survive with `agent_id: null`, matching `ActivityEvent.agent_id`'s exact precedent.
- **Empty filter window / no matching entries** — `list_entries()` returns `([], 0)`, never a 404 or 500; the frontend renders an empty table with a "No entries" row, matching the reports arc's empty-state convention.
- **A caller without `view_audit_log` hits `GET /audit-log`.** Router-level `dependencies=[Depends(require_permission("view_audit_log"))]` 403s before the handler runs.
- **`date_from` after `date_to`** — unlike `reports.py`'s `_window()` (which raises `Conflict` → 409), this route's filters are optional and independent (`created_at >= date_from` and `created_at <= date_to` are separate, both-optional clauses) — an inverted range simply yields zero rows, not an error, since there is no single "window" concept being validated here, only two independent bounds.
- **Very large `payload` values** (e.g. a role's full permission list embedded in a `role.updated` entry) — no application-level size cap in this story; `JSONB` on Postgres has no practical row-size concern at this scale. Revisit only if a future caller starts logging genuinely large payloads.
- **Concurrent writes to the same audit stream** — no locking needed; each `record()` call is a plain `INSERT`, and ordering for display is by `created_at DESC` (Python-stamped, see Context item 3) plus the row's own insertion order as a tiebreak via the database's natural row order — matches every other append-only table in this codebase.

---

## Test Plan

Backend (`backend/tests/`):

1. **Create `backend/tests/test_audit_log.py`**:
   - `test_login_writes_audit_entry` — log in as `agent`, then `admin_client.get("/api/audit-log")`, assert an `agent.login` entry with the right `agent_id`.
   - `test_password_set_writes_audit_entry_with_actor` — `admin_client` sets `agent`'s password; assert the resulting `agent.password_set` entry's `agent_id` is the **admin's** id (the actor), not the target agent's, and `target_id` is the target agent's id.
   - `test_role_assignment_writes_audit_entry`.
   - `test_filter_by_agent_id`, `test_filter_by_action`, `test_filter_by_date_range`.
   - `test_view_audit_log_requires_permission` — `agent_client` (no `view_audit_log` permission) gets `403`; `admin_client` gets `200`.
   - `test_empty_filters_return_empty_page` — a date range with no matching entries returns `{"items": [], "total": 0}`, not an error.
2. **Regression:** `pytest -q` full suite, including Story 15/16's own tests, which now also produce audit entries as a side effect — assert those tests still pass unmodified (audit writes are additive, not behavior-changing for existing assertions).

Frontend:

3. **Create `frontend/src/pages/__tests__/AuditLogPage.test.tsx`** — mocks `GET /audit-log`; asserts the table renders mocked rows and the date-range filter refetches on change (mirroring `TicketReportPage.test.tsx`'s pattern).
4. **Update `frontend/src/__tests__/navigation.test.tsx`** — assert the "Audit Log" nav link is hidden without `view_audit_log` and shown with it.

---

## Verification Steps

1. **Backend migrates:** `cd backend && uv run alembic upgrade head` — `0012_audit_logs` applies on top of `0011`.
2. **Backend tests:** `cd backend && uv run pytest -q`.
3. **Manual smoke:** log in as admin, perform a role assignment, hit `GET /api/audit-log`, confirm the entry appears with the correct actor/target.
4. **Frontend type-checks and tests:** `cd frontend && npx tsc -b --noEmit && npm test`.
5. **Regression:** full `pytest -q` and `npm test`.

---

## Done Criteria

- [ ] `audit_log_entries` table exists; `app/services/audit.py::record()`/`list_entries()` exist.
- [ ] Login, logout, password-set, role-created/updated, and role-assignment all write an audit entry with the correct actor and target.
- [ ] `GET /api/audit-log` is paginated, filterable, and gated by `view_audit_log`.
- [ ] `AuditLogPage.tsx` exists and is hidden from staff without the permission.
- [ ] `pytest -q`, `npm test`, and `npx tsc -b --noEmit` are all green, with no regression in Story 15/16's own tests.

**STOP HERE. Report to the user and wait for confirmation before proceeding to Story 18.**
