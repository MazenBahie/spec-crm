# Story 18 — System Configuration

## Prerequisites

- [Story 16](16-story-permissions-access-control.md) completed: the `manage_system_config` permission key already exists in the seeded `permissions` catalog (`backend/alembic/versions/0011_permissions.py`) — this story wires the first route that checks it.
- [Story 17](17-story-audit-logs.md) completed: `app/services/audit.py::record()` exists — every config write in this story calls it.
- The Alembic chain is linear: this story's migration sets `down_revision = '0012'`.
- **Explicit, documented scope decision — read before implementing anything here:** this story introduces a **new, first-of-its-kind** DB-backed, admin-editable settings table. It does **not** migrate any existing env-only `Settings` field (`backend/app/core/config.py`: `ai_enabled`, `anthropic_api_key`, `ai_model`, `portal_session_ttl_days`, `agent_session_ttl_days`) into it, and does not touch any of the "tuning constant, not a config table" precedents cited throughout `.squad/plans/checkout/00-overview.md` (`app/services/activity.py::MENTION_WINDOW_DAYS`, `app/services/tickets.py::MAX_ESCALATION_LEVEL`, `app/services/reports.py::SLA_FIRST_RESPONSE_MINUTES`/`SLA_RESOLUTION_MINUTES`). Doing either would require every one of Stories 06-14 to switch a live code path from reading `settings.x`/a module constant to a database lookup — far beyond what a bare "System configuration" intake bullet asks for, and each such change would need its own review of what happens when the value changes mid-request, mid-session, or mid-migration. Instead, this story ships a **new, self-contained key-value settings area** for admin-facing values that do not already have an owner.
- `backend/app/core/config.py` (read in full, 28 lines) — confirms there is currently no DB-backed settings mechanism anywhere in this codebase to extend; this story is the first.

---

## Story Goal

A generic, admin-editable key-value configuration store, with a fixed initial seed of genuinely new settings that don't already belong to an existing owner:

1. **`system_settings` table** — `key` (unique), `value` (a JSON-serialisable string), `description`, `updated_at`, `updated_by_agent_id`.
2. **Seed values** (chosen for being real, low-risk, and previously nonexistent — not stand-ins for any existing constant): `support_hours_message` (a free-text string shown to customers, e.g. on the portal), `maintenance_mode_banner` (a free-text string; empty means no banner shown). Both are genuinely new, optional, low-risk admin toggles — neither has any effect on business logic in this story (a follow-up story can wire `maintenance_mode_banner` into `PortalApp.tsx`'s shell once a concrete design exists; this story ships the storage and admin editing UI only, not that consumer).
3. **`GET /api/system-settings`, `PATCH /api/system-settings/{key}`** — gated by `require_permission("manage_system_config")`, every write audit-logged via Story 17's `audit.record()`.
4. **A `SystemConfigPage`** for staff with that permission.

**Out of scope:**
- Migrating any existing env-var or module-constant setting into this table (see Prerequisites).
- Any consumer of `maintenance_mode_banner`/`support_hours_message` beyond the admin edit screen itself — wiring either value into a customer-facing surface is left to a future story once there's a concrete design for where it should appear.
- Arbitrary key creation from the UI — the key catalog is fixed at migration time (`PATCH` only, no `POST`), so a typo can't silently create an orphan setting nobody reads. A future story can add key creation if a real need arises.

---

## Context — Read These Files First

1. `backend/app/core/config.py` (read in full) — confirms the exact env-only settings this story deliberately does not touch (Prerequisites).
2. `.squad/plans/checkout/00-overview.md` line 63 (Story 14's dependency-notes bullet) and lines 12/198-214 of `.squad/plans/checkout/14-story-reports-management.md` — the "tuning constant, not a config table" precedent this story explicitly diverges from for its own new settings, while leaving those specific precedents alone.
3. [Story 17](17-story-audit-logs.md) Backend Tasks §3 — `audit.record()`'s exact signature, called from this story's `set_setting()`.
4. [Story 16](16-story-permissions-access-control.md) Backend Tasks §3 — `require_permission()`.
5. `backend/app/models/customer.py:44-45` — `_pk()` (not used here, since `system_settings` is keyed by its own `key` string rather than a uuid — see Backend Tasks §2 for why).
6. `frontend/src/pages/TicketSetupPage.tsx` (read in full) — the `<table>` + inline-form editing idiom `SystemConfigPage.tsx` follows for a small, flat key/value list.

---

## Backend Tasks

### 1 — Migration

**Create file:** `backend/alembic/versions/0013_system_configuration.py`, `down_revision = '0012'`.

```python
"""system settings (admin-editable key-value configuration)

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-02
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0013'
down_revision: Union[str, None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEED: dict[str, tuple[str, str]] = {
    # key: (default value, description)
    "support_hours_message": ("", "Free-text message shown to customers describing support hours."),
    "maintenance_mode_banner": ("", "Free-text banner shown when non-empty. Empty means no banner."),
}


def upgrade() -> None:
    op.create_table(
        'system_settings',
        sa.Column('key', sa.String(length=80), nullable=False),
        sa.Column('value', sa.Text(), nullable=False, server_default=''),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_by_agent_id', sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(['updated_by_agent_id'], ['agents.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('key'),
    )

    settings_table = sa.table(
        'system_settings', sa.column('key', sa.String()), sa.column('value', sa.Text()), sa.column('description', sa.Text())
    )
    op.bulk_insert(
        settings_table,
        [{'key': key, 'value': default, 'description': desc} for key, (default, desc) in SEED.items()],
    )


def downgrade() -> None:
    op.drop_table('system_settings')
```

`key` is the primary key (a short, fixed, human-readable string), not a uuid — this table is a small, fixed catalog of named settings, not a growing collection of independent rows, so a natural string key is more legible in the database and in audit-log `target_id` fields than an opaque uuid. This is a deliberate, one-off divergence from every other table's `_pk()` uuid-PK convention, documented here so it doesn't read as an oversight.

### 2 — Model

**Create file:** `backend/app/models/system_settings.py`

```python
"""Admin-editable key-value system configuration.

A new, first-of-its-kind DB-backed settings mechanism -- see this story's own
Prerequisites in `.squad/plans/checkout/18-story-system-configuration.md` for
why this does not replace or migrate `app.core.config.Settings` (env-only) or
any existing module-level tuning constant.

`key` is the primary key: a small, fixed catalog of named settings, not a
growing collection -- see the migration's own note on why this diverges from
the `_pk()` uuid-PK convention used everywhere else.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.ticket import Agent


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    description: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    updated_by_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL")
    )

    updated_by: Mapped["Agent | None"] = relationship()
```

Register in `backend/app/models/__init__.py`.

### 3 — Service

**Create file:** `backend/app/services/system_settings.py`

```python
"""System-configuration service layer.

Pure functions over a SQLAlchemy Session. `set_setting` is the only write
path and always audit-logs (Story 17) -- there is no route or function that
bypasses it.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.system_settings import SystemSetting
from app.services import audit
from app.services.errors import NotFound


def list_settings(db: Session) -> list[SystemSetting]:
    return list(db.scalars(select(SystemSetting).order_by(SystemSetting.key)))


def get_setting(db: Session, key: str) -> SystemSetting:
    setting = db.get(SystemSetting, key)
    if setting is None:
        raise NotFound(f"setting {key!r} not found")
    return setting


def set_setting(db: Session, key: str, value: str, *, actor_agent_id: uuid.UUID) -> SystemSetting:
    setting = get_setting(db, key)  # 404s on an unknown key -- no implicit creation, see Story Goal.
    setting.value = value
    setting.updated_by_agent_id = actor_agent_id
    db.flush()
    db.refresh(setting)
    audit.record(
        db,
        action="system_config.updated",
        agent_id=actor_agent_id,
        target_type="system_setting",
        payload={"key": key, "value": value},
    )
    return setting
```

Note `target_id` is omitted from the `audit.record(...)` call (it is typed `uuid.UUID | None` in `AuditLogEntry`, and `key` is a string, not a uuid) — the setting's identity is carried in `payload["key"]` instead. This is a deliberate, narrow exception to Story 17's `target_id` field being populated; document it in that field's own docstring if it isn't already generic enough (`target_id: Mapped[uuid.UUID | None]` — already nullable, so this is a supported, not a broken, usage).

### 4 — Schemas

**Create file:** `backend/app/schemas/system_settings.py`

```python
from __future__ import annotations

from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field


class SystemSettingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    value: str
    description: str | None
    updated_at: datetime
    updated_by_agent_id: uuid.UUID | None


class SystemSettingUpdate(BaseModel):
    value: str = Field(max_length=10_000)
```

### 5 — Routes

**Create file:** `backend/app/api/routes/system_settings.py`

```python
"""System-configuration HTTP routes. Every write is audit-logged via
app.services.audit -- see app.services.system_settings.set_setting."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.session import get_db
from app.models.ticket import Agent
from app.schemas.system_settings import SystemSettingRead, SystemSettingUpdate
from app.services import system_settings as svc

router = APIRouter(
    prefix="/system-settings",
    tags=["system-settings"],
    dependencies=[Depends(require_permission("manage_system_config"))],
)

DbDep = Annotated[Session, Depends(get_db)]
ActorDep = Annotated[Agent, Depends(require_permission("manage_system_config"))]


@router.get("", response_model=list[SystemSettingRead])
def list_settings(db: DbDep) -> list[SystemSettingRead]:
    return [SystemSettingRead.model_validate(s) for s in svc.list_settings(db)]


@router.patch("/{key}", response_model=SystemSettingRead)
def update_setting(key: str, payload: SystemSettingUpdate, db: DbDep, actor: ActorDep) -> SystemSettingRead:
    return SystemSettingRead.model_validate(svc.set_setting(db, key, payload.value, actor_agent_id=actor.id))
```

(`ActorDep` re-resolves `require_permission` a second time per request purely to get the `Agent` object for `actor.id` — FastAPI caches dependency results per request by default, so this is not a second permission check or a second database round-trip, just a second reference to the same resolved value. This mirrors how `backend/app/api/routes/auth.py` already threads a `CurrentAgent`-resolved agent into a handler body.)

### 6 — Wiring

**File:** `backend/app/main.py` — add `system_settings` to the router import block and `app.include_router(system_settings.router, prefix=settings.api_prefix)`.

---

## Frontend Tasks

### 7 — Types, API client, page

**Create file:** `frontend/src/types/systemSettings.ts`:

```ts
export interface SystemSetting {
  key: string;
  value: string;
  description: string | null;
  updated_at: string;
  updated_by_agent_id: string | null;
}
```

**Create file:** `frontend/src/api/systemSettings.ts`:

```ts
import { request } from "./client";
import type { SystemSetting } from "../types/systemSettings";

export function listSystemSettings(): Promise<SystemSetting[]> {
  return request<SystemSetting[]>("/system-settings");
}

export function updateSystemSetting(key: string, value: string): Promise<SystemSetting> {
  return request<SystemSetting>(`/system-settings/${encodeURIComponent(key)}`, {
    method: "PATCH",
    body: JSON.stringify({ value }),
  });
}
```

**Create file:** `frontend/src/pages/SystemConfigPage.tsx` — same `<table>` + inline-edit idiom as `TicketSetupPage.tsx`: one row per setting (`key`, `description`, an editable `value` `<input>`/`<textarea>`, a "Save" button per row calling `updateSystemSetting`), loaded on mount via `listSystemSettings()`.

**File:** `frontend/src/App.tsx` — add a `{ to: "/system-config", label: "System Config" }` `NAV` entry (conditional on `manage_system_config`, same pattern as Story 17's audit-log nav entry) and its `<Route>` inside `StaffProtectedRoute`.

---

## Edge Cases & Failure Modes

- **`PATCH` on an unknown key** — `get_setting()` raises `NotFound` → 404; there is no implicit key creation (Story Goal §3's explicit "no `POST`" decision).
- **Concurrent edits to the same key by two admins** — last-write-wins, no optimistic-concurrency check, matching this codebase's existing documented stance elsewhere (`app.services.tickets`'s own module docstring on reassignment, cited in `00-overview.md`'s Story 14 entry). `updated_at`/`updated_by_agent_id` at least record who made the last change, visible both here and in the Story 17 audit trail.
- **A value containing characters that would break a future consumer's rendering (e.g. HTML in `maintenance_mode_banner`)** — out of scope for this story, since this story ships no consumer of the value yet (see Story Goal's explicit scope note); a future story that renders it must sanitize/escape at render time, not at write time.
- **An agent without `manage_system_config` calls `GET /system-settings`.** Router-level `dependencies=[Depends(require_permission(...))]` 403s the read too, not just the write — unlike the audit log (Story 17), which has no separate "view" vs. "edit" distinction requested by this intake either, so both routes share one permission key for simplicity.
- **The seeded default values are empty strings**, not `null` — `value` is `NOT NULL` with `server_default=''`, so `SystemSettingRead.value` is always a `str`, never requiring the frontend to handle a null-vs-empty distinction.

---

## Test Plan

Backend (`backend/tests/`):

1. **Create `backend/tests/test_system_settings.py`**:
   - `test_list_settings_returns_seeded_defaults` — `admin_client.get("/api/system-settings")` returns both seeded keys with empty-string values.
   - `test_update_setting` — `admin_client.patch(...)` updates a value; a follow-up `list` reflects it; `updated_by_agent_id` is the admin's id.
   - `test_update_unknown_key_returns_404`.
   - `test_manage_system_config_required` — `agent_client` (no permission) gets `403` on both `GET` and `PATCH`.
   - `test_update_writes_audit_entry` — after a `PATCH`, `admin_client.get("/api/audit-log")` (Story 17) shows a `system_config.updated` entry with `payload.key` matching.
2. **Regression:** `pytest -q` full suite.

Frontend:

3. **Create `frontend/src/pages/__tests__/SystemConfigPage.test.tsx`** — mocks `GET`/`PATCH /system-settings`; asserts editing a value and saving calls the mocked `PATCH` with the right body and re-renders the updated value.
4. **Update `frontend/src/__tests__/navigation.test.tsx`** — assert the "System Config" nav link is hidden without `manage_system_config` and shown with it.

---

## Verification Steps

1. **Backend migrates:** `cd backend && uv run alembic upgrade head` — `0013_system_configuration` applies on top of `0012`; confirms the full chain `0001` → `0013` runs clean on a fresh database.
2. **Backend tests:** `cd backend && uv run pytest -q` — full suite, including all of Stories 15-18's new tests.
3. **Manual smoke:** log in as admin, open System Config, edit `support_hours_message`, save, reload the page, confirm the new value persists; confirm the change appears in the Audit Log page (Story 17).
4. **Frontend type-checks and tests:** `cd frontend && npx tsc -b --noEmit && npm test`.
5. **Full regression:** `pytest -q` and `npm test` in full across the whole backend/frontend suite — this is the last story in the Security & Administration arc, so this is the final check that Stories 15-18 together leave every prior story (01-14) working unchanged.

---

## Done Criteria

- [ ] `system_settings` table exists, seeded with `support_hours_message`/`maintenance_mode_banner`.
- [ ] `GET /api/system-settings`, `PATCH /api/system-settings/{key}` exist, gated by `manage_system_config`, and every write is audit-logged.
- [ ] No existing env-var setting or module-level tuning constant was migrated into this table — confirmed by diff review against Prerequisites' explicit scope boundary.
- [ ] `SystemConfigPage.tsx` exists and is hidden from staff without the permission.
- [ ] `.squad/plans/checkout/00-overview.md` and `.squad/plans/00-index.md` reflect Stories 15-18 (done as part of this planning pass — see the sibling update to those two files).
- [ ] `pytest -q`, `npm test`, and `npx tsc -b --noEmit` are all green, with the full backend/frontend suite (Stories 01-18) passing together.

**This is the final story in the Security & Administration area.**
