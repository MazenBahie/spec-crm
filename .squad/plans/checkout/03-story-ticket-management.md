# Story 03 — Ticket Management

---

## Prerequisites

- **Story 01 completed:** [Project init and structure](01-story-project-init-and-structure.md) — FastAPI backend, React + Vite frontend, Postgres via `infra/docker-compose.yml`.
- **Story 02 completed:** [Customer Management](02-story-customer-management.md) — this story builds directly on it. It reuses the layering (`models/` → `schemas/` → `services/` → `api/routes/`), the `get_db` dependency, the `NotFound`/`Conflict` → 404/409 handlers, the Alembic setup, the SQLite-backed pytest fixtures, and the frontend router + `ui.tsx` atoms. **Do not re-invent any of these** — mirror them.
- **Alembic head is `0001`** (`backend/alembic/versions/0001_customer_management.py`, line 23). The new migration must set `down_revision = '0001'`.
- No coordination needed on `infra/postgres/init.sql` — it is intentionally empty and schema lives in Alembic. **Do not add tables there.**
- Attachments folder for this intake (`.squad/stories/checkout/ticket-management/attachments/`) is **empty**. There are no design assets to honour; UI follows the Story 02 inline-style conventions.

---

## Story Goal

Deliver a **Ticket Management** module so support operators can raise tickets against customers, route them, and see everything that ever happened to them.

User-visible outcomes:

1. **Create and track tickets** against a customer — subject, description, human-readable reference, timestamps.
2. **Categories and priorities** — tickets carry a priority and an admin-maintained category.
3. **Assign tickets to agents** — a ticket can be assigned to, or unassigned from, an active agent.
4. **Status and escalation** — a ticket moves through a guarded status lifecycle and can be escalated, with invalid moves rejected rather than silently accepted.
5. **Ticket history** — every mutation appends an immutable event row, readable as a timeline.

**Not in scope:** authentication/authorisation (the `agents` table is a standalone directory, **not** a login system — see the uncertainty note in Edge Cases); SLA timers, cron jobs, or time-based auto-escalation; email/notification delivery; ticket merging or splitting; customer-facing portal; full-text search; per-agent permissions; reporting dashboards. Attachments on tickets are **out of scope** — Story 02's attachment endpoints remain customer/note-scoped.

---

## Context — Read These Files First

1. `backend/app/models/customer.py` — read the whole file (186 lines). Copy its conventions exactly: the `_pk()` helper (line 39), the module-level status tuples and named `Enum` objects (lines 30–36), `DateTime(timezone=True)` with `server_default=func.now()`, and the `ForeignKey(..., ondelete="CASCADE")` + `passive_deletes=True` pairing. Note the `Customer.contacts/interactions/notes/attachments` relationship block at **lines 63–77** — the new `tickets` relationship goes at the end of it.
2. `backend/app/models/customer.py` **lines 118–139** (`Interaction`) — the closest precedent for the new `TicketEvent`. Note `author: Mapped[str | None] = mapped_column(String(255))` at **line 134**: free-text actor, deliberately not an FK, because auth does not exist yet. `TicketEvent.actor` follows the same choice.
3. `backend/app/models/customer.py` **lines 84–99** (`ContactDetail.__table_args__`) — the partial-unique-index pattern, including the **`sqlite_where` mirror of `postgresql_where`**. Any conditional index you add must set both, or the SQLite test suite will enforce the wrong constraint.
4. `backend/app/models/__init__.py` — read all 19 lines. Every new model **must** be re-exported here or Alembic autogenerate will not see the tables.
5. `backend/app/schemas/customer.py` — read the whole file (167 lines). Reuse `Page` (line 20), `NonEmptyStr` (line 15), and the `Literal` type aliases (lines 11–13). Mirror the Base/Create/Update/Read quartet layout and `model_config = ConfigDict(from_attributes=True)` on `Read` variants.
6. `backend/app/services/customers.py` — read **lines 1–40** (module docstring: "no FastAPI imports", "flush ... but never commit", last-write-wins) and these helpers verbatim:
   - **lines 145–147** `_require_active` — raises `Conflict("customer is archived")`. Ticket creation reuses this exact guard.
   - **lines 164–184** `_assert_primary_free` — the pattern for a service-layer pre-check that mirrors a DB constraint. Status-transition and assignment validation follow the same shape.
   - **lines 44–74** `list_customers` — the `(items, total)` tuple + `or_`/`func.lower` search + limit/offset contract to copy for `list_tickets`.
7. `backend/app/services/errors.py` — all 19 lines. `NotFound` (line 10) and `Conflict` (line 14) already exist. **Do not add a new exception type**; invalid transitions and assignment failures are `Conflict`.
8. `backend/app/api/routes/customers.py` — read **lines 39–44** (`router`, `DbDep`, `StorageDep`, no per-route try/except) and **lines 62–107** (the customer CRUD block) for the response-model + `status.HTTP_201_CREATED` + `Response(status_code=204)` conventions. Note `status_filter: Annotated[CustomerStatus | None, Query(alias="status")]` at **line 66** — the alias trick that avoids shadowing the imported `status` module. You will need it again.
9. `backend/app/main.py` — all 38 lines. The new router is registered beside the existing two at **line 19**, and the error handlers at **lines 33–35** already cover 404/409, so no handler changes are needed.
10. `backend/app/db/session.py` **lines 30–43** — `get_db()`: commits on success, rolls back on exception. The service layer must therefore `flush()`, never `commit()`.
11. `backend/tests/conftest.py` — read the whole file (122 lines). Reuse the `engine`/`session_factory`/`app`/`client` fixture chain (**lines 45–100**), the `customer` fixture (**lines 103–110**) as the parent for tickets, the FK pragma listener (**lines 29–36**, without which cascade tests silently pass), and `missing_uuid()` (**lines 121–122**). New fixtures are added to this same file.
12. `backend/tests/test_interactions.py` — read the whole file. The closest template for the new ticket tests: local `_interaction(...)` helper, ordering assertions, and the 409-when-archived test.
13. `frontend/src/App.tsx` — all 72 lines. `NAV` at **lines 9–12** and the `<Routes>` block at **lines 54–69** are the two places to extend.
14. `frontend/src/api/client.ts` — all 68 lines. `request<T>()` (**line 33**) already unwraps FastAPI's `detail` and returns `undefined` on 204; `buildQuery` is at **line 47**. Reuse both — **do not** call `fetch` directly in new code.
15. `frontend/src/api/customers.ts` — read **lines 19–57** for the section-comment + one-function-per-endpoint style the new `tickets.ts` must match.
16. `frontend/src/pages/CustomerDetailPage.tsx` — read **lines 12–13** (`TABS` const + derived `Tab` type) and **lines 130–197** (the `role="tablist"` markup and the `tab === "…" && <Panel …/>` dispatch). A **Tickets** tab is added here.
17. `frontend/src/components/customer/InteractionsPanel.tsx` — read the whole file (261 lines). The direct template for the ticket timeline and the add-form: `load` via `useCallback`, `busy` flag, `ErrorBanner`, `toDateTimeLocal` for `datetime-local` inputs, and `new Date(x).toISOString()` on submit.
18. `frontend/src/components/ui.tsx` — all 113 lines. Use `styles`, `tokens`, `ErrorBanner`, `Loading`, `StatusBadge`, `formatDateTime`, `toDateTimeLocal`. **Do not introduce a CSS framework.**
19. `frontend/src/components/customer/__tests__/ContactDetailsPanel.test.tsx` — the mocking convention for new component tests: `vi.stubGlobal("fetch", …)` returning real `Response` objects and recording `{method, url, body}` for assertions.

Grep lines to run before editing:

- `grep -rn "include_router" backend/app` — confirms the two existing registrations in `backend/app/main.py`.
- `grep -rn "get_db\|get_sessionmaker" backend/app` — confirms the sync `Session` dependency (there is **no** async session in this project).
- `grep -rn "sqlite_where" backend/app` — the single existing use, in `models/customer.py`.
- `grep -rn "_require_active\|is_archived" backend/app` — the archived-customer guard and the `Customer.is_archived` property (`models/customer.py` lines 79–81).
- `grep -rn "CONTACT_KINDS\|INTERACTION_KINDS" frontend/src` — how enum option lists are exported from `types/customer.ts` and consumed by `<select>` panels.

---

## Product rules (from story)

- **Current behaviour:** The system holds customers with contacts, interactions, notes, and attachments. There is no concept of a support request, no queue, no assignment, and no per-record audit trail.
- **New behaviour:** An operator raises a **ticket** against a customer. The ticket carries a **category** and a **priority**, sits in a **status**, and may be **assigned** to an **agent**. Status changes follow a permitted-transition map — an illegal move is rejected with **409**, not silently applied. A ticket can be **escalated**, which raises its escalation level and stamps `escalated_at`. Every one of these mutations appends an immutable **ticket event**, so the full history is reconstructable and nothing is overwritten without a trace.

---

## Backend Tasks

### 1 — Dependencies

**File:** `backend/requirements.txt`

`grep` the file first: `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `sqlalchemy`, `psycopg[binary]`, `alembic`, and `python-multipart` are **already declared**. This story needs **no new runtime dependency** — state that in the PR description rather than adding anything.

`backend/pyproject.toml` and `backend/requirements-dev.txt` likewise need **no changes**.

---

### 2 — Data model

**Create file:** `backend/app/models/ticket.py`

Follow `backend/app/models/customer.py` exactly: `from __future__ import annotations`, the same import block, a local copy of the `_pk()` idiom (import it from `app.models.customer` rather than duplicating — it is a module-level function at line 39), module-level value tuples, and **named** `Enum` objects.

Declare the value tuples and enums at module level so both the schemas and the frontend type lists stay in sync:

```python
TICKET_STATUSES = (
    "open",
    "triaged",
    "in_progress",
    "waiting_customer",
    "resolved",
    "closed",
)
TICKET_PRIORITIES = ("low", "normal", "high", "urgent")
TICKET_EVENT_TYPES = (
    "created",
    "status_changed",
    "priority_changed",
    "category_changed",
    "assigned",
    "unassigned",
    "escalated",
    "commented",
)

ticket_status_enum = Enum(*TICKET_STATUSES, name="ticket_status")
ticket_priority_enum = Enum(*TICKET_PRIORITIES, name="ticket_priority")
ticket_event_type_enum = Enum(*TICKET_EVENT_TYPES, name="ticket_event_type")
```

Four models:

- **`Agent`** — `__tablename__ = "agents"`. `id` (`_pk()`), `display_name: str` (`String(255)`, required, indexed), `email: str | None` (`String(320)`, **unique** where present), `is_active: bool` (required, `default=True`, `server_default=text("true")`), `created_at`. A flat directory of assignable people. **No password, no session, no roles** — see the uncertainty note in Edge Cases.
- **`TicketCategory`** — `__tablename__ = "ticket_categories"`. `id`, `name: str` (`String(120)`, required, **unique**), `description: str | None` (`Text`), `default_priority: str` (`ticket_priority_enum`, required, `server_default="normal"`), `is_active: bool` (default `True`), `created_at`.
- **`Ticket`** — `__tablename__ = "tickets"`.
  - `id`, `reference: str` (`String(24)`, required, **unique**) — see task 4 for how it is generated.
  - `customer_id` → `ForeignKey("customers.id", ondelete="CASCADE")`, **required**, indexed. A ticket always belongs to a customer.
  - `category_id` → `ForeignKey("ticket_categories.id", ondelete="SET NULL")`, **nullable**, indexed.
  - `assignee_id` → `ForeignKey("agents.id", ondelete="SET NULL")`, **nullable**, indexed.
  - `subject: str` (`String(255)`, required), `description: str` (`Text`, required, `server_default=""`).
  - `status: str` (`ticket_status_enum`, required, `server_default="open"`).
  - `priority: str` (`ticket_priority_enum`, required, `server_default="normal"`).
  - `escalation_level: int` (`Integer`, required, `default=0`, `server_default=text("0")`).
  - `escalated_at`, `due_at`, `resolved_at`, `closed_at` — all `DateTime(timezone=True)`, **nullable**.
  - `created_at`, `updated_at` — `server_default=func.now()`, `updated_at` also `onupdate=func.now()`.
  - `__table_args__`: a composite index for the queue view — `Index("ix_tickets_status_priority", "status", "priority")` — and one for the customer timeline — `Index("ix_tickets_customer_created", "customer_id", text("created_at DESC"))`, mirroring `ix_interactions_customer_occurred` at `models/customer.py` line 121.
  - Relationships: `customer`, `category`, `assignee`, and `events` (`cascade="all, delete-orphan"`, `passive_deletes=True`, `order_by="TicketEvent.created_at"`).
  - Two convenience properties, mirroring `Customer.is_archived` (lines 79–81):

    ```python
    @property
    def is_terminal(self) -> bool:
        return self.status in ("resolved", "closed")

    @property
    def is_overdue(self) -> bool:
        """True when a still-open ticket has passed its due date.

        Computed on read only. There is no background job that acts on this —
        time-based auto-escalation is out of scope for this story.
        """
    ```

- **`TicketEvent`** — `__tablename__ = "ticket_events"`. **Append-only.** `id`, `ticket_id` → `ForeignKey("tickets.id", ondelete="CASCADE")` required + indexed, `event_type: str` (`ticket_event_type_enum`, required), `field: str | None` (`String(64)`), `old_value: str | None` (`Text`), `new_value: str | None` (`Text`), `comment: str | None` (`Text`), `actor: str | None` (`String(255)`) — **free text, deliberately not an FK**, exactly as `Interaction.author` at line 134 — and `created_at`. Index `("ticket_id", text("created_at DESC"))`.

**File:** `backend/app/models/customer.py`

Add the reverse relationship at the end of the existing block, immediately **after line 77** (`attachments`) and **before the blank line preceding the `is_archived` property at line 79**:

```python
    tickets: Mapped[list[Ticket]] = relationship(
        back_populates="customer", cascade="all, delete-orphan", passive_deletes=True
    )
```

Import `Ticket` under `TYPE_CHECKING` to avoid a circular import at runtime; the string form in `Mapped[list[Ticket]]` resolves lazily because the module already has `from __future__ import annotations` (line 12).

**File:** `backend/app/models/__init__.py`

Extend the import and `__all__` (currently lines 3–19) with `Agent`, `Ticket`, `TicketCategory`, `TicketEvent`. **Keep the list alphabetised** as it is today.

---

### 3 — Migration

**Create file:** `backend/alembic/versions/0002_ticket_management.py`

Generate it, then hand-check:

```bash
cd backend
CRM_DATABASE_URL="postgresql+psycopg://crm:crm@localhost:5432/crm" \
  alembic revision --autogenerate -m "ticket management" --rev-id 0002
```

Required hand-edits — autogenerate gets all three wrong:

1. Confirm `down_revision: Union[str, None] = '0001'`.
2. **Drop the named enum types in `downgrade()`.** `op.drop_table` does **not** remove Postgres enum types, so a second `upgrade` fails with *"type already exists"*. Copy the loop already present at the end of `backend/alembic/versions/0001_customer_management.py` (**lines 116–120**), substituting the new names:

   ```python
   bind = op.get_bind()
   for enum_name in ('ticket_status', 'ticket_priority', 'ticket_event_type'):
       sa.Enum(name=enum_name).drop(bind, checkfirst=True)
   ```

3. Write a docstring in the same style as `0001` (**lines 1–14**), naming the four tables and stating that `downgrade` destroys all ticket history irrecoverably.

Verify the round-trip against the compose Postgres before moving on:

```bash
cd backend
alembic upgrade head && alembic downgrade -1 && alembic upgrade head
```

---

### 4 — Ticket reference generation

**Create file:** `backend/app/services/tickets.py` (the reference helper lives here, alongside the rest of the service layer)

```python
def build_reference(ticket_id: uuid.UUID) -> str:
    """Human-quotable ticket reference, e.g. "TCK-3F9A21C4".

    Derived from the ticket's own UUID rather than a counter: identical on
    Postgres and on the SQLite test database, and safe under concurrent
    inserts with no locking. Uniqueness is backed by the unique index on
    `tickets.reference`. Strictly sequential numbering would need a Postgres
    SEQUENCE (and a SQLite fallback) — deliberately deferred.
    """
    return f"TCK-{ticket_id.hex[:8].upper()}"
```

Call it in `create_ticket` after the `uuid4()` id is assigned. **Do not** attempt `SELECT max(reference) + 1` — it races.

---

### 5 — Pydantic schemas

**Create file:** `backend/app/schemas/ticket.py`

Import and reuse `Page` and `NonEmptyStr` from `app.schemas.customer` (lines 20 and 15) — **do not redefine them**. Add `Literal` aliases mirroring `backend/app/schemas/customer.py` lines 11–13:

```python
TicketStatus = Literal[
    "open", "triaged", "in_progress", "waiting_customer", "resolved", "closed"
]
TicketPriority = Literal["low", "normal", "high", "urgent"]
TicketEventType = Literal[
    "created", "status_changed", "priority_changed", "category_changed",
    "assigned", "unassigned", "escalated", "commented",
]
```

Quartets, each `Read` variant carrying `model_config = ConfigDict(from_attributes=True)`:

- `AgentBase/Create/Update/Read` — `display_name: NonEmptyStr`, `email: str | None`, `is_active: bool = True`.
- `TicketCategoryBase/Create/Update/Read` — `name: NonEmptyStr`, `description: str | None`, `default_priority: TicketPriority = "normal"`, `is_active: bool = True`.
- `TicketCreate` — `customer_id: uuid.UUID`, `subject: NonEmptyStr`, `description: str = ""`, `category_id: uuid.UUID | None = None`, `priority: TicketPriority | None = None` (**`None` means "inherit the category's `default_priority`"** — see task 6), `assignee_id: uuid.UUID | None = None`, `due_at: datetime | None = None`.
- `TicketUpdate` — every field optional: `subject`, `description`, `category_id`, `priority`, `due_at`. **`status` and `assignee_id` are deliberately absent** — they are only mutable through the dedicated transition/assignment endpoints so that history is always recorded. Document that in a docstring.
- `TicketRead` — all columns plus the computed `is_overdue: bool`.
- `TicketDetailRead(TicketRead)` — adds `customer: CustomerRead`, `category: TicketCategoryRead | None`, `assignee: AgentRead | None`. Import `CustomerRead` from `app.schemas.customer` (line 52).
- `TicketEventRead` — all `TicketEvent` columns. **There is no `TicketEventCreate`/`Update`** for direct writes; the only client-authored event is a comment, via `TicketCommentCreate` (`comment: NonEmptyStr`, `actor: str | None`).
- Action payloads: `TicketStatusChange` (`status: TicketStatus`, `comment: str | None`, `actor: str | None`), `TicketAssignment` (`assignee_id: uuid.UUID | None`, `actor: str | None`), `TicketEscalation` (`comment: str | None`, `actor: str | None`, `raise_priority: bool = True`).

End the module with `TicketDetailRead.model_rebuild()`, matching `backend/app/schemas/customer.py` line 167.

---

### 6 — Service layer

**File:** `backend/app/services/tickets.py` (created in task 4)

Same contract as `backend/app/services/customers.py`: pure functions taking `Session` as the first positional arg, **no FastAPI imports**, `flush()` + `refresh()` but **never `commit()`**, `NotFound`/`Conflict` for expected failures. Copy the module docstring shape from `services/customers.py` lines 1–10, including the last-write-wins note.

#### 6a — The status machine

Declare the permitted moves as data, not branching:

```python
ALLOWED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "open": ("triaged", "in_progress", "closed"),
    "triaged": ("in_progress", "open", "closed"),
    "in_progress": ("waiting_customer", "resolved", "triaged", "closed"),
    "waiting_customer": ("in_progress", "resolved", "closed"),
    "resolved": ("closed", "in_progress"),   # reopen
    "closed": ("open",),                     # reopen
}
```

`change_status(db, ticket_id, payload)`:

- Raise `Conflict` when the target is not in `ALLOWED_TRANSITIONS[current]`, with the message `f"cannot move ticket from {current} to {target}"`. Mirror the pre-check style of `_assert_primary_free` (`services/customers.py` lines 164–184).
- A no-op transition (target == current) is **idempotent**: return the ticket unchanged and append **no** event.
- Stamp `resolved_at` on entering `resolved`, `closed_at` on entering `closed`, and **clear both** when reopening to a non-terminal status.
- Append a `status_changed` event with `field="status"`, `old_value`, `new_value`, plus the caller's `comment`/`actor`.

#### 6b — Functions to implement

Agents and categories (thin CRUD, needed to populate the ticket form):

- `list_agents(db, *, active_only: bool = False) -> list[Agent]`, `get_agent`, `create_agent`, `update_agent`, `deactivate_agent`.
- `list_categories(db, *, active_only: bool = False) -> list[TicketCategory]`, `get_category`, `create_category`, `update_category`, `delete_category`.
  - `create_category`/`update_category` raise `Conflict` on a duplicate `name` (pre-check with a `func.lower` comparison before the unique index fires).
  - `delete_category` raises `Conflict("category is in use by N ticket(s)")` when any ticket references it; deactivation via `is_active=False` is the supported way to retire one.

Tickets:

- `list_tickets(db, *, q=None, status=None, priority=None, customer_id=None, assignee_id=None, category_id=None, unassigned=None, limit=20, offset=0) -> tuple[list[Ticket], int]` — mirror `list_customers` (lines 44–74) exactly: build a `filters` list, compute `total` with `select(func.count()).select_from(Ticket).where(*filters)`, then the page. `q` matches `reference`, `subject`, or `description` case-insensitively via `or_` + `func.lower`. `unassigned=True` adds `Ticket.assignee_id.is_(None)`. Default order: `priority` **urgent → low**, then `created_at DESC`. Postgres orders enum columns by declaration order, but SQLite stores them as `VARCHAR` and would sort alphabetically — so **order by an explicit `case()` expression over `TICKET_PRIORITIES`**, not by the raw column, or the test suite and production will disagree.
- `get_ticket(db, ticket_id, *, with_relations: bool = False)` — `selectinload` `customer`, `category`, `assignee` when requested, matching `get_customer(..., with_contacts=True)` at `services/customers.py` lines 76–86.
- `create_ticket(db, payload)`:
  1. `customer = get_customer(db, payload.customer_id)` then `_require_active(customer)` — **import and reuse the existing helper** from `services/customers.py` (line 145). A ticket cannot be raised against an archived customer.
  2. Validate `category_id` (must exist; `Conflict` if `is_active` is `False`) and `assignee_id` (must exist; `Conflict` if inactive).
  3. Resolve priority: `payload.priority` when given, else the category's `default_priority`, else `"normal"`.
  4. Assign `id = uuid.uuid4()` explicitly and set `reference = build_reference(id)`.
  5. Append a `created` event, and an `assigned` event too when the ticket is born assigned.
- `update_ticket(db, ticket_id, payload)` — partial update of the editable fields only. Append a `priority_changed` and/or `category_changed` event when those actually change (compare before assigning; **do not** emit an event when the value is identical). Allowed on terminal tickets; note the last-write-wins comment.
- `change_status` — task 6a.
- `assign_ticket(db, ticket_id, payload)` — `assignee_id=None` unassigns. `Conflict` when the ticket `is_terminal`, or when the target agent is inactive. Appends `assigned` or `unassigned`. Re-assigning to the same agent is a no-op with no event.
- `escalate_ticket(db, ticket_id, payload)` — `Conflict` when `is_terminal` (`"cannot escalate a resolved or closed ticket"`) or when `escalation_level` already equals `MAX_ESCALATION_LEVEL = 3` (`"ticket is already at the maximum escalation level"`). Otherwise increment `escalation_level`, set `escalated_at = now()`, and when `raise_priority` is true bump one step along `TICKET_PRIORITIES` (capped at `urgent`). Append an `escalated` event recording the old and new level; append a separate `priority_changed` event if the priority moved.
- `delete_ticket(db, ticket_id)` — hard delete; events cascade. **No attachment cleanup is needed** — tickets hold no files in this story.
- `list_events(db, ticket_id, *, limit=200, offset=0) -> tuple[list[TicketEvent], int]` — newest first.
- `add_comment(db, ticket_id, payload) -> TicketEvent` — appends a `commented` event. The **only** way a client writes an event directly.

#### 6c — The event recorder

One private helper, used by every mutator so the shape never drifts:

```python
def _record(
    db: Session,
    ticket: Ticket,
    event_type: str,
    *,
    field: str | None = None,
    old_value: object = None,
    new_value: object = None,
    comment: str | None = None,
    actor: str | None = None,
) -> TicketEvent:
    """Append one immutable history row. Never updates an existing event."""
```

Stringify `old_value`/`new_value` with `None if v is None else str(v)` so UUIDs and ints store cleanly.

---

### 7 — API routes

**Create file:** `backend/app/api/routes/tickets.py`

Mirror `backend/app/api/routes/customers.py` lines 39–44: one `router = APIRouter(tags=["tickets"])`, a module-level `DbDep = Annotated[Session, Depends(get_db)]`, and **no try/except in route bodies** — the handlers in `main.py` (lines 33–35) already map `NotFound` → 404 and `Conflict` → 409.

| Method | Path | Notes |
|---|---|---|
| `GET` | `/tickets` | `Page[TicketRead]`. Query: `q`, `status`, `priority`, `customer_id`, `assignee_id`, `category_id`, `unassigned`, `limit` (default 20, `ge=1, le=100`), `offset` (`ge=0`). Use the `Query(alias="status")` trick from `routes/customers.py` line 66 for `status`/`priority` so they do not shadow the imported `status` module. |
| `POST` | `/tickets` | 201, `TicketRead`. |
| `GET` | `/tickets/{ticket_id}` | `TicketDetailRead` (customer, category, assignee eagerly loaded). |
| `PATCH` | `/tickets/{ticket_id}` | `TicketRead`. Editable fields only. |
| `DELETE` | `/tickets/{ticket_id}` | 204 via `Response(status_code=status.HTTP_204_NO_CONTENT)`. |
| `POST` | `/tickets/{ticket_id}/status` | `TicketRead`. Body `TicketStatusChange`. 409 on a forbidden move. |
| `POST` | `/tickets/{ticket_id}/assignment` | `TicketRead`. Body `TicketAssignment`; `assignee_id: null` unassigns. |
| `POST` | `/tickets/{ticket_id}/escalate` | `TicketRead`. Body `TicketEscalation`. |
| `GET` | `/tickets/{ticket_id}/events` | `Page[TicketEventRead]`, newest first. |
| `POST` | `/tickets/{ticket_id}/events` | 201, `TicketEventRead`. Body `TicketCommentCreate`. **No `PATCH`/`DELETE` on events** — history is immutable. |
| `GET` | `/customers/{customer_id}/tickets` | `Page[TicketRead]` scoped to one customer; 404 when the customer does not exist. |
| `GET`/`POST` | `/ticket-categories` | list (`active_only` query flag) / create 201. |
| `PATCH`/`DELETE` | `/ticket-categories/{category_id}` | update / delete (409 when in use). |
| `GET`/`POST` | `/agents` | list (`active_only` flag) / create 201. |
| `PATCH`/`DELETE` | `/agents/{agent_id}` | update / **deactivate** (`is_active=False`, returns the updated `AgentRead` — agents are never hard-deleted, so assignment history stays readable). |

**File:** `backend/app/main.py`

Add the import to line 5 and one registration immediately after line 19:

```python
app.include_router(tickets.router, prefix=settings.api_prefix)
```

**No other change to `main.py`.** The 404/409 handlers already cover everything this story raises.

---

## Frontend Tasks

### 1 — Types

**Create file:** `frontend/src/types/ticket.ts`

Mirror `frontend/src/types/customer.ts`: `type` aliases for the three enums, exported `const` arrays for `<select>` population (`TICKET_STATUSES`, `TICKET_PRIORITIES`) following the `CONTACT_KINDS` precedent at line 7, and interfaces `Agent`, `TicketCategory`, `Ticket`, `TicketDetail`, `TicketEvent`, plus the input shapes. Re-export nothing from `customer.ts` except by explicit `import type` (`Page<T>` at line 16, `Customer` at line 21).

### 2 — API client

**Create file:** `frontend/src/api/tickets.ts`

One function per endpoint, using `request<T>` and `buildQuery` from `./client` (lines 33 and 47). Match the section-comment layout of `frontend/src/api/customers.ts`. Cover: `listTickets`, `getTicket`, `createTicket`, `updateTicket`, `deleteTicket`, `changeTicketStatus`, `assignTicket`, `escalateTicket`, `listTicketEvents`, `addTicketComment`, `listCustomerTickets`, `listCategories`, `createCategory`, `updateCategory`, `deleteCategory`, `listAgents`, `createAgent`, `updateAgent`, `deactivateAgent`.

**No change** to `frontend/src/api/client.ts` — `request` already handles 204 and FastAPI's `detail` envelope.

### 3 — Pages

- **Create file:** `frontend/src/pages/TicketsListPage.tsx` — the queue. Debounced search (copy the 300 ms `useEffect` + `requestId` guard from `frontend/src/pages/CustomersListPage.tsx` lines 24–60 — it prevents a slow early response from overwriting a newer one), `<select>` filters for status / priority / assignee plus an "Unassigned only" checkbox, a table (reference, subject, customer, category, priority, status, assignee, updated), `Previous`/`Next` pagination, and a **New ticket** link. Show an `is_overdue` marker on the row.
- **Create file:** `frontend/src/pages/TicketDetailPage.tsx` — header with reference, subject, `StatusBadge`, priority, escalation level, and a link to the parent customer. Tabs `["Overview", "Workflow", "History"]` built with the `TABS`/`role="tablist"` pattern from `frontend/src/pages/CustomerDetailPage.tsx` lines 12–13 and 130–145. Delete uses `window.confirm`, matching `CustomerDetailPage.tsx` lines 57–60.
- **Create file:** `frontend/src/pages/TicketEditPage.tsx` — create/edit form, following `frontend/src/pages/CustomerEditPage.tsx` (id present ⇒ edit mode). Category and assignee are `<select>`s fed by `listCategories({activeOnly: true})` and `listAgents({activeOnly: true})`. On create, `customer_id` comes from a `?customerId=` search param when present (so the customer page can deep-link), otherwise from a customer picker.
- **Create file:** `frontend/src/pages/TicketSetupPage.tsx` — one lightweight admin screen at `/tickets/setup` for creating/renaming/deactivating **categories** and **agents**. Two simple tables with inline add rows; no separate admin area.

### 4 — Components

**Create file:** `frontend/src/components/ticket/TicketWorkflowPanel.tsx` — status `<select>` restricted to the moves the server permits (keep a client copy of `ALLOWED_TRANSITIONS` so illegal options are never offered, and **still** surface a server 409 in `ErrorBanner` if one slips through — the same belt-and-braces the contacts panel uses for primary contacts), assignee `<select>` with an "— Unassigned —" option, an **Escalate** button disabled when the ticket is terminal or already at level 3, and an optional comment box attached to each action.

**Create file:** `frontend/src/components/ticket/TicketHistoryPanel.tsx` — reverse-chronological timeline of `TicketEvent`s. Render each type as a sentence ("status changed from **open** to **triaged**", "escalated to level 2", "assigned to Dana"), with `formatDateTime(event.created_at)` and the actor. Include the comment composer (`POST /tickets/{id}/events`). Copy the list/`useCallback`/`busy` structure from `frontend/src/components/customer/InteractionsPanel.tsx` — but **no edit or delete controls**, because events are immutable.

**Create file:** `frontend/src/components/customer/CustomerTicketsPanel.tsx` — compact ticket list for one customer (`listCustomerTickets`), plus a **New ticket** link pre-filled with `?customerId=`. Lives under `components/customer/` because it is mounted by the customer page.

### 5 — Routing and navigation

**File:** `frontend/src/App.tsx`

- Add `{ to: "/tickets", label: "Tickets" }` to `NAV` (lines 9–12). The existing `active` logic at lines 34–35 already handles prefix matching, so no change there.
- Add to the `<Routes>` block (lines 54–69), **before** the `path="*"` fallback and with `/tickets/setup` and `/tickets/new` **ahead of** `/tickets/:id` so the literal segments win:

  ```tsx
  <Route path="/tickets" element={<TicketsListPage />} />
  <Route path="/tickets/new" element={<TicketEditPage />} />
  <Route path="/tickets/setup" element={<TicketSetupPage />} />
  <Route path="/tickets/:id" element={<TicketDetailPage />} />
  <Route path="/tickets/:id/edit" element={<TicketEditPage />} />
  ```

**File:** `frontend/src/pages/CustomerDetailPage.tsx`

- Extend `TABS` at line 12 to `["Overview", "Contacts", "Interactions", "Tickets", "Notes & Attachments"]`.
- Add the dispatch line beside the existing ones (lines 184–197): `{tab === "Tickets" && <CustomerTicketsPanel customerId={id} archived={archived} />}`.
- When `archived` is true the panel hides its **New ticket** link, because the backend returns 409 for that case.

---

## Edge Cases & Failure Modes

- **Ticket for an archived customer** → **409** `"customer is archived"`, by reusing `_require_active` from `backend/app/services/customers.py` (**lines 145–147**) inside `create_ticket`. Existing tickets on a customer that is archived later stay readable and editable.
- **Illegal status transition** (e.g. `open` → `resolved`) → **409** from `change_status`, driven by the `ALLOWED_TRANSITIONS` map. The UI never offers the option, but the API is the enforcement point.
- **Same-status transition** → idempotent 200 and **no** history row, so retries and double-clicks do not pollute the timeline. Same rule for re-assigning to the current assignee and for a `PATCH` that changes nothing.
- **Escalating a resolved/closed ticket** → **409**. **Escalating past level 3** (`MAX_ESCALATION_LEVEL`) → **409**. Escalating an `urgent` ticket with `raise_priority=true` raises the level but leaves priority at `urgent` and emits **no** `priority_changed` event.
- **Assigning to an inactive agent** → **409**. Deactivating an agent **does not** unassign their open tickets: the assignment and its history stay intact, and the UI shows the name with an "(inactive)" suffix. This is why `DELETE /agents/{id}` deactivates instead of deleting.
- **Deleting a category that is in use** → **409** with the referencing count. `ON DELETE SET NULL` on `tickets.category_id` is the second line of defence if a row is removed out of band; `TicketRead.category_id` then reads `null` rather than dangling.
- **Deleting a customer cascades tickets and their events.** Verified by the FK pragma listener in `backend/tests/conftest.py` (**lines 29–36**) — without `PRAGMA foreign_keys=ON` the SQLite cascade test would pass vacuously.
- **Priority ordering differs by dialect.** Postgres sorts enum columns by declaration order; SQLite stores them as `VARCHAR` and sorts alphabetically (`high` < `low` < `normal` < `urgent`). `list_tickets` **must** order by an explicit `case()` over `TICKET_PRIORITIES`, or the queue is wrong in production, in tests, or both.
- **Named enums survive `downgrade`** unless dropped explicitly — the failure mode already hit in Story 02. Guarded by the enum-drop loop in `0002_ticket_management.py`, and proven by the `upgrade → downgrade → upgrade` verification below.
- **Unicode in subject, description, and comments** — all `Text`/`String` with no length games beyond the declared caps; assert a round-trip including CJK and em-dashes, as `backend/tests/test_notes.py` does for note bodies.
- **Reference collision** — astronomically unlikely from 8 hex chars, but the unique index on `tickets.reference` means a collision surfaces as an `IntegrityError`, not as two tickets sharing a reference. Do **not** add retry logic; document it.
- **Concurrent updates** are last-write-wins, matching `backend/app/services/customers.py` (module docstring, lines 8–9). Two operators changing status simultaneously both append events, so the history still shows what happened even though one write wins the row.
- **Pagination bounds** — `limit` clamped to `[1, 100]` and `offset >= 0` at the route layer via `Query(ge=…, le=…)`, yielding **422**, exactly as `backend/app/api/routes/customers.py` line 67 does.
- **Malformed UUID in a path** → **422** from FastAPI's `uuid.UUID` coercion, not 404 or 500.
- **Uncertainty — agents vs. authenticated users.** This story creates a standalone `agents` table because assignment is an acceptance criterion and no auth exists yet (the same reasoning behind free-text `Interaction.author` at `backend/app/models/customer.py` line 134). When authentication lands, `agents` must either gain a nullable FK to the users table or be replaced outright, with a migration mapping existing `assignee_id` values. **Flag this in the PR description** so the auth story plans the reconciliation rather than discovering it.
- **Uncertainty — no time-based escalation.** `Ticket.is_overdue` is computed on read; nothing acts on it. A scheduler (Celery/APScheduler/cron) is required for real SLA escalation and is out of scope. Do **not** add a background thread to the FastAPI app as a shortcut.

---

## Test Plan

Backend — match the fixture style of `backend/tests/conftest.py` and the local-helper style of `backend/tests/test_interactions.py`.

1. **`backend/tests/conftest.py`** (modify) — add fixtures beside the existing `customer` fixture (lines 103–110): `agent` (one active `Agent` via `POST /api/agents`), `inactive_agent`, `ticket_category`, and `ticket` (an open ticket on `customer`). Do **not** restructure the existing `engine`/`session_factory`/`app`/`client` chain.
2. **`backend/tests/test_tickets_crud.py`** (new) — create returns 201 with a `TCK-`-prefixed reference and inherits the category's `default_priority` when `priority` is omitted; explicit priority wins; `GET` detail embeds customer/category/assignee; `PATCH` touches only supplied fields; `DELETE` → 204 then 404; unknown id → 404 on every verb; malformed UUID → 422; blank subject → 422; unicode subject/description round-trip; **409 when the customer is archived**.
3. **`backend/tests/test_ticket_status.py`** (new) — every transition in `ALLOWED_TRANSITIONS` succeeds; a representative set of forbidden moves (`open` → `resolved`, `closed` → `resolved`) → 409; same-status is idempotent and writes no event; `resolved_at`/`closed_at` are stamped on entry and **cleared on reopen**.
4. **`backend/tests/test_ticket_assignment.py`** (new) — assign, reassign, and unassign (`assignee_id: null`); 409 for an inactive agent, for an unknown agent, and for a terminal ticket; deactivating an agent leaves their assignment intact; `?unassigned=true` and `?assignee_id=` filters return the right rows.
5. **`backend/tests/test_ticket_escalation.py`** (new) — escalation increments the level and stamps `escalated_at`; `raise_priority=true` bumps `normal` → `high`; an `urgent` ticket keeps `urgent` and emits no `priority_changed`; 409 past `MAX_ESCALATION_LEVEL`; 409 on a resolved and on a closed ticket.
6. **`backend/tests/test_ticket_history.py`** (new) — a `created` event exists immediately after creation; status/priority/category/assignment/escalation each append exactly one correctly-typed event with accurate `old_value`/`new_value`; `POST /events` adds a `commented` event; the list is newest-first and paginates; **there is no route that edits or deletes an event** (assert `PATCH`/`DELETE` on `/api/tickets/{id}/events` return 405); deleting the ticket removes its events; deleting the **customer** cascades tickets **and** events.
7. **`backend/tests/test_ticket_categories.py`** (new) — category and agent CRUD; duplicate category name → 409; `DELETE` of an in-use category → 409; deactivation succeeds and drops the category from `?active_only=true`; `DELETE /agents/{id}` deactivates rather than deleting.
8. **`backend/tests/test_ticket_queue.py`** (new) — `list_tickets` ordering puts `urgent` first and `low` last **on SQLite** (the regression guard for the dialect trap above); `q` matches reference, subject, and description case-insensitively; filters compose; `limit`/`offset` bounds → 422; `total` reflects filters rather than page size, mirroring `backend/tests/test_pagination.py`.
9. **Regression** — `backend/tests/test_health.py`, `test_customers_crud.py`, `test_contacts.py`, `test_interactions.py`, `test_notes.py`, `test_attachments.py`, and `test_pagination.py` must all still pass unmodified. The only permitted edit to an existing test file is none.

Frontend — Vitest + RTL, mocking via `vi.stubGlobal("fetch", …)` exactly as `frontend/src/components/customer/__tests__/ContactDetailsPanel.test.tsx` does.

10. **`frontend/src/pages/__tests__/TicketsListPage.test.tsx`** (new) — renders rows from a mocked page; each row links to `/tickets/{id}`; search is debounced to a single request for a multi-character burst; status/priority/unassigned filters appear in the query string and reset `offset` to 0; `Next` advances and disables at the last page; empty state; API error reaches `role="alert"`.
11. **`frontend/src/components/ticket/__tests__/TicketWorkflowPanel.test.tsx`** (new) — the status `<select>` offers **only** the transitions legal from the current status; choosing one `POST`s to `/status` with the comment; the **Escalate** button is disabled at level 3 and on a terminal ticket; a server 409 renders in the error banner.
12. **`frontend/src/components/ticket/__tests__/TicketHistoryPanel.test.tsx`** (new) — renders each event type as its own sentence, newest first; the comment composer `POST`s to `/events` and refreshes; **no edit or delete control is rendered** for any event.
13. **`frontend/src/__tests__/navigation.test.tsx`** (modify) — extend the existing suite: **Tickets** appears in the nav pointing at `/tickets`; clicking it from `/` renders the queue heading; `/tickets/new` renders the create form; `aria-current="page"` lands on Tickets at `/tickets`. **Keep the existing health-page and customers assertions intact** — they are the Story 01/02 regression guard.

---

## Migration / Rollback

- **Forward:** `docker compose -f infra/docker-compose.yml exec backend alembic upgrade head` after deploy. Four new tables; nothing existing is altered except the addition of the `Customer.tickets` ORM relationship, which is **not** a schema change.
- **Rollback:** `alembic downgrade -1` drops `ticket_events`, `tickets`, `ticket_categories`, `agents` and the three named enum types. **This destroys all ticket history irrecoverably** — say so in the migration docstring. Customers and their Story 02 data are untouched.
- **Half-applied state:** Alembic uses transactional DDL on Postgres, so a failed `upgrade` rolls back whole. The dangerous combination is a **successful migration with a rolled-back application image**: the new tables simply sit unused, which is harmless. The reverse — new image, un-migrated database — fails loudly on the first ticket query with an `UndefinedTable` error, so **run the migration before switching traffic**.
- **Enum-drop verification is mandatory.** Run `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` against the compose Postgres. If the second `upgrade` fails with *"type ... already exists"*, the enum-drop loop in `downgrade()` is missing or wrong.

---

## Verification Steps

1. **Backend builds:** from `backend/`, with the venv active (`.venv\Scripts\activate` on Windows), `pip install -r requirements-dev.txt` then `alembic upgrade head` against the compose Postgres — set `CRM_DATABASE_URL=postgresql+psycopg://crm:crm@localhost:5432/crm`.
2. **Migration round-trips:** from `backend/`, `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` — all three succeed, proving the enum drops are correct.
3. **Backend tests:** from `backend/`, `pytest` — every new test file passes **and** the Story 01/02 suites stay green. Confirm the total count rose by the number of new tests with **zero** failures.
4. **Backend runs:** from `backend/`, `uvicorn app.main:app --reload`. `curl http://localhost:8000/api/tickets` returns `{"items":[],"total":0}`. Confirm `http://localhost:8000/docs` lists the `tickets` tag.
5. **Manual API smoke:** `POST /api/ticket-categories`, `POST /api/agents`, `POST /api/tickets` (against a customer from Story 02), then `POST /api/tickets/{id}/status` for a legal move (expect 200) and an illegal one (expect **409**), `POST /api/tickets/{id}/assignment`, `POST /api/tickets/{id}/escalate`, and finally `GET /api/tickets/{id}/events` — the event list must contain one row per mutation, newest first. On Windows, pass JSON bodies with `--data-binary @file.json` written as UTF-8; `curl -d` with inline non-ASCII is mangled by Git Bash.
6. **Frontend tests:** from `frontend/`, `npm test` (`vitest run`) — all suites pass.
7. **Frontend builds:** from `frontend/`, `npm run build` (`tsc -b && vite build`) — no type errors under `strict`.
8. **Frontend runs:** from `frontend/`, `npm install && npm run dev`. Open `http://localhost:5173/tickets`: create a category and an agent at `/tickets/setup`, raise a ticket, move it through statuses, assign it, escalate it, add a comment, and confirm the History tab shows every step. Open a customer at `/customers/:id` and confirm the **Tickets** tab lists that ticket.
9. **Regression:** `/` still renders "CRM — System Health" with `status: ok`; `/customers` still lists, searches, and paginates; a customer's Contacts, Interactions, and Notes & Attachments tabs are unchanged.
10. **Compose:** from the repo root, `docker compose -f infra/docker-compose.yml up --build` then `docker compose -f infra/docker-compose.yml exec backend alembic upgrade head` — `db`, `backend`, and `frontend` all reach a running state and the ticket queue loads through the Vite proxy at `http://localhost:5173/tickets`.

---

## Done Criteria

- [ ] A ticket can be created against a customer and tracked, carrying a unique human-readable reference, subject, description, and timestamps.
- [ ] Tickets carry a **priority** (`low`/`normal`/`high`/`urgent`) and an admin-maintained **category**; omitting the priority inherits the category's `default_priority`.
- [ ] Categories and agents can be created, renamed, and deactivated; deleting an in-use category returns **409**.
- [ ] A ticket can be assigned to an active agent, reassigned, and unassigned; assigning to an inactive agent returns **409**.
- [ ] Status changes follow `ALLOWED_TRANSITIONS`; a forbidden move returns **409** and `resolved_at`/`closed_at` are stamped on entry and cleared on reopen.
- [ ] A ticket can be escalated, incrementing `escalation_level` and stamping `escalated_at`; escalation is refused past level 3 and on resolved/closed tickets.
- [ ] Every mutation appends an immutable `ticket_events` row; the history endpoint returns them newest-first; **no route edits or deletes an event**.
- [ ] Deleting a customer cascades their tickets and all ticket events.
- [ ] Migration `0002_ticket_management` applies, rolls back, and **re-applies** cleanly, dropping its three named enum types on downgrade.
- [ ] `/tickets` is reachable from the app's main navigation, and each customer's detail page has a **Tickets** tab.
- [ ] Backend and frontend tests listed in the Test Plan all pass.
- [ ] No regressions in the health endpoint or in any Story 02 customer behaviour.

**STOP HERE. Report to the user and wait for confirmation before proceeding to Story 04.**
