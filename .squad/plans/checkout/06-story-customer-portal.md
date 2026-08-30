# Story 06 — Customer Portal

---

## Prerequisites

- **Story 01 completed:** [Project init and structure](01-story-project-init-and-structure.md) — FastAPI backend, React + Vite frontend, Postgres via `infra/docker-compose.yml`.
- **Story 02 completed:** [Customer Management](02-story-customer-management.md) — this story adds a login onto an *existing* `Customer`. It reuses `_pk()` (`backend/app/models/customer.py:43-44`), the `Customer` model and its relationship block (`backend/app/models/customer.py:47-88`), `ContactDetail` (kind `email`, `backend/app/models/customer.py:91-122`) as the signup-matching source, and `_require_active` (`backend/app/services/customers.py:145-147`).
- **Story 03 completed:** [Ticket Management](03-story-ticket-management.md) — this story wraps, not duplicates, `create_ticket`/`get_ticket`/`list_customer_tickets` (`backend/app/services/tickets.py:334-387`, `:304-317`, `:297-301`), reuses `Ticket.is_terminal` (`backend/app/models/ticket.py:147-149`) as the feedback-eligibility gate, and reads (filtered) from `TicketEvent`/`TICKET_EVENT_TYPES` (`backend/app/models/ticket.py:43-52`, `:165-196`).
- **Stories 04 (Communication Channels) and 05 (Agent Dashboard) are not prerequisites.** This story does not touch `channels`, `agent_tasks`, `quick_replies`, or `activity_events`. It follows sequentially in the plan numbering only.
- **Alembic head is `0004`** (`backend/alembic/versions/0004_agent_dashboard.py`, line 34: `revision: str = '0004'`). The new migration sets `down_revision = '0004'`.
- Attachments folder for this intake (`.squad/stories/checkout/customer-portal/attachments/`) is **empty**. There are no design assets to honour; UI follows the existing inline-style conventions (`frontend/src/components/ui.tsx`).

---

## Story Goal

Deliver a **Customer Portal** so a customer can self-serve without calling or emailing support:

1. **Sign up and log in** with an email and password, tied to their existing `Customer` record.
2. **Submit a ticket** against their own account (subject, description, optional category).
3. **Track requests** — a list of their own tickets, with status and priority.
4. **View history** — a customer-safe timeline per ticket (created, status changes) — no internal detail (assignment, escalation, category routing) leaks through.
5. **Submit feedback** — a 1–5 rating plus an optional comment, once a ticket is resolved or closed.

**Not in scope:**

- **FAQs** — explicitly deferred to another story (per the intake).
- **Two-way messaging.** The portal's ticket view is **read-only** beyond creation: no customer replies/comments into the ticket thread. Real conversation is deferred to the already-stubbed web-form channel sub-story (`.squad/plans/checkout/04-story-communication-channels.md`, stories 21–25 in its internal numbering).
- **Password reset, email verification, rate limiting / login lockout.** No email-sending infrastructure exists yet (the email channel adapter is a stub that raises `NotImplementedError` — see Story 04), and no rate-limiting middleware exists anywhere in this codebase. Flagged explicitly as follow-up work, not silently skipped.
- **A separately deployed portal frontend.** The portal is a `/portal/*` route subtree of the existing single Vite app, not a second build.
- **Self-service account creation for a brand-new company.** Signup only *claims* an existing `Customer` contact record; it never creates a new `Customer`.

---

## Context — Read These Files First

1. `backend/app/models/customer.py` — read the whole file (194 lines). Copy the `_pk()` helper (**lines 43-44**) via `from app.models.customer import _pk`, exactly as `backend/app/models/ticket.py:29` already does. Note the `Customer` relationship block at **lines 67-84** — `portal_users` is added at the end of it, same shape as `tickets` (**lines 82-84**). `ContactDetail` (**lines 91-122**, `kind` enum at line 35 `CONTACT_KINDS = ("phone", "email", "address", "other")`) is the signup-matching source — a matching row must have `kind == "email"`.
2. `backend/app/models/ticket.py` — read the whole file (196 lines). `Ticket.is_terminal` (**lines 147-149**) is reused verbatim as the feedback-eligibility gate — do not reimplement the `("resolved", "closed")` check. `TICKET_EVENT_TYPES` (**lines 43-52**) is the full set; the portal only ever exposes `created` and `status_changed` from it (see Backend Task 6). `TicketEvent.actor` (**line 182**) stays free text — do **not** attempt to backfill it with a `portal_user_id` FK; feedback attribution goes through `TicketFeedback.portal_user_id` instead, kept separate from the ticket-history audit trail.
3. `backend/app/api/deps.py` — read all 86 lines. This is the *shape* to mirror for the new portal dependency — `AGENT_HEADER`/`_lookup`/`get_current_agent`/`get_optional_agent`/`CurrentAgent` Annotated alias pattern — but **not** the trust model. `get_current_agent` trusts a bare header value; the portal equivalent must verify a hashed bearer token against a sessions table. Keep the new dependency in its own file (`deps_portal.py`), not appended here, because the docstring/threat model differs enough to blur the "placeholder vs real" distinction this file currently signals (see its own docstring, **lines 1-12**).
4. `backend/app/services/customers.py` — read **lines 145-147** (`_require_active`, raises `Conflict("customer is archived")`) and **lines 76-93** (`get_customer`/`create_customer` shape). `_require_active`'s *reasoning* (not the function itself, which takes a `Customer` not applicable directly here) is reused for the "customer archived after signup" gate in Backend Task 5.
5. `backend/app/services/tickets.py` — read **lines 1-13** (module docstring: "no FastAPI imports", "flush... but never commit", last-write-wins) and:
   - **lines 334-387** `create_ticket` — the function `create_portal_ticket` wraps. Note it already validates the customer is active (`_require_active`, line 336) and resolves priority from category (**lines 346-351**) — the portal wrapper does not re-implement any of this, it only builds the `TicketCreate` payload and calls through.
   - **lines 304-317** `get_ticket` and **lines 297-301** `list_customer_tickets` — both already customer-scoped internally; the portal wrappers add the ownership check and the caller-supplied-`customer_id`-never-trusted rule on top.
6. `backend/app/services/errors.py` — all 30 lines. `NotFound` (line 10), `Conflict` (line 14), `Forbidden` (line 18). **Read the `Forbidden` docstring (lines 18-25) carefully** — it justifies 403-not-404 for *internal* callers ("both agents are trusted staff"). That reasoning does **not** carry over to the portal: a cross-customer ticket-id lookup must return **404**, not 403, so a stranger cannot distinguish "not yours" from "does not exist." This is a deliberate, documented exception to the existing convention — say so in the new service module's docstring.
7. `backend/app/schemas/ticket.py` — read the whole file (186 lines). `TicketCreate` (**lines 86-95**) takes `customer_id` directly from the caller — the new `PortalTicketCreate` schema must **not** expose `customer_id`, `assignee_id`, or `priority` at all, so a customer can never inject another customer's id or override staff-controlled routing. Mirror the `Literal` alias style (**lines 13-16**) and the `Read`-variant `model_config = ConfigDict(from_attributes=True)` convention throughout.
8. `backend/app/main.py` — all 56 lines. New router import added beside the existing block (**lines 5-13**) and one `app.include_router(portal.router, prefix=settings.api_prefix)` call added beside the others (**lines 26-36**). The exception handlers (**lines 41-53**) already cover `NotFound`/`Forbidden`/`Conflict`/`PayloadTooLarge` — no handler changes needed.
9. `backend/app/core/config.py` — all 18 lines. Add `portal_session_ttl_days: int = 14` to `Settings` (env override `CRM_PORTAL_SESSION_TTL_DAYS`, via the existing `env_prefix="CRM_"`, line 15).
10. `backend/alembic/versions/0004_agent_dashboard.py` — read the whole file (161 lines). This is the migration-authoring template: `op.create_table`/`op.create_index` ordering in `upgrade()` (**lines 40-130**), FK/index-aware drop ordering in `downgrade()` (**lines 133-154**), and the named-enum-drop loop (**lines 156-160**) — note this story's migration does **not** need that loop (see Backend Task 3) and should say so explicitly rather than silently omitting it.
11. `backend/tests/conftest.py` — read the whole file (200 lines). The `agent`/`inactive_agent`/`agent_client` fixtures (**lines 121-169**) are the direct template for new `portal_user`/`inactive_portal_user`/`portal_client` fixtures — same shape, `TestClient(app, headers={...})` for the authenticated variant (**lines 154-161**) becomes `Authorization: Bearer <token>` instead of `X-Agent-Id`. `customer` (**lines 103-110**) is the parent fixture a `portal_user` fixture signs up against. `missing_uuid()` (**lines 198-199**) is reused for 404 tests.
12. `frontend/src/App.tsx` — all 87 lines. `NAV` (**lines 16-21**) and `<Nav>` are agent-only and are **never** rendered inside the portal subtree. One new route is added to the `<Routes>` block (**lines 62-84**), before the `path="*"` fallback (**line 76**): `<Route path="/portal/*" element={<PortalApp />} />`.
13. `frontend/src/api/client.ts` — all 79 lines. `request<T>()` (**lines 35-56**) bakes `agentHeaders()` in at module scope (**line 39**) and clears the agent id specifically on 401 (**lines 48-52**) — this is exactly why the portal needs its **own** parallel wrapper (`portalClient.ts`) rather than a shared one: a shared `request()` would either always send both header schemes or need every call site to remember which one to pass. `buildQuery()` (**lines 58-67**) is still reused as-is, imported independently.
14. `frontend/src/api/agentContext.ts` — all 69 lines. This is the shape to mirror for `portalAuth.ts`: `STORAGE_KEY` (line 14), the `listeners`/`emit`/`subscribe` pattern (**lines 16-33, 60-63**), `get`/`set`/`clear` (**lines 35-57**), and the header-builder (**lines 66-68**). The docstring (**lines 1-12**) explicitly frames this file as "Placeholder for real authentication" — `portalAuth.ts` is the real thing, storing a bearer token instead of a bare id with no verification.
15. `frontend/src/pages/TicketsListPage.tsx` — read the whole file (237 lines). The debounced-search + `requestId`-guard pattern (**lines 32-46**) and the `Page<T>` + Previous/Next pagination block (**lines 214-234**) are the template for `PortalTicketsPage`, simplified (no assignee/priority filters — a customer's own ticket list needs none of the staff triage controls).
16. `frontend/src/pages/TicketDetailPage.tsx` — read the whole file (183 lines). The `TABS`/`role="tablist"` pattern (**line 14**, **lines 110-132**) is *not* needed for the simpler portal detail page (no Workflow/Messages/Notes tabs — just status + timeline + feedback), but the `load`/`useCallback`/loading-and-error branches (**lines 27-42, 59-76**) are reused directly.
17. `frontend/src/components/ui.tsx` — all 114 lines. Use `styles`, `tokens`, `ErrorBanner`, `Loading`, `StatusBadge`, `formatDateTime`. **Do not introduce a CSS framework** or a second design-token module for the portal.
18. `frontend/src/components/customer/__tests__/ContactDetailsPanel.test.tsx` — the mocking convention for new component tests: `vi.stubGlobal("fetch", …)` returning real `Response` objects.

Grep lines to run before editing:

- `grep -rn "include_router" backend/app` — confirms the current registrations in `backend/app/main.py` before adding `portal.router`.
- `grep -rn "get_db\b" backend/app` — confirms the sync `Session` dependency (there is **no** async session anywhere in this project).
- `grep -rn "bcrypt" backend/` — confirms `bcrypt` is not already a dependency under a different name before adding it.
- `grep -rn "kind.*email\|ContactKind" backend/app frontend/src` — confirms the exact `"email"` literal used for `ContactDetail.kind`, which the signup-matching query filters on.
- `grep -rn "is_terminal" backend/app` — the single existing definition (`ticket.py:147-149`) and every call site, to confirm nothing else needs to change to reuse it.

---

## Product rules (from story)

- **Current behaviour:** `Customer` and `ContactDetail` exist and are staff-managed. There is no login of any kind for a customer — only the internal `Agent`/`X-Agent-Id` placeholder, which trusts a bare header with no credential.
- **New behaviour:** A customer with an existing `email`-kind `ContactDetail` on an **active** `Customer` can **sign up** for a portal login (email + password), creating a `PortalUser` tied to that `Customer`. **Login** issues an opaque bearer session token (hashed at rest); **logout** revokes it. An authenticated `PortalUser` can **create tickets** against their own `Customer` only (never choosing the customer, assignee, or priority), **list and view** only their own tickets with a **customer-safe** status timeline, and **submit or edit** a 1–5 star rating plus comment once a ticket reaches `resolved` or `closed`. A `Customer` account may hold **multiple** `PortalUser` logins (one per contact person); all see the same customer's tickets. If the underlying `Customer` is later archived, every portal request 403s even with a still-valid token — access is gated live, not by revoking existing sessions.

---

## Backend Tasks

### 1 — Dependencies

**File:** `backend/requirements.txt`

Add one new line:

```
bcrypt>=4.1
```

**Justification:** this is the first *real* credential-based auth in the codebase — the existing `X-Agent-Id` scheme is an explicitly documented placeholder that trusts a bare UUID (`backend/app/api/deps.py:1-12`), not a password. Stdlib `hashlib.pbkdf2_hmac` could do this without a new dependency, but hand-rolling the encoding format (algorithm + iteration count + salt, versioned so the cost factor can be raised later without breaking existing hashes) is exactly what a small, vetted library exists to get right for a public-facing credential. `bcrypt` alone (not the larger, maintenance-mode `passlib`) is a single, tiny, actively-maintained C-extension with a self-encoding cost factor (`bcrypt.gensalt(rounds=N)`), so no separate migration is ever needed to raise it.

**File:** `backend/pyproject.toml`

Mirror the same addition in `dependencies` (**line 6-14** block) — this project pins in both places (see Story 02's Backend Task 1 precedent).

No other dependency changes — `fastapi`, `sqlalchemy`, `alembic`, `pydantic`, `python-multipart` are already present and sufficient (no JWT library needed; the session token is a plain opaque string, not a signed JWT, since it is only ever compared against a server-side table, never decoded client-side).

---

### 2 — Data model

**Create file:** `backend/app/models/portal.py`

Follow `backend/app/models/customer.py` and `backend/app/models/ticket.py` exactly: `from __future__ import annotations`, import `_pk` rather than redefining it:

```python
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.customer import _pk

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.ticket import Ticket
```

Three models:

- **`PortalUser`** — `__tablename__ = "portal_users"`.
  - `id` (`_pk()`), `customer_id` → `ForeignKey("customers.id", ondelete="CASCADE")`, required, indexed.
  - `email: str` (`String(320)`, required, **unique** — global uniqueness, not per-customer: a person's email is not expected to be claimed by two different `Customer` accounts in this story's scope).
  - `password_hash: str` (`String(255)`, required — comfortably fits bcrypt's ~60-char output).
  - `display_name: str` (`String(255)`, required).
  - `is_active: bool` (required, `default=True`, `server_default=text("true")`) — mirrors `Agent.is_active` (`ticket.py:69-71`); lets support deactivate one login without touching the `Customer` or its other contacts.
  - `created_at`, `updated_at` — the standard `DateTime(timezone=True)` / `server_default=func.now()` / `onupdate=func.now()` pair used throughout.
  - Relationships: `customer: Mapped[Customer] = relationship(back_populates="portal_users")`, `sessions: Mapped[list[PortalSession]] = relationship(back_populates="portal_user", cascade="all, delete-orphan", passive_deletes=True)`.

- **`PortalSession`** — `__tablename__ = "portal_sessions"`.
  - `__table_args__ = (Index("ix_portal_sessions_portal_user_created", "portal_user_id", text("created_at DESC")),)` — mirrors `ix_tickets_customer_created` (`ticket.py:98`).
  - `id` (`_pk()`), `portal_user_id` → `ForeignKey("portal_users.id", ondelete="CASCADE")`, required, indexed.
  - `token_hash: str` (`String(64)`, required, **unique**, indexed) — the hex-encoded SHA-256 digest of the raw token; the raw token itself is never stored.
  - `expires_at: datetime` (`DateTime(timezone=True)`, required, indexed).
  - `revoked_at: datetime | None` (`DateTime(timezone=True)`, nullable) — set on logout; a session row is never deleted, only soft-revoked, so session lifetime stays auditable (consistent with the append-only philosophy already used for `TicketEvent`, though this table is mutable-once, not append-only).
  - `created_at` (standard).
  - Relationship: `portal_user: Mapped[PortalUser] = relationship(back_populates="sessions")`.

- **`TicketFeedback`** — `__tablename__ = "ticket_feedback"`.
  - `__table_args__ = (Index("ix_ticket_feedback_ticket_id", "ticket_id"),)`.
  - `id` (`_pk()`), `ticket_id` → `ForeignKey("tickets.id", ondelete="CASCADE")`, required, **`unique=True`** — enforces one feedback row per ticket; resubmission is an update, not a new row (see Backend Task 6).
  - `portal_user_id` → `ForeignKey("portal_users.id", ondelete="SET NULL")`, **nullable** — `SET NULL` not `CASCADE`, matching `Ticket.assignee_id`'s reasoning (`ticket.py:109-111`): if a `PortalUser` row is later deleted, the feedback itself (a business record about ticket quality) survives; only the attribution is lost.
  - `rating: int` (`Integer`, required) — validated to 1–5 at the Pydantic schema layer (`Field(ge=1, le=5)`), not a DB `CHECK` constraint — matches this codebase's existing preference for enums/ranges expressed in Python rather than raw SQL `CHECK`s (none appear in any existing model).
  - `comment: str | None` (`Text`, nullable).
  - `created_at`, `updated_at` (standard pair).
  - Relationship: `ticket: Mapped[Ticket] = relationship(back_populates="feedback")`.

**File:** `backend/app/models/customer.py`

Add, at the end of the existing relationship block (immediately after `tickets` at **lines 82-84**, before the blank line preceding the `is_archived` property at line 86):

```python
    portal_users: Mapped[list[PortalUser]] = relationship(
        back_populates="customer", cascade="all, delete-orphan", passive_deletes=True
    )
```

Import `PortalUser` under the existing `TYPE_CHECKING` block (**line 31-32**), alongside `Ticket`.

**File:** `backend/app/models/ticket.py`

Add to the `Ticket` relationship block (**lines 137-145**), after `events`:

```python
    feedback: Mapped[TicketFeedback | None] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", passive_deletes=True
    )
```

Import `TicketFeedback` under `TYPE_CHECKING` (**lines 31-32**).

**File:** `backend/app/models/__init__.py`

Extend the import and `__all__` list with `PortalUser`, `PortalSession`, `TicketFeedback`. **Keep the list alphabetised**, matching the existing convention.

---

### 3 — Migration

**Create file:** `backend/alembic/versions/0005_customer_portal.py`

Generate it, then hand-check:

```bash
cd backend
CRM_DATABASE_URL="postgresql+psycopg://crm:crm@localhost:5432/crm" \
  alembic revision --autogenerate -m "customer portal" --rev-id 0005
```

Required hand-edits:

1. Confirm `down_revision: Union[str, None] = '0004'` (the current head, `backend/alembic/versions/0004_agent_dashboard.py:34-35`).
2. Create three tables in dependency order: `portal_users` (FK → `customers.id` CASCADE), `portal_sessions` (FK → `portal_users.id` CASCADE), `ticket_feedback` (FK → `tickets.id` CASCADE **with a unique constraint on `ticket_id`**, FK → `portal_users.id` SET NULL, nullable).
3. **No named-enum-drop block is needed in `downgrade()`.** Unlike `0001`–`0004`, this migration introduces no new Postgres enum type — `TicketFeedback.rating` is a plain validated `Integer`, not an `Enum` (see Backend Task 2's rationale: enums are painful to widen later if the scale ever changes from 1–5). Say so explicitly in the migration's module docstring — following `0004`'s own docstring style (**lines 1-18**) of stating up front what is and is not created — so a future reader does not mistake the missing enum-drop loop for an oversight against the `0001`–`0004` precedent.
4. Write a docstring in the style of `0004` (**lines 1-18**), naming the three tables and stating that `downgrade` destroys all portal logins, sessions, and feedback irrecoverably (but leaves `customers`, `tickets`, and every other table untouched).
5. `downgrade()` drops `ticket_feedback` and `portal_sessions` first (either order — neither references the other), then `portal_users` last (both reference it via FK).

Verify the round-trip against the compose Postgres before moving on:

```bash
cd backend
alembic upgrade head && alembic downgrade -1 && alembic upgrade head
```

---

### 4 — Pydantic schemas

**Create file:** `backend/app/schemas/portal.py`

Import and reuse `NonEmptyStr` from `app.schemas.customer` (line 15) and `TicketPriority`/`TicketStatus` type aliases where needed from `app.schemas.ticket` — **do not redefine them**.

```python
class PortalSignup(BaseModel):
    email: EmailStr
    password: NonEmptyStr = Field(min_length=8)
    display_name: NonEmptyStr


class PortalLogin(BaseModel):
    email: EmailStr
    password: NonEmptyStr


class PortalUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    email: str
    display_name: str


class PortalAuthResponse(BaseModel):
    token: str
    expires_at: datetime
    portal_user: PortalUserRead


class PortalTicketCreate(BaseModel):
    """No `customer_id`, `assignee_id`, or `priority` — all three are either
    derived from the authenticated session or left to staff triage."""

    subject: NonEmptyStr
    description: str = ""
    category_id: uuid.UUID | None = None


class TicketFeedbackCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = None


class TicketFeedbackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    rating: int
    comment: str | None
    created_at: datetime
    updated_at: datetime
```

Use Pydantic's built-in `EmailStr` (requires no new dependency beyond the `email-validator` extra that ships with `pydantic[email]`; if `pydantic` is not installed with that extra, use `NonEmptyStr` with application-level `@` validation instead and note the substitution in the PR description — check `backend/requirements.txt` for `pydantic[email]` vs plain `pydantic` before assuming `EmailStr` is available).

---

### 5 — Portal auth dependency

**Create file:** `backend/app/api/deps_portal.py`

Mirror the *shape* of `backend/app/api/deps.py` (Annotated aliases, a single shared 401 exception constant, a `_lookup` helper that returns `None` rather than raising) but with real verification:

```python
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

_bearer = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="a valid session token is required"
)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _lookup(
    db: Session, credentials: HTTPAuthorizationCredentials | None
) -> PortalUser | None:
    if credentials is None:
        return None
    token_hash = _hash_token(credentials.credentials)
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
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> PortalUser:
    portal_user = _lookup(db, credentials)
    if portal_user is None:
        raise _UNAUTHORIZED
    return portal_user


def require_active_portal_customer(
    portal_user: Annotated[PortalUser, Depends(get_current_portal_user)],
) -> PortalUser:
    """Same portal user, but 403s if their customer has since been archived.

    Mirrors the reasoning of ``_require_active`` (backend/app/services/customers.py:145-147):
    the session token can still be structurally valid while the underlying
    account should no longer see or touch anything. No background job revokes
    the session proactively — every request re-checks live, matching the
    "computed on read" precedent already used for ``Ticket.is_overdue``.
    """
    if portal_user.customer.is_archived:
        raise Forbidden("customer account is not active")
    return portal_user


CurrentPortalUser = Annotated[PortalUser, Depends(require_active_portal_customer)]
```

Note `require_active_portal_customer` accesses `portal_user.customer` — this triggers a lazy load unless eagerly joined; acceptable here since it is one extra query per authenticated request, matching the simplicity of the rest of this dependency layer (no eager-load optimisation needed at this scale).

---

### 6 — Service layer

**Create file:** `backend/app/services/portal.py`

Same contract as `backend/app/services/tickets.py`: pure functions over `Session`, no FastAPI imports, `flush()`/`refresh()` but never `commit()`.

```python
"""Customer-portal service layer.

Every ticket-scoped function here takes ``customer_id`` from the caller's
verified session (never from the request body or path) and treats a
cross-customer lookup as :class:`NotFound`, not :class:`Forbidden` — a
deliberate divergence from ``app.services.errors.Forbidden``'s documented
reasoning for internal, trusted-staff callers (backend/app/services/errors.py:18-25).
On a public surface, "not yours" and "does not exist" must look identical, or
the response leaks the existence of another customer's ticket id.
"""
```

Functions:

- `signup(db, payload: PortalSignup) -> tuple[PortalUser, str, datetime]` — returns the created user, the **raw** token (only ever returned once, never stored), and its expiry.
  1. Look up an **active** `Customer` with a `ContactDetail(kind="email", value=payload.email)` (case-insensitive match via `func.lower`, matching the search style in `services/customers.py:54-61`). No match, or the matched `Customer.is_archived` → raise `Forbidden("no matching customer account for this email")`.
  2. If a `PortalUser` with this email already exists → raise `Conflict("an account with this email already exists")`.
  3. Hash the password with `bcrypt.hashpw(password.encode(), bcrypt.gensalt())`, create the `PortalUser`.
  4. Call `_create_session(db, portal_user)` (below) and return.
- `login(db, payload: PortalLogin) -> tuple[PortalUser, str, datetime]`:
  1. Look up `PortalUser` by email. Missing, inactive, or `bcrypt.checkpw` failure → **the same** `Forbidden` message as an unknown email (single branch, mirroring `get_current_agent`'s "one branch to handle" philosophy at `deps.py:51-56` — do not distinguish "wrong password" from "no such account" in the response).
  2. Call `_create_session` and return.
- `_create_session(db, portal_user) -> tuple[str, datetime]` — generates `raw = secrets.token_urlsafe(32)`, computes `expires_at = now + timedelta(days=settings.portal_session_ttl_days)`, stores `PortalSession(portal_user_id=..., token_hash=_hash_token(raw), expires_at=expires_at)`, `db.flush()`, returns `(raw, expires_at)`. The raw token is never persisted.
- `logout(db, portal_user_id, raw_token) -> None` — hashes the token, finds the matching non-revoked `PortalSession` for this `portal_user_id`, sets `revoked_at = now()`. No-op (not an error) if already revoked or not found — logout is idempotent.
- `list_portal_tickets(db, customer_id, *, limit=20, offset=0)` — thin wrapper: `return tickets_svc.list_customer_tickets(db, customer_id, limit=limit, offset=offset)`.
- `get_portal_ticket(db, customer_id, ticket_id) -> Ticket` — `ticket = tickets_svc.get_ticket(db, ticket_id)`; if `ticket.customer_id != customer_id`, raise `NotFound(f"ticket {ticket_id} not found")` (same message shape as a genuinely missing ticket — see module docstring above).
- `create_portal_ticket(db, customer_id, payload: PortalTicketCreate) -> Ticket` — builds `TicketCreate(customer_id=customer_id, subject=payload.subject, description=payload.description, category_id=payload.category_id, priority=None, assignee_id=None, due_at=None)` and calls `tickets_svc.create_ticket(db, ticket_create)` — **no logic duplicated**, this is purely an adapter that fixes `customer_id`/`assignee_id`/`priority`.
- `list_portal_ticket_events(db, customer_id, ticket_id) -> list[TicketEvent]` — calls `get_portal_ticket` first (for the ownership check, raising `NotFound` on mismatch), then `tickets_svc.list_events(db, ticket_id, limit=200, offset=0)`, then filters the returned items to `event_type in ("created", "status_changed")` before returning. Every other `event_type` (`priority_changed`, `category_changed`, `assigned`, `unassigned`, `escalated`, `commented`) is internal-only and must not appear in the portal response — leave a comment at the filter site noting that customer-facing replies (once two-way messaging lands) will need a `visibility` concept added to `TicketEvent` or routed through `ChannelMessage` instead, since none exists yet.
- `submit_feedback(db, customer_id, ticket_id, payload: TicketFeedbackCreate) -> TicketFeedback` — `ticket = get_portal_ticket(db, customer_id, ticket_id)` (ownership + existence); if `not ticket.is_terminal`, raise `Conflict("feedback can only be submitted once a ticket is resolved or closed")`; then **upsert** on the unique `ticket_id` — look up an existing `TicketFeedback` row for this ticket and update `rating`/`comment`/`updated_at` if found, otherwise create one. Resubmission is an edit, not a rejection (see Edge Cases).
- `get_feedback(db, customer_id, ticket_id) -> TicketFeedback | None` — ownership check via `get_portal_ticket`, then a plain lookup; returns `None` (not 404) when no feedback has been submitted yet, since "no feedback yet" is a normal state, not an error.

---

### 7 — API routes

**Create file:** `backend/app/api/routes/portal.py`

Mirror `backend/app/api/routes/tickets.py:41-44`: one `router = APIRouter(prefix="/portal", tags=["portal"])`, `DbDep = Annotated[Session, Depends(get_db)]`, **no try/except in route bodies**.

| Method | Path | Auth | Notes |
|---|---|---|---|
| `POST` | `/portal/auth/signup` | none | `PortalAuthResponse`, 201. |
| `POST` | `/portal/auth/login` | none | `PortalAuthResponse`, 200. |
| `POST` | `/portal/auth/logout` | bearer | 204. Reads the raw token straight from the `Authorization` header (via the same `_bearer` dependency used in `deps_portal.py`) rather than `CurrentPortalUser`, since a token that is *about* to be revoked must still resolve for this one call even if some other check would otherwise reject it. |
| `GET` | `/portal/auth/me` | bearer | `PortalUserRead`, built directly from `CurrentPortalUser`. |
| `GET` | `/portal/tickets` | bearer | `Page[TicketRead]`. Query: `limit` (default 20, `ge=1, le=100`), `offset` (`ge=0`) — same bounds as the existing ticket list route. |
| `POST` | `/portal/tickets` | bearer | `TicketRead`, 201. Body: `PortalTicketCreate`. |
| `GET` | `/portal/tickets/{ticket_id}` | bearer | `TicketRead`. 404 (not 403) when the ticket belongs to a different customer. |
| `GET` | `/portal/tickets/{ticket_id}/events` | bearer | `list[TicketEventRead]`, pre-filtered to `created`/`status_changed`. |
| `GET` | `/portal/tickets/{ticket_id}/feedback` | bearer | `TicketFeedbackRead | null`. |
| `POST` | `/portal/tickets/{ticket_id}/feedback` | bearer | `TicketFeedbackRead`. Body: `TicketFeedbackCreate`. 409 if the ticket is not yet terminal. 200 (not 201) on both first submission and edit, since the route cannot cheaply tell the caller which happened without an extra query, and the distinction has no product meaning here. |

**File:** `backend/app/main.py`

Add `portal` to the router import block (**lines 5-13**) and one registration line beside the existing routers (**lines 26-36**):

```python
app.include_router(portal.router, prefix=settings.api_prefix)
```

**No other change to `main.py`.** The existing exception handlers (**lines 41-53**) already map `NotFound`→404, `Forbidden`→403, `Conflict`→409 — exactly the three this story raises.

---

### 8 — Config

**File:** `backend/app/core/config.py`

Add one field to `Settings`:

```python
    portal_session_ttl_days: int = 14
```

Env override: `CRM_PORTAL_SESSION_TTL_DAYS` (via the existing `env_prefix="CRM_"`, line 15 — no change needed to `model_config`).

---

## Frontend Tasks

### 1 — Portal identity and API client

**Create file:** `frontend/src/api/portalAuth.ts`

Mirror `frontend/src/api/agentContext.ts` exactly in shape (`STORAGE_KEY`, `listeners`/`emit`/`subscribe`, try/catch around every `localStorage` access) but store a real bearer token under a **different** key (`"portalToken"`) plus the small identity payload returned by login/signup/`/auth/me` (id, email, display_name, customer_id) under a second key or an in-memory cache refreshed on load. Export `getPortalToken`, `setPortalSession(token, expiresAt, user)`, `clearPortalSession`, `subscribePortalToken`, `portalAuthHeaders()` (returns `{ Authorization: "Bearer " + token }` or `{}`).

**Create file:** `frontend/src/api/portalClient.ts`

A **separate** `requestPortal<T>()`, not a shared wrapper with `frontend/src/api/client.ts` — same `/api` prefix, same JSON handling and `detail`-unwrapping `ApiError` (copy `toApiError` verbatim or import it if exported), but attaches `portalAuthHeaders()` instead of `agentHeaders()`, and on a 401 response calls `clearPortalSession()` (never `clearAgentId()`). Keeping this a fully separate module — rather than parameterising `client.ts`'s `request()` — prevents a portal page from accidentally sending `X-Agent-Id` (or an agent page from sending a portal bearer token) simply by importing the wrong helper; the two identity schemes must never be reachable from the same call site.

**Create file:** `frontend/src/api/portal.ts`

One function per endpoint, following `frontend/src/api/tickets.ts`'s layout (section comments, one function per row of the route table in Backend Task 7): `signup`, `login`, `logout`, `getMe`, `listPortalTickets`, `createPortalTicket`, `getPortalTicket`, `listPortalTicketEvents`, `getFeedback`, `submitFeedback`. Built on `requestPortal`/`buildQuery` (the latter imported from `./client`, since it has no identity coupling).

**Create file:** `frontend/src/types/portal.ts`

Mirror the new Pydantic schemas (`PortalUser`, `PortalTicketCreateInput`, `TicketFeedback`, `TicketFeedbackInput`), following the interface style of `frontend/src/types/ticket.ts`. Import and reuse `Ticket`/`TicketEvent`/`TicketStatus`/`TicketPriority` from `./ticket` rather than redefining them — the portal ticket list/detail views render the same `Ticket` shape the agent app uses, just via a different fetch path.

### 2 — Pages

**Create directory:** `frontend/src/pages/portal/`

- `PortalLoginPage.tsx` — email/password controlled-input form (no form library, matching `frontend/src/pages/CustomerEditPage.tsx`'s pattern), on success calls `setPortalSession(...)` and navigates to `/portal/tickets`. Surfaces the uniform "invalid email or password" `ApiError` message in an `ErrorBanner`.
- `PortalSignupPage.tsx` — email/password/display name form. Surfaces the 403 ("no matching account") and 409 ("already registered") `ApiError`s distinctly via `err.message` (already differentiated server-side).
- `PortalTicketsPage.tsx` — list view. Mirrors `frontend/src/pages/TicketsListPage.tsx`'s `load`/`useCallback`/`requestId`-guard/pagination structure (**lines 44-73, 214-234** of that file) but with **no** status/priority/assignee filter controls and no search box — just the customer's own tickets, newest-first, paginated. Table columns: reference, subject, status, priority, updated. A **New ticket** link.
- `PortalNewTicketPage.tsx` — subject/description/category form (category `<select>` populated via the existing `listCategories`-equivalent call — reuse `frontend/src/api/tickets.ts`'s `listCategories` directly, it is not portal-specific data). No assignee or priority field is rendered at all.
- `PortalTicketDetailPage.tsx` — status (`StatusBadge`), priority, reference, subject/description, a customer-safe timeline (rendering only the `created`/`status_changed` events the backend already filtered — no client-side filtering needed), and — rendered only when `ticket.status` is `"resolved"` or `"closed"` — an inline feedback block: existing rating/comment pre-filled if `getFeedback` returns a row, editable and re-submittable via the same `submitFeedback` call. No separate feedback page/route.

### 3 — Shell and routing

**Create file:** `frontend/src/PortalApp.tsx`

A minimal shell — customer/display name plus a **Logout** button calling `logout()` then `clearPortalSession()` then navigating to `/portal/login` — deliberately **not** importing or rendering the agent `<Nav>` from `App.tsx`. Wraps a nested `<Routes>`:

```tsx
<Routes>
  <Route path="login" element={<PortalLoginPage />} />
  <Route path="signup" element={<PortalSignupPage />} />
  <Route element={<PortalProtectedRoute />}>
    <Route path="tickets" element={<PortalTicketsPage />} />
    <Route path="tickets/new" element={<PortalNewTicketPage />} />
    <Route path="tickets/:id" element={<PortalTicketDetailPage />} />
  </Route>
</Routes>
```

`PortalProtectedRoute` renders `<Outlet />` when `getPortalToken()` is non-null, otherwise `<Navigate to="login" replace />` — read the token via `subscribePortalToken`/`useSyncExternalStore` so a logout while a protected page is mounted redirects immediately, matching the reactive-store pattern `agentContext.ts` already establishes for the agent app.

**File:** `frontend/src/App.tsx`

Add one route to the existing `<Routes>` block (**lines 62-84**), immediately before the `path="*"` fallback (**line 76**):

```tsx
<Route path="/portal/*" element={<PortalApp />} />
```

No changes to `NAV` (**lines 16-21**) or `<Nav>` (**lines 23-56**) — the portal is never reachable through the agent navigation bar.

### 4 — Tests

- `frontend/src/pages/portal/__tests__/PortalLoginPage.test.tsx`, `PortalSignupPage.test.tsx`, `PortalTicketsPage.test.tsx`, `PortalTicketDetailPage.test.tsx` — new, following the `vi.stubGlobal("fetch", ...)` convention of `frontend/src/components/customer/__tests__/ContactDetailsPanel.test.tsx`.
- `frontend/src/__tests__/navigation.test.tsx` (modify) — extend the existing suite to assert `/portal/tickets` redirects to `/portal/login` when no token is stored, and that the agent `<Nav>` never renders a "Portal" link. **Keep the existing health-page/customers/tickets assertions intact.**

---

## Edge Cases & Failure Modes

- **Signup email matches no `ContactDetail`, or matches one on an archived `Customer`** → **403**, the **same** generic message (`"no matching customer account for this email"`) for both cases. Distinguishing them would let an attacker probe which emails belong to real (even if archived) customer accounts — enumeration is avoided by collapsing the two into one response, enforced in `backend/app/services/portal.py::signup`.
- **Signup email already has a `PortalUser`** → **409**, distinct from the 403 above (this is not an enumeration risk in the same way — the caller already supplied a plausible signup intent, and a clear "already registered, log in instead" message is better UX than a generic failure).
- **Login with an unknown email, wrong password, or a deactivated `PortalUser`** → the **same** 403 message for all three, mirroring `get_current_agent`'s "one branch to handle" design (`backend/app/api/deps.py:51-56`) — the frontend does not need to (and cannot) distinguish them.
- **Multiple `PortalUser`s per `Customer`** — fully supported by design. All see the same customer's tickets (scoping is by `customer_id`, not by individual `PortalUser`); nothing in the schema prevents it.
- **Token expiry mid-session** — the next authenticated call gets 401 from `requestPortal`, which calls `clearPortalSession()` (mirroring `client.ts:48-52`'s existing pattern for the agent side); `PortalProtectedRoute`'s next render redirects to `/portal/login`. No silent refresh/rotation — the customer re-authenticates.
- **Cross-customer ticket access** (a valid, active portal session requesting another customer's `ticket_id`) → **404**, not 403 — see the module docstring in `backend/app/services/portal.py` and the `Forbidden` docstring caveat (`backend/app/services/errors.py:18-25`) this deliberately departs from. Enforced in `get_portal_ticket` and every function built on it.
- **Customer archived after a `PortalUser` account already exists** — every subsequent portal request 403s via `require_active_portal_customer` (`backend/app/api/deps_portal.py`), even with a token that has not expired. No background job proactively revokes the session — this is a live, per-request check, consistent with the existing "no background job" precedent for `Ticket.is_overdue` (`backend/app/models/ticket.py:151-162`).
- **Feedback submitted on a non-terminal ticket** → **409** from `submit_feedback`, reusing `Ticket.is_terminal` (`backend/app/models/ticket.py:147-149`) without reimplementing the check.
- **Feedback submitted twice on the same ticket** → **upsert, not rejected.** The unique constraint on `ticket_feedback.ticket_id` backs an update-in-place; a customer refining their rating shortly after submitting is normal, and there is no requirement here for an immutable feedback audit trail (unlike `TicketEvent`, which is append-only by design because it *is* the ticket's audit trail).
- **Portal ticket creation never accepts `customer_id`, `assignee_id`, or `priority` from the client** — `PortalTicketCreate` (Backend Task 4) structurally excludes all three; the portal service builds the underlying `TicketCreate` itself. Attempting to pass any of them in the request body is a plain 422 (unknown field) under Pydantic's default `extra="ignore"`... **verify** whether `TicketCreate`/other schemas set `model_config = ConfigDict(extra="forbid")` anywhere in this codebase before relying on rejection versus silent-ignore behaviour; if none do, extra fields in `PortalTicketCreate` payloads are silently dropped rather than rejected, which is acceptable here since the fields are simply absent from the model regardless.
- **Unicode in email/display_name/ticket subject/description/feedback comment** — all `String`/`Text` columns with no length games beyond the declared caps; assert a round-trip including CJK and em-dashes, matching the precedent in `backend/tests/test_notes.py`.
- **Malformed UUID in a path** (`ticket_id`) → **422** from FastAPI's `uuid.UUID` coercion, not 404 or 500, matching every other route in this codebase.
- **Concurrent signups for the same email** — the unique index on `portal_users.email` is the actual enforcement point; the pre-check in `signup` is a UX nicety, not the guarantee. A rare race surfaces as an `IntegrityError`, not two accounts sharing an email — do **not** add retry logic, document it (same reasoning as ticket-reference collisions in `backend/app/services/tickets.py:75-84`).
- **Password minimum length** — enforced at the schema layer (`Field(min_length=8)` on `PortalSignup.password`) → **422** on a too-short password, not a service-layer check.
- **Rate limiting / brute-force login attempts** — **explicitly out of scope and not silently skipped.** No rate-limiting middleware or infra (Redis, in-memory limiter) exists anywhere in this codebase; adding one correctly (with proper IP-vs-account keying) is a separable concern from this story's data-model/CRUD work. Flag it in the PR description as follow-up work, the same way the ticket-management story flagged the agents-vs-real-users reconciliation (`03-story-ticket-management.md`, Edge Cases, "Uncertainty — agents vs. authenticated users").

---

## Test Plan

Backend — match the fixture style of `backend/tests/conftest.py` and the local-helper style of `backend/tests/test_tickets_crud.py`.

1. **`backend/tests/conftest.py`** (modify) — add fixtures beside the existing `agent`/`agent_client` pair (**lines 121-169**): `portal_user` (signs up via `POST /api/portal/auth/signup` against the `customer` fixture — first add an `email`-kind `ContactDetail` to `customer` via the existing contacts endpoint, since signup requires a matching contact), `inactive_portal_user`, `portal_client` (a `TestClient` pre-authed with `Authorization: Bearer <token>` from the signup response). Do **not** restructure the existing `engine`/`session_factory`/`app`/`client` chain.
2. **`backend/tests/test_portal_auth.py`** (new) — signup succeeds when the email matches an active customer's email contact; 403 when no contact matches; 403 when the matching customer is archived (and the message is identical to the no-match case); 409 on duplicate signup email; login succeeds and returns a usable token; login fails identically for unknown email, wrong password, and a deactivated portal user; `POST /auth/logout` revokes the session (a second call with the same token then 401s); `GET /auth/me` returns the caller's own identity; password shorter than 8 chars → 422.
3. **`backend/tests/test_portal_tickets.py`** (new) — `POST /portal/tickets` creates a ticket owned by the caller's customer, ignoring any `customer_id`/`assignee_id`/`priority` sent in the body; `GET /portal/tickets` returns only the caller's own tickets even when other customers have tickets too; `GET /portal/tickets/{id}` on another customer's ticket id → **404** (assert the response body/status matches the missing-uuid case exactly — this is the load-bearing assertion for the no-enumeration guarantee); `GET /portal/tickets/{id}/events` returns only `created`/`status_changed` events even after a status change, an assignment, and an escalation have all happened on the ticket (seed all three via the existing staff-facing endpoints, then assert the portal view shows exactly two events); unauthenticated request to any `/portal/tickets*` route → 401.
4. **`backend/tests/test_portal_feedback.py`** (new) — 409 when submitting feedback on an `open`/`in_progress` ticket; success once the ticket is moved to `resolved` (via the existing `POST /tickets/{id}/status`); resubmitting updates the existing row rather than creating a second one (assert via a direct row count, not just a 200); `GET .../feedback` returns `null`/`None` before any submission; rating outside 1–5 → 422; feedback on another customer's ticket → 404, matching the ticket-ownership behaviour above.
5. **Regression** — `backend/tests/test_health.py`, `test_customers_crud.py`, `test_contacts.py`, `test_interactions.py`, `test_notes.py`, `test_attachments.py`, `test_tickets_crud.py`, `test_ticket_status.py`, `test_ticket_assignment.py`, `test_ticket_escalation.py`, `test_ticket_categories.py`, `test_ticket_history.py`, `test_ticket_queue.py`, and `test_pagination.py` must all still pass unmodified.

Frontend — Vitest + RTL, mocking via `vi.stubGlobal("fetch", …)` exactly as `frontend/src/components/customer/__tests__/ContactDetailsPanel.test.tsx` does.

6. **`frontend/src/pages/portal/__tests__/PortalLoginPage.test.tsx`** (new) — successful login stores the token and navigates to `/portal/tickets`; a 403 response renders in `role="alert"` without navigating.
7. **`frontend/src/pages/portal/__tests__/PortalSignupPage.test.tsx`** (new) — the 403 "no matching account" and 409 "already registered" errors render distinct messages.
8. **`frontend/src/pages/portal/__tests__/PortalTicketsPage.test.tsx`** (new) — renders rows from a mocked page; each row links to `/portal/tickets/{id}`; `Next`/`Previous` pagination behaves as in `TicketsListPage.test.tsx`; empty state.
9. **`frontend/src/pages/portal/__tests__/PortalTicketDetailPage.test.tsx`** (new) — the feedback block is **absent** for an `open`/`in_progress` ticket and **present** for a `resolved`/`closed` one; submitting feedback calls the API and reflects the saved rating on reload; only `created`/`status_changed` timeline entries render (feed the mock a payload including other event types and assert they do **not** appear, proving the component trusts the server-side filter rather than needing its own).
10. **`frontend/src/__tests__/navigation.test.tsx`** (modify) — `/portal/tickets` with no stored portal token redirects to `/portal/login`; the agent `<Nav>` never renders a portal link. **Keep the existing Story 01/02/03 regression assertions intact.**

---

## Migration / Rollback

- **Forward:** `docker compose -f infra/docker-compose.yml exec backend alembic upgrade head` after deploy. Three new tables; the only change to an existing table is the addition of the `Customer.portal_users` and `Ticket.feedback` ORM relationships, which are **not** schema changes.
- **Rollback:** `alembic downgrade -1` drops `ticket_feedback`, `portal_sessions`, and `portal_users`. **This destroys all portal logins, sessions, and feedback irrecoverably** — every customer with a portal account would need to sign up again. Customers, tickets, and all prior-story data are untouched. No named enum types are created by this migration, so — unlike `0001`–`0004` — there is nothing to drop on that front (state this explicitly in the migration's own docstring, per Backend Task 3).
- **Half-applied state:** Alembic uses transactional DDL on Postgres, so a failed `upgrade` rolls back whole. A successful migration with a rolled-back application image is harmless (the new tables sit unused). The reverse — new image, un-migrated database — fails loudly on the first portal request with an `UndefinedTable` error, so **run the migration before switching traffic**, matching the existing guidance in Story 03's Migration/Rollback section.
- **Verification is mandatory.** Run `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` against the compose Postgres before considering this story done.

---

## Verification Steps

1. **Backend builds:** from `backend/`, with the venv active (`.venv\Scripts\activate` on Windows), `pip install -r requirements-dev.txt` (which now pulls in `bcrypt` transitively via `requirements.txt`) then `alembic upgrade head` against the compose Postgres — `CRM_DATABASE_URL=postgresql+psycopg://crm:crm@localhost:5432/crm`.
2. **Migration round-trips:** from `backend/`, `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` — all three succeed.
3. **Backend tests:** from `backend/`, `pytest` — every new test file passes **and** every prior story's suite stays green.
4. **Backend runs:** from `backend/`, `uvicorn app.main:app --reload`. Confirm `http://localhost:8000/docs` lists the `portal` tag with all nine routes.
5. **Manual API smoke:** create a customer and an `email`-kind contact via the existing staff endpoints, then `POST /api/portal/auth/signup` with that email (expect 201 + a usable token), `POST /api/portal/tickets` with the returned bearer token, `GET /api/portal/tickets` (expect the one ticket), move the ticket to `resolved` via the **staff** `POST /api/tickets/{id}/status` route, then `POST /api/portal/tickets/{id}/feedback` (expect 200), then re-submit with a different rating (expect the row to update, not duplicate) and finally attempt `GET /api/portal/tickets/{another-customer's-ticket-id}` (expect 404). On Windows, pass JSON bodies with `--data-binary @file.json` written as UTF-8; `curl -d` with inline non-ASCII is mangled by Git Bash.
6. **Frontend tests:** from `frontend/`, `npm test` (`vitest run`) — all suites pass.
7. **Frontend builds:** from `frontend/`, `npm run build` (`tsc -b && vite build`) — no type errors under `strict`.
8. **Frontend runs:** from `frontend/`, `npm install && npm run dev`. Open `http://localhost:5173/portal/signup`, sign up with an email matching a seeded customer contact, submit a ticket, confirm it appears at `/portal/tickets`, move it to resolved via the agent app, reload the portal detail page and confirm the feedback form appears and saves.
9. **Regression:** the agent app's `/dashboard`, `/customers`, `/tickets` (including Workflow/Messages/Notes/History tabs) are unchanged; the agent `<Nav>` shows no portal link.
10. **Compose:** from the repo root, `docker compose -f infra/docker-compose.yml up --build` then `docker compose -f infra/docker-compose.yml exec backend alembic upgrade head` — `db`, `backend`, and `frontend` all reach a running state and `http://localhost:5173/portal/signup` loads through the Vite proxy.

---

## Done Criteria

- [ ] A customer with an existing email contact on an active `Customer` can sign up for a portal login and log in; login/signup with an unmatched or archived-customer email fails identically (403), avoiding enumeration.
- [ ] A `Customer` account can hold multiple independent `PortalUser` logins, all scoped to the same customer's data.
- [ ] A logged-in customer can submit a ticket against their own account without being able to set `customer_id`, `assignee_id`, or `priority`.
- [ ] A logged-in customer can list and view only their own tickets; requesting another customer's ticket id returns 404, not 403 or a leaked object.
- [ ] The portal ticket timeline shows only `created` and `status_changed` events — no internal assignment, escalation, category, or priority detail leaks through.
- [ ] Feedback (1–5 rating + optional comment) can be submitted once a ticket is `resolved` or `closed`, is rejected with 409 before then, and resubmission updates the existing row rather than creating a duplicate.
- [ ] If a customer's account is archived after their portal login was created, every subsequent portal request is refused (403) even with a still-valid, unexpired session token.
- [ ] Migration `0005_customer_portal` applies, rolls back, and re-applies cleanly.
- [ ] `/portal/*` is reachable and fully functional without ever rendering the internal agent `<Nav>`, and the agent app's existing routes/behaviour are unchanged.
- [ ] Backend and frontend tests listed in the Test Plan all pass.
- [ ] No regressions in any prior story's behaviour (health, customers, tickets, channels, dashboard).

**STOP HERE. Report to the user and wait for confirmation before proceeding to Story 07.**
