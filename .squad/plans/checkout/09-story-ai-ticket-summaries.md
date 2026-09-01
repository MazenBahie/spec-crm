# Story 09 — Ticket Summaries

## Prerequisites

- Story 01 project init completed: backend FastAPI + Alembic scaffold under `backend/app/` and frontend React scaffold under `frontend/src/` are in place.
- Story 03 ticket management completed (migration `backend/alembic/versions/0002_ticket_management.py`) — this story adds two nullable columns to the existing `tickets` table and one new value to the existing `ticket_event_type` Postgres enum. It does not touch `customers`, `channels`, `agent_tasks`/`quick_replies`, `portal_users`, or `kb_articles`.
- Story 08 "AI Foundation" completed. This story depends on it for concrete contracts, not just convention — **confirmed against Story 08's final file** (`.squad/plans/checkout/08-story-ai-foundation.md`), not merely assumed:
  - `app.services.ai.provider.AIProvider` — a `Protocol` (mirroring `ChannelDriver` in `backend/app/services/channels/driver.py`, read in full below) whose methods include `summarize_ticket(self, ticket: Ticket, messages: Sequence[ChannelMessage]) -> str` — real ORM rows, not keyword args or dicts.
  - `app.services.ai.provider.get_ai_provider()` — a **plain, zero-argument module-level function**, not a FastAPI dependency (Story 08's own `provider.py` docstring: the service layer stays FastAPI-free by this codebase's convention, `app/api/deps.py:10-12`). Callers import the module (`from app.services.ai import provider as ai_provider`) and call `ai_provider.get_ai_provider()`, so a test's `monkeypatch.setattr(ai_provider, "get_ai_provider", fake_factory)` takes effect — a bare-name import would not. Tests do **not** use `application.dependency_overrides[...]` for this (unlike `get_db`/`get_storage`).
  - `app.services.ai.provider.AnthropicProvider` and `app.services.ai.provider.StubAIProvider` — the real and degrade-to-stub implementations. `StubAIProvider` is what every AI capability falls back to when `settings.ai_enabled` is false or `settings.anthropic_api_key` is unset.
  - `app.services.ai.errors.AIProviderError` (re-exported from `app.services.ai.provider`) — raised by a provider on failure. It does **not** subclass `app.services.errors.ServiceError` and is **not** registered in `backend/app/main.py`'s `register_exception_handlers` — Story 08 explicitly ships no central mapping for it and leaves that decision to each caller. This story is the first caller to raise it from a route (Backend Tasks §5) and therefore must add its own handling — see the resolved instruction there.
  - `settings.anthropic_api_key`, `settings.ai_model`, `settings.ai_enabled` on `backend/app/core/config.py`'s `Settings`.

---

## Story Goal

Give agents a fast, disposable read on a ticket without opening the whole thread: an AI-generated summary of the ticket's subject, description, and full message history, shown on the ticket detail page and regenerable on demand.

1. `Ticket` gains two nullable columns — `ai_summary` (text) and `ai_summary_generated_at` (timestamp) — so the summary persists across page loads instead of being recomputed on every view.
2. A new service function assembles the ticket + its message thread, calls the AI provider (Story 08), writes the two columns, and appends a `ticket_events` row of a new type, `ai_summary_generated`, so "when was this last regenerated, and by implication who was looking at the ticket at the time" is visible in the existing history tab with no new UI.
3. Agents trigger generation with an explicit "Regenerate" click on the ticket detail page — never automatically on page load, which would spend an API call every time anyone opens the ticket.
4. The summary is visually labelled as AI-generated wherever it is shown, and degrades to whatever `StubAIProvider` returns when AI is disabled or unconfigured — the feature never disappears, it just stops sounding like Claude.

**Out of scope:** summarizing anything other than one ticket's own subject/description/messages (no cross-ticket context, no customer-history rollup); streaming the summary as it generates; editing or approving the summary before it's saved (it's a read-only display, not a suggested reply — that's Story 10); scheduled/automatic regeneration on a timer or on new messages arriving.

---

## Context — Read These Files First

1. `.squad/stories/checkout/ai-features/intake.md` — this arc's intake. Item 1 of both the Description and Acceptance Criteria lists is "Ticket summaries" — this story.
2. `.squad/plans/checkout/08-story-ai-foundation.md` — **read this first if it exists on disk by the time you execute this story.** It is being authored in parallel and was not available to write this plan; every assumption about `AIProvider`/`get_ai_provider`/`StubAIProvider`/`AIProviderError` above must be checked against it and this story's Backend Tasks adjusted to match the real signatures, not the assumed ones.
3. `backend/app/services/channels/driver.py` (93 lines) — the `ChannelDriver` Protocol that `AIProvider` is modeled on. Read this to understand the *shape* Story 08 is expected to have produced (a stateless Protocol, a stub implementation that never breaks the caller, raising rather than returning sentinel failure values) even though you cannot read `AIProvider` itself yet.
4. `backend/app/services/channels/service.py:74-93` (`list_messages_for_ticket`) — how a ticket's message thread is paged and ordered (oldest first). This story's summary service reuses this function rather than querying `ChannelMessage` directly.
5. `backend/app/services/channels/service.py:96-166` (`enqueue_outbound`) — the best-effort precedent: the row is written first, the external call is best-effort, and a failure is recorded rather than raised past the caller. Read the module docstring (lines 1-13) too. This story's route is **not** on that same synchronous-request-path concern (ticket creation doesn't call AI), so the parallel is one of *pattern*, not identical need — see Edge Cases below for how this story's contract actually differs.
6. `backend/app/models/ticket.py:44-53` (`TICKET_EVENT_TYPES`) and `:95-166` (`Ticket` model) — read in full before adding the new columns and the new event type; note `TicketEvent.event_type` is backed by a real Postgres named enum (`ticket_event_type_enum = Enum(*TICKET_EVENT_TYPES, name="ticket_event_type")`, line 57), **unlike** Knowledge Base's `kind`/`status` columns, which Story 07 deliberately made plain strings with a CHECK constraint specifically so they could grow without a named-enum migration. `ticket_event_type` cannot be widened the same way — see Backend Tasks §1 for what that means for the migration.
7. `backend/app/services/tickets.py:111-134` (`_record`) — the only way a `ticket_events` row is written; this story's service calls it the same way `add_comment` (line 590) does, with `event_type="ai_summary_generated"`.
8. `backend/app/schemas/ticket.py:114-142` (`TicketRead`, `TicketDetailRead`) — read in full. `TicketDetailRead` extends `TicketRead` (`class TicketDetailRead(TicketRead):`, line 136) rather than repeating its fields, so the two new fields go on `TicketRead` once and `TicketDetailRead` inherits them for free. `TicketEventType` (line 17-26) is a `Literal` mirroring `TICKET_EVENT_TYPES` — it needs the new value too, or `TicketEventRead.model_validate(...)` raises a validation error the first time a summary-generation event is fetched through `GET /tickets/{id}/events`.
9. `backend/app/services/errors.py` — `NotFound`/`Conflict`/`Forbidden`/`PayloadTooLarge`, no `Error` suffix, mapped centrally in `backend/app/main.py:61-64`. This story does not add a new error class for "ticket not found" (reuses `NotFound` via `get_ticket`) but does need a mapping decision for `AIProviderError` — see Backend Tasks §5.
10. `backend/app/api/deps.py` — `CurrentAgent`/`get_current_agent` (401 on a missing/invalid `X-Agent-Id`), used to gate the new route.
11. `backend/app/api/routes/tickets.py` (281 lines) — read the whole file. Its router has **no** router-level `dependencies=` (unlike `knowledge_base.router`); individual routes opt into `CurrentAgent` inline, exactly as the internal-notes routes do (`list_ticket_notes`/`add_ticket_note`, lines 169-201). This story's new route follows that same inline-gating pattern rather than moving the whole router behind agent auth.
12. `backend/app/main.py` — see `app.include_router(tickets.router, ...)` (line 31) and the exception-handler registrations (lines 52-64). No new router is added by this story (see Backend Tasks §5), so nothing here changes — confirm that by reading the file rather than assuming it.
13. `backend/alembic/versions/0006_knowledge_base.py` — the immediately preceding migration; read in full for the module-docstring / `revision`/`down_revision` / `Sequence`/`Union` import style to mirror. Note it deliberately avoided a named enum for exactly the reason described in item 6 above — this story cannot avoid one, since it is adding to an enum that already exists.
14. `backend/tests/conftest.py:70-94` (`app` fixture) — the `dependency_overrides` pattern used for `get_db`/`get_storage`, **not** reused for `get_ai_provider` (Story 08 deliberately keeps that a plain module-level function — see Prerequisites). This story's tests monkeypatch `app.services.ai.provider.get_ai_provider` directly instead (see Test Plan). Lines 154-161 (`agent_client`) and 222-234 (`ticket`) are the fixtures the route test builds on.
15. `frontend/src/api/client.ts` — `request<T>`, `buildQuery`, `ApiError`. All agent-facing calls in this story go through `request`, never `portalClient.ts` (customer/portal-only, not used by this agent-facing story).
16. `frontend/src/api/tickets.ts` — `getTicket` (lines 41-43, GET shape) and `addTicketComment` (lines 114-123, POST shape) are this story's templates for `frontend/src/api/ai.ts`.
17. `frontend/src/types/ticket.ts` — `Ticket` (line 73), `TicketDetail` (line 93, extends `Ticket`), and the `TicketEventType` union (lines 11-19). Same inheritance shape as the backend schemas: add the two new fields to `Ticket` once, `TicketDetail` inherits them.
18. `frontend/src/pages/TicketDetailPage.tsx` — read in full (182 lines). `TABS` array at line 14; the Overview tab's content block spans lines 136-169 (a `<dl>` of read-only fields); `MessagesPanel`/`NotesThreadPanel`/`TicketHistoryPanel`/`TicketWorkflowPanel` (lines 4-8) are the four existing tab components, each taking `ticketId` (and, for `MessagesPanel`, the loaded `ticket`) as props and calling `load()` on the page to refresh after a mutation.
19. `frontend/src/components/ticket/MessagesPanel.tsx` — the closest existing precedent for "load on mount, POST an action, refresh, show a per-item error state without crashing the page" (see its `handleSend`, lines 82-103, and the `sent.status === "failed"` branch at line 95 — a failure is still a successful response the component renders specially, not a thrown error page).
20. `frontend/src/components/ticket/__tests__/MessagesPanel.test.tsx` — this story's test template: a `mockApi`-style `vi.stubGlobal("fetch", ...)` router keyed on URL substring and HTTP method (see its `mockApi` helper, lines 104-139), `render` + `screen.findBy...` assertions, and a dedicated test for the initial-load error path (last test in the file, "surfaces an API error from the initial load").

- Grep for `include_router` in `backend/app/main.py` before assuming this story needs a new one — it does not (see Backend Tasks §5).
- Grep for `from app.services.errors import` across `backend/app/services/` to see the canonical error import path before adding any new exception type.
- Grep for `dependency_overrides` in `backend/tests/conftest.py` before writing the AI-provider override in this story's test module — Story 08 may already have added a fixture for it (e.g. `stub_ai_provider` or similar) by the time this story executes; if so, reuse it instead of duplicating the override.

---

## Backend Tasks

### 1 — Alembic migration

Create file: `backend/alembic/versions/0007_ai_ticket_summaries.py`

```python
"""ai ticket summaries

Adds ai_summary (nullable text) and ai_summary_generated_at (nullable
timestamp) to tickets, and a new "ai_summary_generated" value to the
pre-existing ticket_event_type Postgres enum.

The two new columns follow the same nullable-with-no-backfill shape as every
other optional Ticket field (due_at, escalated_at, ...) -- an existing ticket
simply has no summary yet, which the frontend renders as "No summary yet."

Widening ticket_event_type is NOT the same operation as adding a KB `kind` or
`status` value (0006_knowledge_base.py): those are plain strings backed by a
CHECK constraint specifically so they could grow without touching a named
type. ticket_event_type is a real Postgres enum
(``app.models.ticket.ticket_event_type_enum``), so growing it needs
``ALTER TYPE ... ADD VALUE``, which:

- is safe to run inside the same transaction Alembic wraps this migration in
  on Postgres 12+ (this project's infra/docker-compose.yml pins postgres:16),
  as long as the new value is not also *used* in the same transaction --
  this migration only adds it, never inserts a row with it;
- has NO reverse operation. Postgres has never supported dropping a single
  value from an enum type (only recreating the type from scratch under a new
  name and swapping every column over, which is far more than this
  downgrade should attempt). downgrade() therefore only drops the two
  columns; the added enum label is left in place permanently, including
  after a downgrade. This mirrors an accepted, documented one-way door
  elsewhere in this codebase (0001-0004 name their enums so they *can* be
  dropped in downgrade() by dropping the owning table; this is the first
  migration in the project that widens an enum without also being able to
  drop its table, since `tickets` predates this story by two stories).

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-01 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0007'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tickets', sa.Column('ai_summary', sa.Text(), nullable=True))
    op.add_column(
        'tickets',
        sa.Column('ai_summary_generated_at', sa.DateTime(timezone=True), nullable=True),
    )
    # IF NOT EXISTS makes this migration safe to re-run against a database
    # where a prior partial run already added the label.
    op.execute("ALTER TYPE ticket_event_type ADD VALUE IF NOT EXISTS 'ai_summary_generated'")


def downgrade() -> None:
    # See module docstring: the added enum label cannot be removed and is
    # left in place. Only the two columns are reversed.
    op.drop_column('tickets', 'ai_summary_generated_at')
    op.drop_column('tickets', 'ai_summary')
```

**Executor note:** if by the time this migration is written Story 08 has *also* queued a migration ahead of `0007` (e.g. an `08xx` migration for AI-related tables), renumber so the chain stays linear and update `down_revision` accordingly — the number `0007`/`down_revision = '0006'` above assumes this is the very next migration applied after Knowledge Base's `0006`.

Tests never run this migration directly — `backend/tests/conftest.py`'s `engine` fixture builds the schema via `Base.metadata.create_all(eng)` (line 48) straight from the Python models. That means Task 2 (adding `"ai_summary_generated"` to the `TICKET_EVENT_TYPES` tuple and the two columns to the `Ticket` model) is what makes the test suite's SQLite schema correct; this migration is what makes a real Postgres database match it. Both are required — neither alone is sufficient.

### 2 — Model changes

Edit `backend/app/models/ticket.py`.

Add `"ai_summary_generated"` to the `TICKET_EVENT_TYPES` tuple (line 44-53):

```python
TICKET_EVENT_TYPES = (
    "created",
    "status_changed",
    "priority_changed",
    "category_changed",
    "assigned",
    "unassigned",
    "escalated",
    "commented",
    "ai_summary_generated",
)
```

Add two columns to the `Ticket` class, next to the other nullable `datetime`/text fields (near `due_at`/`resolved_at`, before `created_at`):

```python
    ai_summary: Mapped[str | None] = mapped_column(Text)
    ai_summary_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

`Text` and `DateTime` are already imported at the top of this file (lines 16-24) — no new imports needed.

### 3 — Schema changes

Edit `backend/app/schemas/ticket.py`.

Add `"ai_summary_generated"` to the `TicketEventType` Literal (lines 17-26):

```python
TicketEventType = Literal[
    "created",
    "status_changed",
    "priority_changed",
    "category_changed",
    "assigned",
    "unassigned",
    "escalated",
    "commented",
    "ai_summary_generated",
]
```

Add two fields to `TicketRead` (line 114-133), after `is_overdue`:

```python
    is_overdue: bool
    ai_summary: str | None
    ai_summary_generated_at: datetime | None
```

`TicketDetailRead` (line 136) inherits both automatically — do not repeat them there.

### 4 — Service layer

Create file: `backend/app/services/ai/ticket_summary.py`

```python
"""Ticket-summary generation.

One function: build the prompt inputs from a ticket's own fields plus its
full message thread, hand them to whatever `AIProvider` Story 08 wired up
(real Anthropic client or `StubAIProvider`), and persist the result on the
Ticket row plus one `ticket_events` row so "when was this last generated" is
visible in the existing History tab with no new UI.

Deliberately synchronous and blocking within the request that calls it: this
is triggered by an explicit "Regenerate" click (see Story Goal — never on
page load), not by ticket creation or any other path that must stay fast
regardless of AI latency. Contrast with
`app.services.channels.service.enqueue_outbound`, which *is* on such a path
and therefore never lets a provider failure become a raised exception. Here,
letting `AIProviderError` propagate to the route (which turns it into a
clean 5xx) is correct: an agent who clicked "Regenerate" is exactly the
person who needs to be told it failed.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.ticket import Ticket
from app.services.ai import provider as ai_provider  # Story 08
from app.services.channels.service import list_messages_for_ticket
from app.services.tickets import _record, _now, get_ticket

# Defensive cap on how much thread history goes into the prompt. Story 08 may
# already impose its own token/character budget inside AnthropicProvider —
# if so, this cap should be raised to match rather than duplicated at a
# different limit; verify against Story 08's actual code before treating this
# number as final.
MAX_SUMMARY_MESSAGES = 50


def generate_summary(db: Session, ticket_id: uuid.UUID) -> Ticket:
    """(Re)generate and persist the AI summary for one ticket.

    Loads the ticket (raises `NotFound` via `get_ticket` if it does not
    exist — the route needs no separate existence check), loads up to the
    most recent `MAX_SUMMARY_MESSAGES` of its thread, and calls the AI
    provider. A ticket with no messages yet still gets a summary — the
    provider call still happens, with an empty message list, so a brand-new
    ticket's summary is just its subject and description in the agent's
    words rather than an error or a blank state.
    """
    ticket = get_ticket(db, ticket_id, with_relations=True)

    # Oldest-first, matching how the Messages tab itself reads (see
    # `list_messages_for_ticket`'s own docstring: "this reads as a
    # conversation"). Capped to the most recent MAX_SUMMARY_MESSAGES by
    # reading the *last* page rather than the first, so a very long thread
    # summarizes its most recent state, not its oldest.
    messages, total = list_messages_for_ticket(db, ticket.id, limit=MAX_SUMMARY_MESSAGES, offset=0)
    if total > MAX_SUMMARY_MESSAGES:
        offset = total - MAX_SUMMARY_MESSAGES
        messages, _ = list_messages_for_ticket(
            db, ticket.id, limit=MAX_SUMMARY_MESSAGES, offset=offset
        )

    # Confirmed against Story 08's real `AIProvider.summarize_ticket` signature:
    # `summarize_ticket(self, ticket: Ticket, messages: Sequence[ChannelMessage]) -> str`
    # (backend/app/services/ai/provider.py) — real ORM rows passed straight
    # through, the same way `ChannelDriver.send(message: ChannelMessage)` takes
    # the row directly rather than a DTO. An earlier draft of this function
    # assumed keyword args (`subject=`, `description=`, dict-shaped messages);
    # that assumption was wrong and is corrected here.
    # Import the module, not the bare name (see the import above): calling
    # `ai_provider.get_ai_provider()` re-reads the module attribute on every
    # call, which is what lets a test's `monkeypatch.setattr(ai_provider,
    # "get_ai_provider", fake_factory)` take effect. A `from
    # app.services.ai.provider import get_ai_provider` bare-name import would
    # bind the function at import time and never see the monkeypatch.
    provider = ai_provider.get_ai_provider()
    summary_text = provider.summarize_ticket(ticket, messages)

    ticket.ai_summary = summary_text
    ticket.ai_summary_generated_at = _now()

    _record(db, ticket, "ai_summary_generated")

    db.flush()
    db.refresh(ticket)
    return ticket
```

`_now`/`_record`/`get_ticket` are private-by-convention module functions in `app.services.tickets` (the leading underscore on `_now`/`_record` is the same convention as the rest of that file, e.g. `_stringify`); importing them across modules already has precedent (`app.services.channels.service` imports `get_ticket` from `app.services.tickets` the same way — see Context §4/§5). No new activity-feed entry: `activity.record(...)` is for events a teammate needs proactively pushed to them (an assignment, a status change, a reply) — regenerating a summary is a passive, no-one-to-notify action, so `ticket_events` alone (already visible on the existing History tab) is the whole audit trail, exactly the same reasoning `assign_ticket` gives for skipping a mention row on a routine queue move (`backend/app/services/tickets.py:516-519`).

### 5 — API route

Add to `backend/app/api/routes/tickets.py` (do **not** create a new `backend/app/api/routes/ai.py`).

**Justification:** this is a single ticket-scoped mutation, not the start of a new resource family — there is nothing else to hang off an `ai.py` router yet (Story 10's suggested replies and Story 11's categorization are separate ticket-scoped actions that may or may not end up sharing a file with this one; that's a call for whoever writes those stories, informed by how this route reads in practice). `tickets.py` already imports `CurrentAgent`, already has the exact "agent-gated route inline on an otherwise ungated router" pattern for the internal-notes endpoints (lines 169-201), and already imports `svc` (`app.services.tickets`) — this story adds one more import (`app.services.ai.ticket_summary`) rather than standing up a new router, new prefix, and a new `main.py` registration for one endpoint.

```python
from app.services.ai import ticket_summary as ai_summary_svc
```

```python
# --------------------------------------------------------------------------- #
# AI summary (agent-only — costs a real API call, so it is never automatic)
# --------------------------------------------------------------------------- #
@router.post("/tickets/{ticket_id}/ai/summary", response_model=TicketRead)
def regenerate_ticket_summary(
    ticket_id: uuid.UUID, db: DbDep, agent: CurrentAgent
) -> TicketRead:
    """Regenerate and persist the AI summary. Explicit action only — see
    Story Goal on why this is never triggered by a page load."""
    return TicketRead.model_validate(ai_summary_svc.generate_summary(db, ticket_id))
```

No `GET /tickets/{ticket_id}/ai/summary` is added: the two fields already ride on the existing `GET /tickets/{ticket_id}` response (`TicketDetailRead` extends `TicketRead`, Backend Tasks §3), which `TicketDetailPage` already fetches on mount. A separate read endpoint would be a second network call returning a subset of data the page already has in hand.

**`AIProviderError` mapping — resolved, not conditional.** `backend/app/main.py:61-64` maps exactly four exception types today (`NotFound`, `Forbidden`, `Conflict`, `PayloadTooLarge`), all subclasses of `app.services.errors.ServiceError`. Story 08 confirmed `AIProviderError` is **not** one of them and registers no handler of its own (`08-story-ai-foundation.md` Backend Tasks §8: "no router, no new exception handler... later stories decide per-route"). Since this route is the first in the codebase to raise `AIProviderError` from inside a request, and Backend Tasks §4 above deliberately lets it propagate rather than swallowing it (an agent who clicked "Regenerate" needs to be told it failed, per Story 08's own documented judgment call), this story **must** add the mapping itself:

- In `backend/app/main.py`, alongside the existing `app.add_exception_handler(NotFound, ...)`-style block (lines 52-64), add one more registration mapping `AIProviderError` to HTTP 502 (Bad Gateway — this is an upstream/integration failure, not a client-request problem, matching the semantics `NotFound`→404/`Conflict`→409 already establish for the other three).
- Import `AIProviderError` from `app.services.ai.errors` in `main.py`, alongside the existing `from app.services.errors import ...` line — do not import it from `app.services.errors` (it does not live there).
- This handler is added once, in `main.py`, not per-route — Stories 11-13, if any of them also let `AIProviderError` propagate from a route (Story 11's recompute route does; see `.squad/plans/checkout/11-story-ai-automatic-categorization.md` Backend Task 7), reuse this same registration rather than each adding their own. If Story 11 lands first and already added it, skip this step here — check `main.py` before adding a duplicate.

The frontend-facing contract is the same either way: a failed regeneration is a non-2xx (502) response with a JSON `{"detail": "..."}` body, which `frontend/src/api/client.ts`'s `request<T>` already turns into a thrown `ApiError` (see Context §15) — no special-casing needed on the frontend beyond a normal try/catch.

### 6 — Wiring & exports

None. `tickets.router` is already registered in `backend/app/main.py:31`; this story adds one route to an existing router rather than a new router, so no `include_router` change is needed. Confirm this by reading `main.py` rather than assuming — do not add a redundant registration.

---

## Frontend Tasks

### 7 — Types

Edit `frontend/src/types/ticket.ts`.

Add `"ai_summary_generated"` to the `TicketEventType` union (lines 11-19):

```ts
export type TicketEventType =
  | "created"
  | "status_changed"
  | "priority_changed"
  | "category_changed"
  | "assigned"
  | "unassigned"
  | "escalated"
  | "commented"
  | "ai_summary_generated";
```

Add two fields to `Ticket` (line 73-91), after `is_overdue`:

```ts
export interface Ticket {
  // ...existing fields unchanged...
  is_overdue: boolean;
  ai_summary: string | null;
  ai_summary_generated_at: string | null;
}
```

`TicketDetail` (line 93) extends `Ticket` and inherits both — do not repeat them there, mirroring the backend's `TicketRead`/`TicketDetailRead` split (Backend Tasks §3).

### 8 — API client

Create file: `frontend/src/api/ai.ts`

```ts
/** Typed wrappers for the AI-features endpoints. Story 09: ticket summaries.
 *  Story 10+ (suggested replies, categorization, ...) may add to this file
 *  rather than each starting a new one — see the router-placement note in
 *  09-story-ai-ticket-summaries.md Backend Tasks §5. */

import { request } from "./client";
import type { Ticket } from "../types/ticket";

/** Read-only view of a ticket's persisted summary, without a POST.
 *
 * There is no dedicated GET endpoint for this (see the backend story's
 * Backend Tasks §5) — the two fields already ride on `GET /tickets/{id}`.
 * This wrapper exists so a component that only cares about the summary can
 * ask for it by name; it costs the same one network call `getTicket` does,
 * not an extra one.
 */
export function getTicketSummary(
  ticketId: string,
): Promise<Pick<Ticket, "ai_summary" | "ai_summary_generated_at">> {
  return request<Ticket>(`/tickets/${ticketId}`);
}

export function regenerateTicketSummary(ticketId: string): Promise<Ticket> {
  return request<Ticket>(`/tickets/${ticketId}/ai/summary`, { method: "POST" });
}
```

`TicketDetailPage` (Frontend Tasks §9) already holds the full `TicketDetail` from its own `getTicket` call and does not need `getTicketSummary` itself — it is provided for a future standalone summary widget (e.g. a dashboard card) that wants the summary without the rest of the ticket. `regenerateTicketSummary` is the one this story's UI actually calls.

### 9 — Ticket detail page

Edit `frontend/src/pages/TicketDetailPage.tsx`.

**Placement: inside the existing Overview tab, not a new tab.** The summary is a passive, read-only enrichment of information already on that tab (subject/description), not a new workflow surface with its own state machine the way Messages/Notes/Workflow/History each are — adding a sixth tab for two fields and one button would outweigh the content. Insert a new `<section>` inside the `tab === "Overview"` block (line 135), before the existing `<dl>` (which starts at line 138), so it reads top-to-bottom as "here's the AI take, here's the raw fields":

```tsx
{tab === "Overview" && (
  <section>
    <h2 style={{ fontSize: "1.1rem" }}>Overview</h2>

    <div style={{ ...styles.card, marginBottom: "1rem" }}>
      <div style={{ ...styles.row, justifyContent: "space-between" }}>
        <span style={{ ...styles.row, gap: "0.4rem" }}>
          <strong>Summary</strong>
          {/* Visible AI-generated label, per this arc's global rule — every
              AI output is marked wherever it is shown. */}
          <span
            style={{
              fontSize: "0.7rem",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
              padding: "0.1rem 0.4rem",
              borderRadius: 8,
              border: `1px solid ${tokens.accent}`,
              color: tokens.accent,
            }}
          >
            AI-generated
          </span>
        </span>
        <button
          type="button"
          style={styles.button}
          onClick={() => void handleRegenerateSummary()}
          disabled={summaryBusy}
        >
          {summaryBusy ? "Generating…" : ticket.ai_summary ? "Regenerate" : "Generate summary"}
        </button>
      </div>
      <ErrorBanner message={summaryError} />
      <p style={{ whiteSpace: "pre-wrap", margin: "0.5rem 0 0" }}>
        {ticket.ai_summary ?? "No summary yet."}
      </p>
      {ticket.ai_summary_generated_at && (
        <p style={{ ...styles.muted, margin: "0.35rem 0 0", fontSize: "0.8rem" }}>
          Generated {formatDateTime(ticket.ai_summary_generated_at)}
        </p>
      )}
    </div>

    <dl>
      {/* ...existing dl content, unchanged... */}
    </dl>
  </section>
)}
```

State and handler, added alongside the page's existing `useState`/`handleDelete` (near line 24-57):

```tsx
const [summaryBusy, setSummaryBusy] = useState(false);
const [summaryError, setSummaryError] = useState<string | null>(null);

async function handleRegenerateSummary() {
  setSummaryBusy(true);
  setSummaryError(null);
  try {
    const updated = await regenerateTicketSummary(id);
    setTicket((current) => (current ? { ...current, ...updated } : current));
  } catch (err) {
    // A failed regeneration must not blank the summary that's already there,
    // and must not crash the rest of the page — the other four tabs keep
    // working. Same "surface next to the composer, not just a thrown page"
    // instinct as MessagesPanel's failed-send handling (Context §19).
    setSummaryError(err instanceof Error ? err.message : String(err));
  } finally {
    setSummaryBusy(false);
  }
}
```

Add the import at the top of the file: `import { regenerateTicketSummary } from "../api/ai";`.

Note the button label changes from "Generate summary" to "Regenerate" once a summary exists — this is cosmetic only, both call the same endpoint (`POST .../ai/summary` always (re)computes and overwrites; there is no separate "first generation" vs. "regeneration" server-side distinction, matching the service function's name, `generate_summary`, not `generate_or_regenerate`).

---

## Edge Cases & Failure Modes

- **Ticket has no messages yet.** `generate_summary` still calls the provider, with `messages=[]`. The prompt is effectively "summarize this ticket from its subject and description alone." This is a normal, expected call shape, not an error — do not special-case an empty thread into skipping the AI call or returning a canned string outside of what `StubAIProvider` itself would return for a real ticket with no messages either.
- **AI disabled or unconfigured (`settings.ai_enabled` false / no API key).** `get_ai_provider()` (Story 08) returns `StubAIProvider`, whose `summarize_ticket(...)` returns *some* deterministic, clearly-non-Claude string rather than raising. This story's service function has no branch for this case — the degrade-to-stub behavior is entirely Story 08's responsibility, and this story's route/service code is identical whether the real provider or the stub answers. The frontend still shows the "AI-generated" badge on stub output (Story 08 does not appear to distinguish "real" vs. "stub" output at the schema level, and this story does not invent a `is_stub` field to do so — if that distinction matters, it is Story 08's to add).
- **Generation failure (`AIProviderError` — API down, rate-limited, bad key).** The route lets this propagate (see Backend Tasks §5's exact mapping caveat) rather than swallowing it — this is the opposite of `enqueue_outbound`'s best-effort contract, and deliberately so: `enqueue_outbound` runs on a path with no one waiting synchronously for the *outcome* of the send (the row is the record either way), while this route is a direct response to someone clicking "Regenerate" and waiting to see what happened. The frontend's `handleRegenerateSummary` (Frontend Tasks §9) catches the resulting `ApiError`, shows it in `summaryError` next to the button, and leaves `ticket.ai_summary` at whatever it was before the click — a failed regeneration never blanks a previously-successful summary, and never prevents the other four tabs (Workflow/Messages/Notes/History) from rendering, since the failure is caught locally inside the summary panel's own handler, not thrown up to `TicketDetailPage`'s top-level `load()`/`error` state.
- **No auto-regeneration on page view — hard rule, stated for cost control.** `TicketDetailPage`'s `load()` (existing code, lines 27-42) only calls `getTicket`, never `regenerateTicketSummary`. The summary shown on open is whatever was last persisted (possibly `null`, rendered as "No summary yet."). Generation happens **only** inside `handleRegenerateSummary`, itself only reachable via the button's `onClick`. Do not add a `useEffect` that calls `regenerateTicketSummary` when `ticket.ai_summary` is `null` — that would silently spend one AI call per view of every not-yet-summarized ticket, exactly the cost blow-up this rule exists to prevent.
- **Very long message threads.** `generate_summary` caps the thread fed into the prompt at `MAX_SUMMARY_MESSAGES = 50` (the most recent 50, not the oldest 50 — see the service function's comment on why it reads the *last* page). This number is a placeholder chosen without visibility into Story 08's actual prompt-construction code; if Story 08 imposes its own truncation (e.g. a character or token budget inside `AnthropicProvider` itself), reconcile the two — either raise this constant to match, or remove it here and let Story 08's layer own truncation entirely, whichever avoids truncating twice at two different, undocumented-to-each-other limits.
- **Concurrent regeneration (two agents click "Regenerate" on the same ticket around the same time).** Last write wins, matching every other ticket mutation in this codebase (`app/services/tickets.py`'s module docstring: "every update is last-write-wins... two overlapping PATCHes silently keep the later one"). Both requests append their own `ai_summary_generated` ticket_events row (an honest record that two regenerations happened), and whichever `db.flush()`/commit lands second determines the final `ai_summary` text. No locking is introduced for this story, consistent with the rest of the ticket-mutation surface.
- **Ticket does not exist.** `get_ticket` (inside `generate_summary`) raises `NotFound`, mapped to 404 by the existing central handler — no new behavior needed.

---

## Test Plan

Backend (add `backend/tests/test_ai_ticket_summaries.py`, following `backend/tests/test_quick_replies.py`'s fixture style and Story 08's `monkeypatch.setattr(ai_provider, "get_ai_provider", ...)` test-override mechanism — see Prerequisites):

1. **`generate_summary` unit test with the stub provider.** With no monkeypatch at all — `get_ai_provider()` already returns `StubAIProvider` by default in the test environment (no `CRM_ANTHROPIC_API_KEY`/`CRM_AI_ENABLED` set) — call `generate_summary(db, ticket.id)` directly on a ticket with no messages; assert `ticket.ai_summary` is non-empty, `ticket.ai_summary_generated_at` is set, and calling it again with a message added changes `ai_summary` to reflect it (exact content depends on `StubAIProvider`'s deterministic output — assert on presence/change, not literal text, unless Story 08's stub output is stable and documented).
2. **Route test** using the `agent_client`/`ticket` fixtures (`conftest.py:154-161`, `222-234`): `POST /api/tickets/{ticket['id']}/ai/summary` with the `X-Agent-Id` header returns 200 and a `TicketRead`-shaped body with `ai_summary` populated; the same request via the unauthenticated `client` fixture returns 401 (no `X-Agent-Id`).
3. **Event-history assertion.** After calling the route, `GET /api/tickets/{ticket_id}/events` includes exactly one event with `event_type == "ai_summary_generated"`.
4. **Empty-thread case.** A ticket fixture with zero messages still returns 200 from the route (does not require at least one message to succeed) — this is the "ticket has no messages yet" edge case made concrete.
5. **Provider failure surfaces cleanly.** Monkeypatch `ai_provider.get_ai_provider` (module reference, per Backend Tasks §4) to a fake provider whose `summarize_ticket` raises `AIProviderError`; assert the route returns `502` with a JSON `detail` field, per the handler this story registers in `main.py` (Backend Tasks §5) — not an unhandled-exception traceback in the test output.

Frontend (`frontend/src/components/ticket/__tests__/` or co-located with `TicketDetailPage` — follow whichever of `MessagesPanel.test.tsx`/`TicketHistoryPanel.test.tsx` the executor finds still current; `MessagesPanel.test.tsx`'s `mockApi` URL/method-routing helper, Context §20, is this story's closest template since it also covers a load-then-POST-then-refresh cycle):

6. **Initial render with no summary yet.** Mock `GET /api/tickets/:id` returning `ai_summary: null`; render `TicketDetailPage` (or the extracted summary panel, if the executor pulls it into its own component — see the note below); assert "No summary yet." is shown and the button reads "Generate summary".
7. **Regenerate button triggers the POST and updates the display.** Mock the same GET, plus `POST /api/tickets/:id/ai/summary` resolving with an updated `ai_summary`/`ai_summary_generated_at`; click the button; assert the POST fired and the new summary text and generated-at timestamp render, matching `MessagesPanel.test.tsx`'s "sends the composed body ... and refreshes" pattern (Context §20).
8. **Error state doesn't crash the page.** Mock the POST returning a non-2xx `{"detail": "..."}` body; click the button; assert the error text renders (via `ErrorBanner`, giving it `role="alert"` the same way `MessagesPanel`'s existing failed-send test asserts, Context §20's last two tests) and that the rest of the page — specifically, that the tab bar and the other tab labels — are still present and clickable, proving the failure was caught locally and did not propagate to `TicketDetailPage`'s top-level `error` state.

**Executor's call:** the inline `<section>` in Backend/Frontend Tasks §9 above is written directly inside `TicketDetailPage.tsx` for this story's scope (two fields, one button — not enough surface to justify extracting a component yet). If a future story in this arc (e.g. Story 10's suggested replies, which will also need an "AI-generated" badge and a regenerate-style action) makes a shared `AIBadge`/`AISummaryPanel` component worth extracting, that refactor is that story's to do, not this one's — do not speculatively extract a component this story has no second caller for.

---

## Migration / Rollback

- Migration file `backend/alembic/versions/0007_ai_ticket_summaries.py`, `revision = '0007'`, `down_revision = '0006'` (bare-number strings, matching the convention every prior migration in this chain uses).
- Apply with `cd backend && uv run alembic upgrade head`.
- Rollback with `cd backend && uv run alembic downgrade -1` — drops `ai_summary_generated_at` then `ai_summary` from `tickets`. **Does not** remove the `'ai_summary_generated'` label from the `ticket_event_type` Postgres enum — Postgres has no `DROP VALUE` for enums, so that label is permanent once added, even across a downgrade. If a ticket_events row already carries `event_type = 'ai_summary_generated'` at the time of downgrade, that row is untouched and remains readable (the column doesn't disappear, only the two `tickets` columns do) — there is nothing to clean up on that side.
- No data backfill required — both new `tickets` columns are nullable and existing tickets simply have no summary until an agent clicks "Regenerate" for the first time.
- **Half-applied state:** if `upgrade()` fails after `ADD VALUE` but before both `ADD COLUMN`s commit (or vice versa) on a Postgres target, Alembic's transactional wrapping (see `backend/alembic/env.py:37`/`:56`, `context.begin_transaction()`) rolls the whole migration back on Postgres — including the `ALTER TYPE ADD VALUE`, since that statement, run inside the same transaction, is rolled back with everything else on PG 12+. Re-running `alembic upgrade head` from a clean failed state is safe because of the `IF NOT EXISTS` on the `ADD VALUE` statement. On SQLite dev databases (which never run this migration file at all — see Backend Tasks §1's note on `Base.metadata.create_all`), this concern does not apply.

---

## Verification Steps

1. **Backend migration applies:** `cd backend && uv run alembic upgrade head` — succeeds against a Postgres target with `0006` already applied.
2. **Backend tests:** `cd backend && uv run pytest -q` — existing suite still green, new `test_ai_ticket_summaries.py` passes.
3. **Backend serves:** `cd backend && uv run uvicorn app.main:app --reload` — `POST /api/tickets/{id}/ai/summary` with a valid `X-Agent-Id` header against a real ticket returns a populated `ai_summary`; the same request with no header returns 401.
4. **Frontend runs:** `cd frontend && npm run dev` — open a ticket's detail page, confirm the Overview tab shows "No summary yet." with a "Generate summary" button, click it, confirm the summary text and "AI-generated" badge appear and the button now reads "Regenerate".
5. **Frontend tests:** `cd frontend && npm test` — new summary-panel tests pass alongside the existing `TicketDetailPage`/`MessagesPanel` suites.
6. **Regression:** re-run `pytest -q` and `npm test` in full; open the Messages/Notes/Workflow/History tabs on the same ticket to confirm nothing about their rendering changed.

---

## Done Criteria

- [ ] Alembic migration `0007_ai_ticket_summaries.py` adds `ai_summary`/`ai_summary_generated_at` to `tickets` and widens `ticket_event_type` with `'ai_summary_generated'`; `downgrade()` reverses the two columns and documents why the enum label cannot be reversed.
- [ ] `Ticket` model and `TICKET_EVENT_TYPES` in `backend/app/models/ticket.py` carry the new columns and event type; `backend/tests/conftest.py`'s SQLite-via-`metadata.create_all` schema reflects them with no migration involved.
- [ ] `TicketRead`/`TicketEventType` in `backend/app/schemas/ticket.py` expose the two new fields and the new event type; `TicketDetailRead` inherits them with no duplication.
- [ ] `app.services.ai.ticket_summary.generate_summary(db, ticket_id)` loads the ticket and its (possibly empty, possibly truncated) message thread, calls `get_ai_provider().summarize_ticket(...)`, persists both columns, and appends exactly one `ai_summary_generated` ticket_events row per call.
- [ ] `POST /api/tickets/{ticket_id}/ai/summary` (added to `backend/app/api/routes/tickets.py`, not a new router) is gated by `CurrentAgent` (401 without a valid `X-Agent-Id`) and returns the updated `TicketRead`.
- [ ] A raised `AIProviderError` from the provider surfaces as a `502` JSON response, not an unhandled 500 traceback — this story registers the `AIProviderError` → 502 handler in `backend/app/main.py` (Story 08 ships none).
- [ ] `TicketDetailPage`'s Overview tab shows the summary (or "No summary yet."), an "AI-generated" badge, a generated-at timestamp when present, and a "Generate summary"/"Regenerate" button that is the *only* trigger for calling the endpoint — no automatic regeneration on page load.
- [ ] A failed regeneration shows an inline error next to the summary panel and leaves the rest of the ticket detail page (all four other tabs) fully functional.
- [ ] `frontend/src/api/ai.ts` exports `getTicketSummary` and `regenerateTicketSummary`; `frontend/src/types/ticket.ts`'s `Ticket`/`TicketEventType` carry the new fields/value.
- [ ] All new backend tests (`test_ai_ticket_summaries.py`) and new frontend summary-panel tests pass; `pytest -q` and `npm test` stay green in full.

**STOP HERE. Report to the user and wait for confirmation before proceeding to Story 10.**
