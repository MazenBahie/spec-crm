# Story 11 — Automatic Categorization

## Prerequisites

- Story 01 project init completed: backend FastAPI + Alembic scaffold under `backend/app/` and frontend React scaffold under `frontend/src/` are in place.
- Story 03 ticket management completed (migration `backend/alembic/versions/0002_ticket_management.py`) — provides the `Ticket`/`TicketCategory`/`TicketEvent` models and `backend/app/services/tickets.py` this story extends. `agents`, `Ticket.category_id`, `TICKET_EVENT_TYPES` all originate here.
- Story 05 agent dashboard completed — `get_current_agent`/`CurrentAgent`/`OptionalAgent` from `backend/app/api/deps.py` exist, though this story does not end up needing them (see Backend Task 7 for why the new route stays as open as the rest of `backend/app/api/routes/tickets.py`).
- **Story 08 (AI Foundation) completed.** This story depends on it for, and does not redefine:
  - `AIProvider` Protocol in `backend/app/services/ai/provider.py` (modelled on `backend/app/services/channels/driver.py`'s `ChannelDriver`), including a `suggest_category(...)` method.
  - `AnthropicProvider` / `StubAIProvider` implementations of that Protocol.
  - A test-overridable `get_ai_provider()` factory function in the same module.
  - `AIProviderError`, raised by a provider that fails. **Confirmed: Story 08 registers no central handler for it** — `backend/app/main.py`'s `register_exception_handlers` maps only `NotFound`/`Conflict`/`Forbidden`/`PayloadTooLarge`, and Story 08 explicitly leaves `AIProviderError` to each caller. Story 09 (Ticket Summaries), which executes before this story, is the first to need a clean HTTP response for it and registers `AIProviderError` → 502 in `backend/app/main.py` — this story's recompute route (Backend Task 7) reuses that same registration rather than adding a second one. If Story 09 has not landed yet when this story is executed, add the registration here instead, using the identical 502 mapping, so only one exists either way.
  - Settings `anthropic_api_key`, `ai_model`, `ai_enabled` on `backend/app/core/config.py::Settings`.
  - The `backend/app/services/ai/` package itself (with its `__init__.py`) — this story adds a sibling module (`categorization.py`) to it, it does not create the package.
  - **Coordinate with the Story 08 author before implementing:** the exact call signature this story assumes for `AIProvider.suggest_category` (`suggest_category(ticket: Ticket, categories: Sequence[TicketCategory]) -> str | None`, returning the chosen category's `id` as a string, or `None` when the provider can't decide) and the exact HTTP status `AIProviderError` maps to are both assumptions documented below (Backend Task 5 and 7) pending Story 08 landing — reconcile before merging if either differs.
- Story 08's own migration `backend/alembic/versions/0007_ai_ticket_summaries.py` exists with `revision = '0007'`, `down_revision = '0006'` (assumed, not read — a sibling story's file, authored in parallel).

---

## Story Goal

The AI suggests a `TicketCategory` for a ticket — computed best-effort the moment the ticket is created, and recomputable on demand afterwards. The agent sees the suggestion alongside the real category on the ticket's Overview tab, visually labelled as AI-generated, and can apply it with one click (which goes through the existing category-update path so it appends the same `category_changed` history row a manual edit would) or ignore it entirely. No AI call ever blocks or fails ticket creation, and no AI output is ever written to the real `category_id` without that explicit click.

**Out of scope:** re-ranking or scoring multiple candidate categories (the provider returns at most one), suggesting a *new* category that doesn't exist yet, categorizing tickets in bulk/backfill for tickets created before this story, any UI for tuning the AI's confidence threshold.

---

## Context — Read These Files First

1. `.squad/stories/checkout/ai-features/intake.md` — this arc's intake (ticket summaries, suggested replies, automatic categorization, suggested solutions, AI chatbot — this story covers only automatic categorization).
2. `.squad/plans/checkout/08-story-ai-foundation.md` — the sibling story this one depends on for `AIProvider`, `get_ai_provider()`, `AIProviderError`, `StubAIProvider`/`AnthropicProvider`, and the AI settings. Being authored in parallel; confirm its final shape against the assumptions called out in Prerequisites before implementing.
3. `backend/app/services/channels/driver.py` (93 lines, read in full) — the `ChannelDriver` Protocol / `StubDriver` pattern `AIProvider`/`StubAIProvider` are modelled on; understanding it explains why `suggest_category` is expected to be a stateless, session-free call that returns a plain value rather than mutating anything itself.
4. `backend/app/services/channels/service.py:96-166` (`enqueue_outbound`) — the best-effort try/except shape this story's `create_ticket` hook must copy: persist first, call the provider, catch broadly, never let a transport failure reach the caller.
5. `backend/app/services/tickets.py` (read in full, 599 lines) — especially `create_ticket` (334-387), `update_ticket` (390-417), `get_ticket` (304-317, note the `with_relations` `selectinload` options), `list_categories` (195-199), and the module docstring's "every update is last-write-wins" concurrency note (lines 8-12), which this story's recompute-vs-manual-edit race relies on rather than adding new locking.
6. `backend/app/models/ticket.py` (read in full, 200 lines) — `TICKET_EVENT_TYPES` (44-53), `ticket_event_type_enum` (57), `TicketCategory` (78-92), the `Ticket` model's `category_id` FK (107-109) and its `category` relationship (139) — the exact column/relationship style `ai_suggested_category_id` mirrors, and the reason it can't mirror it *verbatim* (see Backend Task 2).
7. `backend/app/schemas/ticket.py` (read in full, 186 lines) — `TicketEventType` Literal (17-26, must stay in sync with the model's tuple), `TicketRead` (114-133), `TicketDetailRead` (136-141), `TicketUpdate` (98-111).
8. `backend/app/api/routes/tickets.py` (read in full, 281 lines) — router pattern (no router-level auth dependency; individual routes opt into `CurrentAgent`/`OptionalAgent` only when they need an actor, e.g. the notes routes at 169-194), `update_ticket` route (90-92), `get_ticket` route (84-87).
9. `backend/app/services/errors.py` — `NotFound`/`Conflict`/`Forbidden`/`PayloadTooLarge`, no `Error` suffix.
10. `backend/alembic/versions/0006_knowledge_base.py` (read in full) — migration style precedent: bare-number `revision`/`down_revision` strings, `sa.Column`/index/FK style. Note it only ever does `op.create_table`; this story's `0008` is the first migration in the codebase to `op.add_column` an existing table, so there is no direct precedent for that half — see Backend Task 1 for the reasoning applied instead.
11. `backend/app/db/base.py` — `Base` declares no `naming_convention` on its metadata, which is why Backend Task 1 passes `None` (not a generated `op.f(...)` name) to `op.create_foreign_key`.
12. `backend/tests/conftest.py:211-234` — `ticket_category` and `ticket` fixtures, reused by this story's tests.
13. `backend/tests/test_ticket_notes.py:21-34` — the `monkeypatch.setattr("app.services.channels.service.get_driver", fake_get_driver)` pattern; this story's tests override `app.services.ai.categorization.get_ai_provider` the same way, module-path monkeypatching rather than a FastAPI dependency override.
14. `frontend/src/pages/TicketDetailPage.tsx` (read in full, 182 lines) — `TABS` (14), the Category field in the Overview tab (`ticket.category?.name ?? "—"`, line 146) this story's suggestion UI sits next to.
15. `frontend/src/api/tickets.ts` (read in full, 181 lines) — `getTicket` (41-43), `updateTicket` (52-57, the PATCH function reused to "apply" a suggestion), `listCategories` (128-132, reused by the new frontend component to detect "no categories configured").
16. `frontend/src/api/client.ts` — `request`/`buildQuery`, the pattern for the new `frontend/src/api/ai.ts`.
17. `frontend/src/components/ticket/TicketWorkflowPanel.tsx` and `frontend/src/components/ticket/__tests__/TicketWorkflowPanel.test.tsx` — precedent for a small ticket-scoped panel component (own `useEffect` fetch, `ErrorBanner`, `styles`/`tokens` from `../ui`) and its Vitest `mockApi`-over-`fetch` test style; this story's `CategorySuggestion.tsx` and its test mirror both.
18. `frontend/src/types/ticket.ts` (read in full) — `Ticket`/`TicketDetail` interfaces to extend, `TicketCategory` interface reused as-is.

---

## Backend Tasks

### 1 — Migration

Create file: `backend/alembic/versions/0008_ai_categorization.py`

```python
revision: str = '0008'
down_revision: Union[str, None] = '0007'
```

- `op.add_column('tickets', sa.Column('ai_suggested_category_id', sa.Uuid(), nullable=True))` — this is the first migration in the codebase to alter an existing table rather than create a new one (every prior migration, `0001`-`0007`, only does `op.create_table`), so there is no `add_column`/`create_foreign_key` precedent to copy verbatim; the style below extrapolates from `0006`'s `sa.Column`/FK conventions.
- `op.create_index(op.f('ix_tickets_ai_suggested_category_id'), 'tickets', ['ai_suggested_category_id'], unique=False)` — matches the existing index on `category_id`.
- `op.create_foreign_key(None, 'tickets', 'ticket_categories', ['ai_suggested_category_id'], ['id'], ondelete='SET NULL')` — pass `None`, not a generated `op.f(...)` name: `backend/app/db/base.py`'s `Base` declares no `naming_convention` on its metadata, so there is no convention-derived name to reference (unlike a `create_table`'s inline `sa.ForeignKeyConstraint`, which never needs a separate name at all); Postgres assigns its own default constraint name.
- `op.execute("ALTER TYPE ticket_event_type ADD VALUE IF NOT EXISTS 'ai_category_suggested'")` — adds the new `TicketEvent.event_type` value (see Backend Task 2) to the named Postgres enum. Assumes Postgres 12+ (the project's existing target); `ADD VALUE` is safe inside Alembic's transaction as long as the new label is not *used* in the same transaction, which this migration never does.
- `downgrade()` drops the FK, the index, then the column, in that order (reverse of creation). It does **not** attempt to remove `'ai_category_suggested'` from `ticket_event_type` — Postgres has no `ALTER TYPE ... DROP VALUE`; the only way to remove an enum label is to rebuild the type from scratch, which is out of scope for a purely additive story. This is documented as an accepted one-way step in Migration / Rollback below, not an oversight.

### 2 — Model changes

Edit `backend/app/models/ticket.py`:

- Append `"ai_category_suggested"` to `TICKET_EVENT_TYPES` (line 44-53), after `"commented"`. This changes what `ticket_event_type_enum` accepts. On the SQLite test database this needs nothing further — `sqlalchemy.Enum` validates the Python-side tuple against whatever `Base.metadata.create_all()` builds at test-collection time, and there is no separately-versioned Postgres type to keep in sync there. On a real Postgres database, only the migration's `ALTER TYPE ... ADD VALUE` (Backend Task 1) makes the new value legal — the Python tuple change alone does nothing there, mirroring the "seeded reference data needs both paths" contract from `.squad/plans/checkout/00-overview.md`.
- Also append `"ai_category_suggested"` to the `TicketEventType` Literal in `backend/app/schemas/ticket.py:17-26` — Pydantic validates `TicketEventRead.event_type` against this Literal independently of the SQLAlchemy enum, and a mismatch here would make the new event type fail to serialize even though the DB happily stores it.
- Add the new column, right after `category_id` (line 107-109) for locality:
  ```python
  ai_suggested_category_id: Mapped[uuid.UUID | None] = mapped_column(
      ForeignKey("ticket_categories.id", ondelete="SET NULL"), index=True
  )
  ```
  This is a second FK from `tickets` to `ticket_categories`, which the existing `category` relationship (line 139) does not anticipate:
  ```python
  category: Mapped[TicketCategory | None] = relationship()
  ```
  With two FK columns pointing at the same target table, SQLAlchemy cannot infer which one `category` should join on and raises `AmbiguousForeignKeysError` at mapper-configuration time (i.e. at import time, breaking every test) unless both relationships disambiguate explicitly. Change the existing line to:
  ```python
  category: Mapped[TicketCategory | None] = relationship(foreign_keys=[category_id])
  ```
  and add:
  ```python
  ai_suggested_category: Mapped[TicketCategory | None] = relationship(
      foreign_keys=[ai_suggested_category_id]
  )
  ```
  This is the one place `category_id`'s own definition is touched by this story, and it is a required change, not an optional cleanup — the app will not start without it once the second FK exists.

### 3 — Eager loading

Edit `backend/app/services/tickets.py::get_ticket` (304-317): add `selectinload(Ticket.ai_suggested_category)` alongside the existing `selectinload(Ticket.customer)`, `selectinload(Ticket.category)`, `selectinload(Ticket.assignee)` inside the `with_relations` branch. Both the existing `GET /tickets/{id}` route and the new recompute route (Backend Task 7) call `get_ticket(db, ticket_id, with_relations=True)`, so this one change is what lets `TicketDetailRead.ai_suggested_category` (Backend Task 4) serialize without a second query — the suggestion rides along on the ticket the frontend already fetches, no dedicated "get suggestion" endpoint needed.

### 4 — Schemas

Edit `backend/app/schemas/ticket.py`:

- `TicketRead` (114-133): add `ai_suggested_category_id: uuid.UUID | None`, next to `category_id`.
- `TicketDetailRead` (136-141): add `ai_suggested_category: TicketCategoryRead | None`, next to `category`.

No new schema module. `TicketUpdate` (98-111) is deliberately left untouched — applying a suggestion goes through its existing `category_id` field (Backend Task 8), and `ai_suggested_category_id` is never client-writable.

### 5 — Service module

Create file: `backend/app/services/ai/categorization.py`

```python
"""AI-assisted ticket categorization.

Mirrors the shape of app.services.channels.service.enqueue_outbound: the
provider call is a plain, session-free function behind the AIProvider
Protocol (see app.services.ai.provider, Story 08), and this module's job is
to fetch what the provider needs, validate what it hands back, and write the
outcome onto the row -- never to trust the provider's answer as a foreign key
without checking it first.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from app.models.ticket import Ticket, TicketCategory, TicketEvent
from app.services.ai.provider import get_ai_provider
from app.services.tickets import get_ticket, list_categories

logger = logging.getLogger(__name__)


def _match_category(
    raw: str | None, categories: list[TicketCategory]
) -> TicketCategory | None:
    """Validate the provider's answer against the exact list it was offered.

    The provider is a Protocol boundary around a third-party model, and
    nothing stops it echoing back a category name instead of an id, an id
    that belonged to a category deactivated moments ago, or an outright
    hallucination. Matching against `categories` -- the very list passed
    into suggest_category, not a fresh query -- means a match can only ever
    be one of the options the provider was actually given.
    """
    if not raw:
        return None
    try:
        candidate_id = uuid.UUID(raw)
    except ValueError:
        return None
    for category in categories:
        if category.id == candidate_id:
            return category
    return None


def suggest_category(db: Session, ticket_id: uuid.UUID) -> TicketCategory | None:
    """Compute (and persist) the AI's category suggestion for one ticket.

    Returns the matched TicketCategory, or None when there is nothing to
    suggest -- no active categories exist, the provider declined to answer,
    or its answer didn't match a real category. None is a valid, silent
    outcome here; callers that need to surface a *failure* (as opposed to
    "no suggestion") should let AIProviderError propagate instead of calling
    this inside a broad try/except -- see the two call sites in
    app.services.tickets.create_ticket and app.api.routes.tickets.
    """
    ticket = get_ticket(db, ticket_id)
    categories = list_categories(db, active_only=True)

    if not categories:
        # Short-circuit before the provider call: there is nothing to choose
        # between, so asking would only spend a real API call (when
        # AnthropicProvider is wired up) to learn what we already know.
        match = None
    else:
        raw = get_ai_provider().suggest_category(ticket, categories)
        match = _match_category(raw, categories)

    old_id = ticket.ai_suggested_category_id
    new_id = match.id if match else None
    if new_id != old_id:
        ticket.ai_suggested_category_id = new_id
        db.add(
            TicketEvent(
                ticket_id=ticket.id,
                event_type="ai_category_suggested",
                field="ai_suggested_category_id",
                old_value=str(old_id) if old_id else None,
                new_value=str(new_id) if new_id else None,
            )
        )
    db.flush()
    return match
```

Design decisions, made explicit per the story brief:

- **A lightweight `TicketEvent` *is* recorded for the suggestion itself** (`event_type="ai_category_suggested"`), which is why `TICKET_EVENT_TYPES` gained the new value in Backend Task 2 rather than staying unused. The alternative — recording nothing until the agent applies a suggestion — would mean an agent looking at History could never tell *when* the AI last looked at a ticket or what it said before they overrode it. The event is only appended when the computed value actually changes (`new_id != old_id`), so recomputing repeatedly with an unchanged answer (a very likely UI interaction — the agent clicking "Recompute" out of curiosity) does not spam the ticket's history the way it would if every call wrote a row unconditionally.
- This does **not** use `app.services.tickets._record` — that helper is prefixed `_` inside `tickets.py`, signalling module-private intent, so `categorization.py` builds its own `TicketEvent` row directly instead of reaching across module boundaries for a private helper.
- `suggest_category`'s own `AIProviderError` (raised by `get_ai_provider().suggest_category(...)` when the provider fails) is **not** caught here. Whether that failure should vanish (the `create_ticket` hook, Backend Task 6) or surface (the on-demand recompute route, Backend Task 7) is a decision that belongs to each caller, not to this shared function.

### 6 — Hook into `create_ticket`

Edit `backend/app/services/tickets.py`:

- Add `import logging` and `logger = logging.getLogger(__name__)` near the top of the file (it currently has neither) — mirroring `backend/app/services/channels/service.py:17,30` (its own `logger = logging.getLogger(__name__)`).
- At the end of `create_ticket` (334-387), immediately before the final `return ticket`, add:

```python
    # Best-effort, mirroring app.services.channels.service.enqueue_outbound:
    # a category suggestion is a nice-to-have, never a precondition for the
    # ticket to exist. Unlike enqueue_outbound this catches every exception,
    # including ServiceError -- enqueue_outbound re-raises ServiceError
    # because those signal the *caller's* mistake (an unknown channel slug);
    # here the ticket and its categories are already validated by the time
    # we reach this line, so there is no legitimate precondition failure left
    # to surface, and every exception (AIProviderError, a network timeout, a
    # misconfigured key) is the provider's problem, not the caller's.
    try:
        from app.services.ai import categorization as ai_categorization

        ai_categorization.suggest_category(db, ticket.id)
    except Exception as exc:
        logger.warning(
            "AI category suggestion failed for ticket %s: %s", ticket.id, exc
        )

    return ticket
```

  The `import` is deliberately placed inside the function, not at module level: `app.services.ai.categorization` imports `get_ticket`/`list_categories` from `app.services.tickets` (Backend Task 5), so a module-level `from app.services.ai import categorization` at the top of `tickets.py` would be a circular import (`tickets.py` → `ai/categorization.py` → `tickets.py`). Deferring the import to call time, inside the function body, breaks the cycle the same way Python code elsewhere resolves this class of dependency — by the time `create_ticket` actually runs, both modules have already finished importing.
- `suggest_category` itself calls `db.flush()` but not `db.refresh()`; that's fine here because it mutates the same `Ticket` Python object already held by `create_ticket` (same `Session`, same identity map), so the attribute change is visible on `ticket` without an extra refresh.

### 7 — Route: recompute on demand

Edit `backend/app/api/routes/tickets.py`: add `from app.services.ai import categorization as ai_categorization` at module level (safe here — routes modules are never imported by the service layer, so there's no cycle the way there was in Task 6).

```python
@router.post(
    "/tickets/{ticket_id}/ai/suggested-category", response_model=TicketDetailRead
)
def recompute_suggested_category(ticket_id: uuid.UUID, db: DbDep) -> TicketDetailRead:
    """Recompute the AI category suggestion on demand.

    Unlike the best-effort hook in create_ticket, this is an explicit,
    single-purpose agent action with nothing else at stake: if the provider
    is unavailable or misconfigured, AIProviderError is allowed to propagate
    rather than being swallowed, so the agent who clicked "Recompute" sees
    that it failed instead of silently seeing nothing change. Story 08 itself
    maps nothing centrally; this relies on the AIProviderError -> 502
    handler Story 09 registers in app.main (or, if Story 09 has not landed
    yet, the one this story's executor adds here using the identical
    mapping -- see Prerequisites).
    """
    ai_categorization.suggest_category(db, ticket_id)
    ticket = svc.get_ticket(db, ticket_id, with_relations=True)
    return TicketDetailRead.model_validate(ticket)
```

No router-level or route-level agent auth dependency: `backend/app/api/routes/tickets.py`'s router carries none (`backend/app/main.py`'s comment: "the pre-existing routers stay open"), and unlike the notes routes (which need `CurrentAgent` because a note has an author) this route attributes nothing to an agent — the `TicketEvent` it may write has `actor=None`, matching `_record`'s default. It stays exactly as open as `PATCH /tickets/{id}` and every other route already in this file.

`response_model=TicketDetailRead` (not `TicketRead`, unlike every other action route in this file) is deliberate: the frontend needs the nested `ai_suggested_category.name` immediately to render the suggestion without a second round-trip, and `TicketDetailRead` is already the shape `GET /tickets/{id}` returns.

### 8 — Applying a suggestion (no new endpoint)

No "apply" route is added. Applying is `PATCH /tickets/{id}` with `{"category_id": "<the ai_suggested_category_id value>"}`, which already goes through `update_ticket` (`backend/app/services/tickets.py:390-417`) and already appends a `category_changed` `TicketEvent` when `category_id` changes (409-413) — exactly the history entry a manual category edit produces, which is the point: applying an AI suggestion should look, in History, indistinguishable from an agent picking the same category by hand.

One change to `update_ticket` is needed for the stale-suggestion edge case (see Edge Cases below): whenever the payload touches `category_id` at all —

```python
    if "category_id" in data:
        ticket.ai_suggested_category_id = None
```

— placed alongside the existing `if "category_id" in data and data["category_id"] is not None: _get_active_category(...)` validation block (395-396), clearing the suggestion regardless of whether the new value came from clicking "Apply" (in which case it now equals what was just cleared — harmless, there is nothing left to apply) or from an unrelated manual edit (in which case the suggestion no longer describes the ticket's current state and showing it would be misleading). This is a single unconditional clear on any `category_id` write, not two special cases.

---

## Frontend Tasks

### 9 — Types

Edit `frontend/src/types/ticket.ts`:

- `Ticket` interface (73-91): add `ai_suggested_category_id: string | null`.
- `TicketDetail` interface (93-102): add `ai_suggested_category: TicketCategory | null`.

### 10 — API client

Create file: `frontend/src/api/ai.ts`

```ts
/** Typed wrapper for the one AI-categorization endpoint this story adds. */

import { request } from "./client";
import type { TicketDetail } from "../types/ticket";

export function recomputeSuggestedCategory(ticketId: string): Promise<TicketDetail> {
  return request<TicketDetail>(`/tickets/${ticketId}/ai/suggested-category`, {
    method: "POST",
  });
}
```

No `getSuggestedCategory` function: `ai_suggested_category` is now part of `TicketDetailRead` (Backend Task 4), so it already arrives on every `getTicket(id)` response (`frontend/src/api/tickets.ts:41-43`) — a dedicated fetch would just be `getTicket` again under a different name.

### 11 — New component

Create file: `frontend/src/components/ticket/CategorySuggestion.tsx`

Mirrors `TicketWorkflowPanel.tsx`'s shape (own `useEffect` fetch, `ErrorBanner`/`styles`/`tokens` from `../ui`, a `busy` flag around each async action):

```tsx
import { useEffect, useState } from "react";

import { recomputeSuggestedCategory } from "../../api/ai";
import { listCategories, updateTicket } from "../../api/tickets";
import { ErrorBanner, styles, tokens } from "../ui";
import type { TicketDetail } from "../../types/ticket";

interface Props {
  ticket: TicketDetail;
  onChanged: () => void;
}

export default function CategorySuggestion({ ticket, onChanged }: Props) {
  const [anyCategories, setAnyCategories] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listCategories({ activeOnly: true })
      .then((cats) => setAnyCategories(cats.length > 0))
      .catch(() => setAnyCategories(false));
  }, []);

  // Nothing configured to suggest from -- suppress the whole control, Apply
  // button included, rather than show a recompute button that can only ever
  // come back empty.
  if (!anyCategories) return null;

  const suggestion = ticket.ai_suggested_category;
  const alreadyCurrent = suggestion !== null && suggestion.id === ticket.category_id;

  async function handleRecompute() {
    setBusy(true);
    setError(null);
    try {
      await recomputeSuggestedCategory(ticket.id);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleApply() {
    if (!suggestion) return;
    setBusy(true);
    setError(null);
    try {
      await updateTicket(ticket.id, { category_id: suggestion.id });
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ marginTop: "0.4rem" }}>
      <ErrorBanner message={error} />
      {suggestion && !alreadyCurrent && (
        <p style={{ margin: "0 0 0.4rem", ...styles.muted }}>
          <span
            style={{
              border: `1px dashed ${tokens.accent}`,
              borderRadius: 4,
              padding: "0 4px",
              fontSize: "0.75rem",
              marginRight: "0.4rem",
            }}
            title="AI-generated suggestion"
          >
            AI
          </span>
          Suggests: {suggestion.name}{" "}
          <button type="button" style={styles.button} disabled={busy} onClick={() => void handleApply()}>
            Apply
          </button>
        </p>
      )}
      <button
        type="button"
        style={{ ...styles.button, fontSize: "0.8rem" }}
        disabled={busy}
        onClick={() => void handleRecompute()}
      >
        {suggestion ? "Recompute suggestion" : "Suggest category"}
      </button>
    </div>
  );
}
```

The `AI` tag (dashed border, explicit `title`) is the "visibly distinct from the actual assigned category" labelling the story arc requires everywhere AI content is shown — it sits inline with the suggestion text, never merged into the real Category value above it.

### 12 — Wiring into `TicketDetailPage.tsx`

Edit the Overview tab's Category block (`frontend/src/pages/TicketDetailPage.tsx:145-146`):

```tsx
              <dt style={styles.label}>Category</dt>
              <dd style={{ margin: "0 0 0.75rem" }}>
                {ticket.category?.name ?? "—"}
                <CategorySuggestion ticket={ticket} onChanged={() => void load()} />
              </dd>
```

with `import CategorySuggestion from "../components/ticket/CategorySuggestion";` added alongside the other component imports (4-8). `onChanged={() => void load()}` reuses the page's existing `load` callback (27-38) exactly the way `TicketWorkflowPanel`'s `onChanged` prop already does (172) — both recompute and apply just refetch the ticket, no separate local state needed in the page itself.

---

## Edge Cases & Failure Modes

- **No categories configured at all** — `suggest_category` (`backend/app/services/ai/categorization.py`) checks `if not categories` before calling `get_ai_provider()` at all, so an empty `ticket_categories` table never spends a provider call. On the frontend, `CategorySuggestion` independently fetches `listCategories({ activeOnly: true })` and renders nothing (not even the "Suggest category" button) when it's empty — belt-and-suspenders, since the backend's own short-circuit means even a stray click there would just come back with `ai_suggested_category: null`.
- **Suggested category already equals the current one** — can happen without any `update_ticket` call at all (e.g. a ticket created with `category_id` already set by the agent, and the AI's first suggestion independently agrees). `CategorySuggestion` computes `alreadyCurrent` and hides the entire suggestion line (not just the Apply button) in that case — there is nothing distinct left to show once they match, and leaving a redundant "AI suggests: Billing" next to "Category: Billing" would just be noise, not a decision to make.
- **Agent manually changes the category after a suggestion exists** — the suggestion is cleared, not left stale. `update_ticket` sets `ticket.ai_suggested_category_id = None` whenever `"category_id"` is present in the payload at all (Backend Task 8), whether that PATCH came from clicking Apply (the suggestion is now redundant with reality) or from an unrelated manual edit (the suggestion no longer describes the ticket's current state, and leaving the AI's old opinion visible next to a category it never saw would be actively misleading). A fresh suggestion only ever reappears via an explicit "Recompute" click.
- **AI returns a category id (or name, or garbage) that doesn't match any real category** — `_match_category` in `categorization.py` only accepts a value that parses as a UUID *and* is present in the exact `categories` list handed to the provider for that call. Anything else — a made-up id, a deactivated category's id, a category name instead of an id, an empty string — is discarded and stored as `None`, never written through as a foreign key. A hallucination degrades to "no suggestion", not a 500 or an integrity error.
- **AI disabled or unconfigured** — `get_ai_provider()` (Story 08) returns `StubAIProvider` whenever `ai_enabled` is false or no API key is configured. `suggest_category` calls it exactly the same way regardless of which implementation comes back; the Protocol boundary (mirroring `ChannelDriver`/`StubDriver`) is what makes this degrade automatically, with no special-casing needed in this story's code.
- **The provider raises during ticket creation** (timeout, `AIProviderError`, network failure) — caught broadly in the `create_ticket` hook (Backend Task 6), logged at `warning`, and never re-raised. The ticket is still created and the response is still `201`; `ai_suggested_category_id` simply stays `None` on that ticket until a manual recompute succeeds.
- **The provider raises during an explicit recompute** — deliberately *not* swallowed by the route (Backend Task 7): the agent asked for this, so a failure should be visible rather than silently doing nothing.
- **Repeated recompute producing the same answer** — `suggest_category` only writes a new `ai_category_suggested` `TicketEvent` (and only touches `ai_suggested_category_id`) when the matched category's id actually differs from what was already stored, so clicking "Recompute" twice in a row with an unchanged answer doesn't spam the ticket's History tab.
- **A new named-enum value that can't be un-added** — `ALTER TYPE ticket_event_type ADD VALUE` (Backend Task 1) has no Postgres-side reversal; `downgrade()` intentionally leaves the label in place after dropping the column, same category of one-way step as Story 07's own migration notes about named enums, just in the opposite direction (can't add there without a migration; can't remove here without one either).
- **Circular import between `app.services.tickets` and `app.services.ai.categorization`** — `categorization.py` imports `get_ticket`/`list_categories` from `tickets.py` at module level; `tickets.py`'s `create_ticket` needs `categorization.suggest_category` but imports it inside the function body instead of at module top, breaking the cycle (Backend Task 6). The route layer (`app/api/routes/tickets.py`) has no such constraint and imports it normally at module level (Backend Task 7).
- **Recompute racing a manual PATCH** — no new locking is introduced; this follows the same "every update is last-write-wins" stance the rest of `tickets.py` already documents (module docstring, lines 8-12) — whichever request's `db.flush()` lands last wins the row, and (per the point above) either outcome still leaves a readable `TicketEvent` behind.

---

## Test Plan

Backend — create `backend/tests/test_ai_categorization.py`, using the `ticket_category`/`ticket` fixtures (`backend/tests/conftest.py:211-234`) and the `monkeypatch.setattr("app.services.ai.categorization.get_ai_provider", ...)` pattern from `backend/tests/test_ticket_notes.py:21-34`:

1. `test_suggest_category_stores_stub_match` — monkeypatch `get_ai_provider` to a fake returning the `ticket_category` fixture's id; call `suggest_category(db, ticket_id)` (or hit the recompute route); assert `ai_suggested_category_id` is set and one `ai_category_suggested` `TicketEvent` exists.
2. `test_suggest_category_short_circuits_with_no_categories` — no `ticket_category` fixture used (table empty); monkeypatch `get_ai_provider` to a spy that raises `AssertionError` if called at all; assert `suggest_category` returns `None` and the spy was never invoked.
3. `test_create_ticket_succeeds_when_ai_provider_raises` — monkeypatch `get_ai_provider` to a fake whose `suggest_category` raises `AIProviderError`; `POST /api/tickets` still returns `201`; the created ticket's `ai_suggested_category_id` is `null`.
4. `test_recompute_route_propagates_provider_failure` — same fake as above, but via `POST /api/tickets/{id}/ai/suggested-category`; assert it returns `502` (the `AIProviderError` handler registered in `app.main`, by Story 09 or by this story if Story 09 has not landed yet — see Prerequisites), not `200`/`201`.
5. `test_apply_suggestion_records_category_changed_and_clears_suggestion` — set a suggestion (via `suggest_category` with a monkeypatched provider), then `PATCH /api/tickets/{id}` with `category_id` equal to the suggested id; assert `GET /api/tickets/{id}/events` now contains a `category_changed` row and the ticket's `ai_suggested_category_id` is `null` afterwards.
6. `test_hallucinated_category_id_is_discarded` — monkeypatch the provider to return `str(uuid.uuid4())` (not any real category's id); assert `suggest_category` returns `None` and `ai_suggested_category_id` stays `None`.
7. `test_manual_category_change_clears_stale_suggestion` — set a suggestion pointing at category A, then `PATCH /api/tickets/{id}` with `category_id` set to a *different* category B; assert `ai_suggested_category_id` is `null` afterwards (not silently left pointing at A).

Frontend — create `frontend/src/components/ticket/__tests__/CategorySuggestion.test.tsx`, mirroring `TicketWorkflowPanel.test.tsx`'s `mockApi`-over-`fetch` harness and fixture-shaped `ticket()`/`agent()` helpers:

8. Renders "Suggests: <name>" with the AI tag and an Apply button when `ai_suggested_category` is present and differs from `category`.
9. Clicking Apply calls `PATCH /tickets/:id` with `{ category_id: <suggested id> }` and then the `onChanged` callback.
10. Hides the suggestion line (but still shows the recompute button) when `ai_suggested_category.id === category_id`.
11. Renders nothing at all when `listCategories` resolves to `[]`.
12. Clicking "Suggest category" / "Recompute suggestion" calls `POST /tickets/:id/ai/suggested-category`.

---

## Migration / Rollback

- Migration file `backend/alembic/versions/0008_ai_categorization.py`, `revision = '0008'`, `down_revision = '0007'`.
- Apply: `alembic upgrade head` from `backend/`. Adds `tickets.ai_suggested_category_id` (nullable, FK to `ticket_categories.id` ON DELETE SET NULL, indexed) and the `'ai_category_suggested'` value on the `ticket_event_type` Postgres enum.
- Rollback: `alembic downgrade -1` drops the FK, the index, and the column — no data loss, since the column is purely advisory (never a source of truth for the real `category_id`). The `'ai_category_suggested'` enum label is **not** removed by `downgrade()` — Postgres has no `DROP VALUE`; the label stays defined but simply becomes unused again, which is harmless (an enum with an extra unused member behaves identically to one without it for every other value already in the codebase).
- No data backfill: existing tickets get `ai_suggested_category_id = NULL`, which behaves exactly like "no suggestion yet" — the same state a newly created ticket has before its own best-effort suggestion lands.

---

## Verification Steps

1. **Backend builds:** `cd backend && uv run alembic upgrade head` — migration applies cleanly, including the `ALTER TYPE` statement.
2. **Backend tests:** `cd backend && uv run pytest -q` — all existing tests still pass; `test_ai_categorization.py` passes.
3. **Backend serves, AI disabled:** `cd backend && uv run uvicorn app.main:app --reload` — with no `CRM_ANTHROPIC_API_KEY` configured (or `CRM_AI_ENABLED=false`), `POST /api/tickets` still returns `201` and the created ticket's `ai_suggested_category_id` is `null` or a `StubAIProvider`-derived value, never a 5xx.
4. **Recompute manually:** with at least one category created via `POST /api/ticket-categories`, `POST /api/tickets/{id}/ai/suggested-category` returns a `TicketDetailRead` with `ai_suggested_category` populated (or `null` if the stub/provider declines).
5. **Apply via the existing PATCH:** `PATCH /api/tickets/{id}` with `{"category_id": "<ai_suggested_category_id>"}` succeeds, `GET /api/tickets/{id}/events` shows a new `category_changed` row, and a follow-up `GET /api/tickets/{id}` shows `ai_suggested_category: null`.
6. **Frontend runs:** `cd frontend && npm run dev` — open a ticket's Overview tab, see the AI-labelled suggestion next to Category (when one exists), click Apply, confirm the real Category updates and the suggestion line disappears.
7. **Frontend tests:** `cd frontend && npm test` — `CategorySuggestion.test.tsx` and all existing suites pass.

---

## Done Criteria

- [ ] Alembic migration `0008_ai_categorization.py` adds `tickets.ai_suggested_category_id` (nullable FK, ON DELETE SET NULL, indexed) and the `ai_category_suggested` enum value; `downgrade()` cleanly reverses the column/FK/index (the enum value is documented, not silently forgotten, as a one-way addition).
- [ ] `Ticket.category` and `Ticket.ai_suggested_category` both resolve correctly with explicit `foreign_keys=` — no `AmbiguousForeignKeysError` at import time.
- [ ] `create_ticket` triggers a best-effort category suggestion that never prevents a ticket from being created, proven by a test that makes the provider raise.
- [ ] `POST /tickets/{id}/ai/suggested-category` recomputes on demand and lets a provider failure propagate (unlike the creation-time hook).
- [ ] Applying a suggestion is just `PATCH /tickets/{id}` with `category_id` set to the suggested value — no new "apply" endpoint exists — and it records the same `category_changed` event a manual edit would.
- [ ] A hallucinated or stale category id from the provider is never stored as `ai_suggested_category_id`; only ids present in the exact category list offered to the provider are accepted.
- [ ] Manually changing `category_id` via `update_ticket` clears any existing `ai_suggested_category_id`.
- [ ] The frontend suppresses the entire suggestion UI when no categories are configured, and hides the Apply button (but not the recompute control) when the suggestion already matches the current category.
- [ ] The AI-generated suggestion is visually labelled and never auto-applied — `category_id` only changes via an explicit Apply click going through the existing PATCH path.
- [ ] All new backend tests (`test_ai_categorization.py`) and the new frontend test (`CategorySuggestion.test.tsx`) pass, alongside every pre-existing suite.

**STOP HERE. Report to the user and wait for confirmation before proceeding to Story 12.**
