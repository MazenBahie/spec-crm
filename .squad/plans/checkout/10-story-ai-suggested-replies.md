# Story 10 — Suggested Replies

## Prerequisites

- Stories 01–07 completed (existing scaffold): `backend/app/main.py`, the Alembic chain through `0006_knowledge_base.py`, and the React shell under `frontend/src/`.
- Story 04 Communication Channels completed — provides `ChannelMessage` (`backend/app/models/channel.py:101-149`, fields include `direction: "inbound" | "outbound"` and `body`) and `list_messages_for_ticket(db, ticket_id, *, limit=200, offset=0) -> tuple[list[ChannelMessage], int]` (`backend/app/services/channels/service.py:74-93`), which internally calls `get_ticket(db, ticket_id)` for its own 404 semantics.
- Story 05 Agent Dashboard completed — provides `get_current_agent`/`CurrentAgent`/`OptionalAgent` (`backend/app/api/deps.py:47-85`), the `X-Agent-Id` placeholder auth every agent-scoped router depends on.
- **Story 08 AI Foundation completed.** This story is entirely built on top of it and defines nothing about the provider itself. Story 08 is being authored in parallel with this file, so the exact file/line citations below could not be verified against merged code — confirm them before starting and adjust names only if Story 08 landed differently:
  - An `AIProvider` Protocol in `backend/app/services/ai/provider.py`, modelled on `ChannelDriver` (`backend/app/services/channels/driver.py:43-61` — a `runtime_checkable` `Protocol` with a `slug: ClassVar[str]` and methods that take plain domain objects and return a plain value, no FastAPI or session involved). It exposes `suggest_reply(self, ticket: Ticket, messages: Sequence[ChannelMessage]) -> str` — real ORM rows, matching `ChannelDriver.send`'s own precedent.
  - `AnthropicProvider` and `StubAIProvider` implementations, and `get_ai_provider() -> AIProvider` — a **plain, zero-argument module-level function, not a FastAPI dependency** (Story 08's own `provider.py` docstring: the service layer stays FastAPI-free by this codebase's convention, `app/api/deps.py:10-12`). Callers import the module (`from app.services.ai import provider as ai_provider`) and call `ai_provider.get_ai_provider()` so a test's `monkeypatch.setattr(ai_provider, "get_ai_provider", fake_factory)` takes effect — a bare-name import would not observe the monkeypatch. This is **not** the `get_storage()`/`dependency_overrides` pattern (`backend/tests/conftest.py:70-94`) — that mechanism is for route-level dependencies, and nothing at route level in this story ever receives or forwards the provider.
  - `StubAIProvider` is what `get_ai_provider()` returns whenever AI is disabled or unconfigured (`settings.ai_enabled` is false or `settings.anthropic_api_key` is unset) — this story never checks those settings itself, it only ever calls `get_ai_provider()` and uses whatever comes back.
  - An `AIProviderError` exception for provider-level failures. **Confirmed (not an open question):** Story 08 registers no central handler for it in `backend/app/main.py` and explicitly leaves the decision to each caller. Backend Tasks §1 below catches it locally and falls back to `StubAIProvider` output rather than surfacing a 5xx — this is the required behavior for this specific feature (an optional, always-human-reviewed suggestion), not a placeholder.
  - Settings `anthropic_api_key`, `ai_model`, `ai_enabled` added to `backend/app/core/config.py` (today a plain `Settings(BaseSettings)` with no AI fields — `backend/app/core/config.py:1-20`).

---

## Story Goal

An agent working a ticket can click **"Suggest a reply"** while composing a message. The system builds context from the ticket and its message thread, asks the configured AI provider for a draft reply, and inserts that draft into the compose box as **editable text** — nothing is sent, and nothing on the ticket record changes, until the agent reviews it and presses the existing Send button themselves.

This story adds **no persistence and no schema change**: a suggestion is a same-request round trip (build context → call the provider → return a string) that is never written to the database. There is no new `TicketEvent` type and no new table; `## Migration / Rollback` is intentionally omitted from this file.

**The central, non-negotiable constraint:** no AI output is ever auto-applied or auto-sent.
- The backend route returns draft text and nothing else — it never calls the existing send-message path (`enqueue_outbound` / `POST /tickets/{ticket_id}/messages`, `backend/app/services/channels/service.py:96-166`) on the agent's behalf.
- The frontend only ever inserts the draft into the compose box's existing state, exactly where a quick reply lands today. There is no "send suggested reply" one-click action anywhere in this story — sending still requires the agent to press the pre-existing "Send" button (`frontend/src/components/ticket/MessagesPanel.tsx:177-183`), which is unchanged by this story.
- The suggestion is visibly labelled as AI-drafted while it sits in the compose box, so the agent is never in doubt about what they are about to send.

**Out of scope:** ticket summaries, categorization, suggested solutions, and the chatbot (Stories 11-13); streaming responses; multi-turn refinement of a suggestion; persisting suggestions or logging them anywhere; rate-limiting AI calls beyond disabling the button while one is in flight.

---

## Context — Read These Files First

1. `.squad/stories/checkout/ai-features/intake.md` — the arc's intake (ticket summaries, suggested replies, automatic categorization, suggested solutions, AI chatbot — this story covers only "Suggested replies").
2. `.squad/plans/checkout/08-story-ai-foundation.md` — read in full once it exists; it is the authority for every `app.services.ai.*` name this story imports. Everything cited from it above is a description, not a verified path.
3. `backend/app/services/channels/driver.py` (93 lines) — the `ChannelDriver` Protocol / `StubDriver` pattern that `AIProvider` / `StubAIProvider` are modelled on. Read this so the shape of `AIProvider.suggest_reply(ticket, messages)` (a plain function over domain objects, no session, raises on failure rather than returning a sentinel) is unsurprising.
4. `backend/app/services/channels/service.py:74-93` — `list_messages_for_ticket`, which this story's service function calls directly to build the thread context. Note it returns oldest-first, matches the compose UI's own read order, and already 404s via its internal `get_ticket` call.
5. `backend/app/services/tickets.py:304-317` — `get_ticket(db, ticket_id, *, with_relations=False) -> Ticket`, raises `NotFound`. Call this separately (with `with_relations=True`) to get the `Ticket` row itself — `list_messages_for_ticket` only returns messages, not the ticket.
6. `backend/app/api/routes/channels.py` (112 lines) — precedent for a ticket-subresource route (`/tickets/{ticket_id}/messages`) living in a router file that is *not* `tickets.py`, because the sub-resource is a distinct domain concern. This story's route follows the same reasoning — see Backend Tasks §2.
7. `backend/app/api/routes/tickets.py` — read for contrast: shows this codebase's router conventions (`DbDep = Annotated[Session, Depends(get_db)]`, thin handlers, `response_model=`) and how `/tickets/{ticket_id}/notes` stays agent-gated (`CurrentAgent`) while most of the file is not.
8. `backend/app/api/routes/quick_replies.py` (54 lines) — precedent for a small, fully agent-gated router: `router = APIRouter(tags=[...], dependencies=[Depends(get_current_agent)])` so every route 401s without `X-Agent-Id`.
9. `backend/app/api/deps.py` — `CurrentAgent`/`get_current_agent` (lines 47-60, 83).
10. `backend/app/services/errors.py` — `NotFound`/`Conflict`/`Forbidden`/`PayloadTooLarge` (no `Error` suffix). This story raises none of its own; `NotFound` surfaces naturally from `get_ticket`.
11. `backend/app/main.py` — `include_router` block (lines 29-47) and `register_exception_handlers` (lines 52-64); wire the new router next to the other agent-scoped ones (`dashboard`, `tasks`, `quick_replies`, `knowledge_base`).
12. `backend/tests/test_ticket_notes.py:21-34` — the `monkeypatch.setattr("app.services.channels.service.get_driver", fake_get_driver)` pattern; this story's tests override `app.services.ai.suggested_replies.ai_provider.get_ai_provider` (via the module reference imported in Backend Tasks §1) the same way, module-path monkeypatching, not a FastAPI dependency override (contrast with `backend/app/services/storage.py:104-106`'s `get_storage`, which *is* a route-level dependency swapped via `backend/tests/conftest.py:70-94`'s `application.dependency_overrides[...]` — `get_ai_provider` is deliberately not that kind of function, per Story 08).
13. `backend/tests/conftest.py:154-169` (`agent_client`/`other_agent_client` fixtures) and `:222-234` (`ticket` fixture) — reuse both.
14. `frontend/src/components/ticket/MessagesPanel.tsx` (187 lines) — **read this in full.** The compose box's draft text is a plain local `useState<string>` called `body` (line 44), set directly by the textarea's `onChange` (line 174) and by `QuickReplyPicker`'s `onChange` prop (line 164, wired straight to `setBody`). There is no lifted/shared compose state anywhere else — a "Suggest a reply" action inserts into this same `body` state via the same `onChange={setBody}`-shaped callback.
15. `frontend/src/components/dashboard/QuickReplyPicker.tsx` (225 lines) — the sibling insertion mechanism. `insert()` (lines 127-146) reads caret position off `textareaRef`, splices the rendered text into `value` at the caret, calls `onChange(next)`, then restores the caret past the inserted text on the next frame. This story's suggestion does **not** need caret-aware splicing (a suggestion replaces/fills the whole draft rather than inserting at a point), but reuses the same `onChange` callback shape into the same `body` state.
16. `frontend/src/components/ticket/__tests__/MessagesPanel.test.tsx` (389 lines) — the test pattern to mirror: a stubbed `fetch` via `vi.stubGlobal("fetch", ...)` routed by URL substring (`mockApi`, lines 104-139), `userEvent` for interaction, and assertions against `screen.getByLabelText("Message body")` for the compose box's current value (e.g. lines 327-329).
17. `frontend/src/api/channels.ts` (57 lines) — precedent for a typed API client module (`listTicketMessages`, `sendTicketMessage`) built on `request`/`buildQuery` from `frontend/src/api/client.ts`.
18. `frontend/src/api/client.ts` — `request<T>` (lines 35-56) and `ApiError`; every agent-authenticated call goes through this, which already forwards `X-Agent-Id`.
19. `frontend/src/pages/TicketDetailPage.tsx:45` — precedent for `window.confirm("...")` guarding a destructive/overwriting action in this codebase; reused for the "overwrite an in-progress draft" edge case below.
20. `frontend/src/types/channel.ts` — `ChannelMessage.direction: "inbound" | "outbound"` (lines 30-42); used client-side to decide whether the ticket has anything from the customer to reply to.

---

## Backend Tasks

No schema change. No new model, no new Alembic revision.

### 1 — Service function

Create file: `backend/app/services/ai/suggested_replies.py`

```python
"""Suggested-reply generation. No persistence — a suggestion is never written
to the database; it exists only for the duration of one request/response.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.services.ai import provider as ai_provider
from app.services.ai.provider import AIProviderError, StubAIProvider
from app.services.channels.service import list_messages_for_ticket
from app.services.tickets import get_ticket

# Matches the limit MessagesPanel itself fetches (frontend/src/components/
# ticket/MessagesPanel.tsx:55) -- if a thread is longer than this, both the
# agent's own view and the AI's context are truncated the same way.
THREAD_CONTEXT_LIMIT = 200


def suggest_reply(db: Session, ticket_id: uuid.UUID) -> str:
    """Draft a reply for ``ticket_id`` from its ticket + message thread.

    Raises ``app.services.errors.NotFound`` (via ``get_ticket``) if the ticket
    does not exist -- the same 404 semantics every other ticket-scoped route
    uses. Does not require an inbound customer message to exist; that gate is
    enforced in the UI (see this story's Edge Cases), not here, so the API
    stays simple to call directly (docs, scripts, a future channel bot) without
    silently refusing a reasonable request.
    """
    ticket = get_ticket(db, ticket_id, with_relations=True)
    messages, _total = list_messages_for_ticket(db, ticket_id, limit=THREAD_CONTEXT_LIMIT)

    # Import the module, not the bare name (see the import above): calling
    # `ai_provider.get_ai_provider()` re-reads the module attribute on every
    # call, which is what lets a test's `monkeypatch.setattr(ai_provider,
    # "get_ai_provider", fake_factory)` take effect.
    try:
        return ai_provider.get_ai_provider().suggest_reply(ticket, messages)
    except AIProviderError:
        # Story 08 ships no central handler for AIProviderError (confirmed:
        # `08-story-ai-foundation.md` registers no exception handler and
        # explicitly leaves this decision to each caller) -- this is the
        # required fallback for this story, not a placeholder pending a
        # central mechanism. A suggested reply is optional and always
        # human-reviewed before sending, so degrading to stub output here
        # (rather than surfacing a 502, which Story 09 does for its explicit
        # "Regenerate" action) is the right call for this specific feature.
        return StubAIProvider().suggest_reply(ticket, messages)
```

- `get_ticket(db, ticket_id, with_relations=True)` is called in addition to (not instead of) `list_messages_for_ticket`'s own internal `get_ticket` call — the latter only returns messages, and this function needs the `Ticket` row itself (subject, description, status, priority, customer) to pass as context. This is a deliberate small duplication, consistent with how `backend/app/api/routes/tickets.py:86` already re-fetches with relations for its own detail view.
- Whatever shape `AIProvider.suggest_reply` expects for `ticket`/`messages` is Story 08's contract — pass the ORM `Ticket` and `list[ChannelMessage]` objects straight through, the same way `ChannelDriver.send(message: ChannelMessage)` takes the ORM row directly rather than a DTO (`backend/app/services/channels/driver.py:46`).

### 2 — Schema

Create file: `backend/app/schemas/ai.py`

```python
"""Pydantic v2 schemas for AI-feature endpoints (stories 09-13)."""

from __future__ import annotations

from pydantic import BaseModel


class SuggestedReplyRead(BaseModel):
    draft: str
```

Not `ConfigDict(from_attributes=True)` — this is never built from an ORM row, only constructed directly from the service's return string (`SuggestedReplyRead(draft=...)`).

### 3 — Route

Create file: `backend/app/api/routes/ai.py`

```python
"""AI-feature HTTP routes (stories 09-13 each add to this file).

Every route here returns a value for an agent to review -- none of them
create, update, or send anything. Agent-scoped at router level, like
quick_replies.py (backend/app/api/routes/quick_replies.py:21): every route is
401 without a valid X-Agent-Id.

Grouped under their own router rather than folded into tickets.py for the same
reason /tickets/{ticket_id}/messages lives in channels.py, not tickets.py
(backend/app/api/routes/channels.py:56-92): the sub-resource is a distinct
domain concern from core ticket CRUD, and five AI endpoints landing here across
stories 10-13 would otherwise keep growing an already-large tickets.py.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import CurrentAgent, get_current_agent
from app.db.session import get_db
from app.schemas.ai import SuggestedReplyRead
from app.services.ai import suggested_replies as svc

router = APIRouter(
    prefix="/tickets/{ticket_id}/ai",
    tags=["ai"],
    dependencies=[Depends(get_current_agent)],
)

DbDep = Annotated[Session, Depends(get_db)]


@router.post("/suggested-reply", response_model=SuggestedReplyRead)
def suggest_reply(
    ticket_id: uuid.UUID, db: DbDep, agent: CurrentAgent
) -> SuggestedReplyRead:
    """Draft a reply from the ticket + thread. Never persisted, never sent."""
    return SuggestedReplyRead(draft=svc.suggest_reply(db, ticket_id))
```

- Default `200 OK` (no `status_code=status.HTTP_201_CREATED`) is intentional and different from `POST /tickets/{ticket_id}/messages` (`backend/app/api/routes/channels.py:69-73`, `201`): that route creates a `ChannelMessage` row, this one creates nothing.
- `agent: CurrentAgent` is accepted but unused in the body beyond satisfying the type/auth contract — nothing here needs to know *which* agent asked, but leaving the parameter in (mirroring `add_ticket_note`, `backend/app/api/routes/tickets.py:186-194`) keeps the signature consistent with every other `CurrentAgent`-gated route and leaves room for a future story that wants to log who asked without changing the signature again.

### 4 — Wiring

- In `backend/app/main.py`: add `ai` to the `from app.api.routes import (...)` block (line 5-16) and add `app.include_router(ai.router, prefix=settings.api_prefix)` next to the other agent-scoped routers (after `knowledge_base.router`, line 47) — same comment block already covers it ("Agent-scoped routers. Each declares `Depends(get_current_agent)` at router level...").
- If Story 09 (Ticket Summaries) lands first or in parallel and also introduces `backend/app/api/routes/ai.py`, merge into the same file/router rather than creating a second one — the router-per-domain-concern reasoning in §3 argues for exactly one `ai.py` for the whole arc, not one per story.

---

## Frontend Tasks

### 5 — API client

Create file: `frontend/src/api/ai.ts`

```typescript
/** Typed wrapper for the AI-feature endpoints (stories 09-13 each add to this file). */

import { request } from "./client";

interface SuggestedReplyResponse {
  draft: string;
}

/** Draft a reply from the ticket's thread. Never sends anything -- the
 * caller is responsible for putting `draft` in front of the agent for review
 * before it goes anywhere near the existing send path. */
export function suggestReply(ticketId: string): Promise<string> {
  return request<SuggestedReplyResponse>(`/tickets/${ticketId}/ai/suggested-reply`, {
    method: "POST",
  }).then((res) => res.draft);
}
```

### 6 — Compose box integration

Edit `frontend/src/components/ticket/MessagesPanel.tsx`. All line numbers below are against the 187-line version read in Context §14.

1. Import `suggestReply` from `../../api/ai`.
2. Add two state variables next to the existing composer state (after `const [busy, setBusy] = useState(false);`, line 47):
   ```typescript
   const [suggesting, setSuggesting] = useState(false);
   const [suggestionActive, setSuggestionActive] = useState(false);
   ```
3. Introduce one wrapped setter used everywhere `body` is written from something other than a fresh AI suggestion, so the "AI-drafted" label disappears the moment the agent (or a quick reply) changes the text:
   ```typescript
   function updateBody(next: string) {
     setBody(next);
     setSuggestionActive(false);
   }
   ```
   Wire this into the textarea's `onChange` (replacing `onChange={(event) => setBody(event.target.value)}` at line 174 with `onChange={(event) => updateBody(event.target.value)}`) and into `QuickReplyPicker`'s `onChange` prop (replacing `onChange={setBody}` at line 164 with `onChange={updateBody}`) — a quick reply inserted after a suggestion correctly clears the AI label, since the text is no longer what the AI drafted.
4. Clear `suggestionActive` on successful send too — inside `handleSend` (lines 82-103), alongside the existing `setBody("")` at line 89, add `setSuggestionActive(false)`.
5. Compute whether the thread has anything to reply to:
   ```typescript
   const hasInboundMessage = messages.some((message) => message.direction === "inbound");
   ```
6. Add the handler, near `handleSend`:
   ```typescript
   async function handleSuggestReply() {
     if (body.trim() !== "") {
       const proceed = window.confirm(
         "Replace your draft with an AI-suggested reply? Your current draft will be lost.",
       );
       if (!proceed) return;
     }
     setSuggesting(true);
     setError(null);
     try {
       const draft = await suggestReply(ticketId);
       setBody(draft);
       setSuggestionActive(true);
     } catch (err) {
       setError(err instanceof Error ? err.message : String(err));
     } finally {
       setSuggesting(false);
     }
   }
   ```
   Note this calls `setBody` directly, not `updateBody` — a freshly-returned suggestion is exactly the case where `suggestionActive` must become `true`, not `false`.
7. Add the button next to `QuickReplyPicker` (inside the `<div style={{ ...styles.row, marginTop: "0.5rem" }}>` block, lines 160-167):
   ```tsx
   <button
     type="button"
     onClick={handleSuggestReply}
     disabled={!hasInboundMessage || suggesting || busy}
     title={
       hasInboundMessage
         ? undefined
         : "Nothing from the customer yet to draft a reply to"
     }
     style={{ ...styles.button, fontSize: "0.85rem" }}
   >
     {suggesting ? "Suggesting…" : "Suggest a reply"}
   </button>
   ```
8. Add the AI-drafted label, rendered only while `suggestionActive` is true, placed between the composer row and the textarea (i.e. right before line 168's `<textarea`):
   ```tsx
   {suggestionActive && (
     <p
       role="status"
       style={{ ...styles.muted, margin: "0.35rem 0 0", fontSize: "0.8rem" }}
     >
       ✨ AI-drafted suggestion — review and edit before sending.
     </p>
   )}
   ```
   (Drop the emoji if the project's existing UI never uses one elsewhere — check `frontend/src/components/ui.tsx` for the house style before adding it; the important part is the visible "AI-drafted" text and the `role="status"` so it's queryable the same way `getByRole("alert")` is used for errors elsewhere in this file's tests.)

No new page, no new route, no navigation change — `frontend/src/__tests__/navigation.test.tsx` is untouched by this story.

---

## Edge Cases & Failure Modes

- **No inbound customer message yet** (a brand-new ticket, or one where only internal notes/outbound messages exist) — the "Suggest a reply" button is disabled with an explanatory `title` tooltip (`hasInboundMessage` check, Frontend Tasks §6.5/§6.7) rather than letting the agent trigger a call that can only produce a generic, contextless draft. This is a **UI-only** gate: the backend service (`suggest_reply` in `backend/app/services/ai/suggested_replies.py`) does not duplicate the check and will happily call the provider with an all-outbound or empty thread if hit directly (e.g. via curl or a future caller) — the provider's own judgment (Story 08) decides what to do with thin context. Keeping the gate UI-only avoids inventing a new backend error class for what is fundamentally a "this button wouldn't be useful right now" UX decision, not an invalid-request condition.
- **Never auto-sent** — there is no code path from the suggestion response to `enqueue_outbound`/`sendTicketMessage`. The draft only ever reaches `body` state; sending still requires the agent to press "Send", which posts whatever is currently in the textarea, suggestion or not, exactly as it does today.
- **Repeated/rapid clicks must not spam the API** — the button is `disabled={... || suggesting || busy}` (Frontend Tasks §6.7); `suggesting` flips true for the duration of the in-flight request, so a second click before the first resolves is a no-op at the DOM level (the button is disabled), not merely ignored in the handler.
- **Overwriting an agent's own in-progress draft** — decision: **prompt for confirmation rather than block outright.** `handleSuggestReply` (§6.6) calls `window.confirm(...)` — the same pattern already used for destructive actions in this codebase (`frontend/src/pages/TicketDetailPage.tsx:45`) — only when `body.trim() !== ""`, and returns without calling the API if the agent declines. Reasoning: blocking the action outright whenever any draft text exists would make "Suggest a reply" a dead end in the common case where an agent typed a note, got stuck, and wants an AI-drafted alternative to react to — exactly the scenario this feature is for. A confirmation dialog costs one click, preserves the "never overwritten without an explicit action" guarantee, and needs no new UI component.
- **Ticket not found** — `get_ticket` raises `NotFound` (`backend/app/services/tickets.py:315-316`), mapped centrally to 404 (`backend/app/main.py:61`); the frontend's existing `ApiError`/`ErrorBanner` path (already exercised by `MessagesPanel`'s initial load, `frontend/src/components/ticket/__tests__/MessagesPanel.test.tsx:373-388`) surfaces it the same way a failed initial load does today.
- **AI disabled or unconfigured** — `get_ai_provider()` returns `StubAIProvider`, whose output is still routed through this story's normal response shape and still gets the "AI-drafted" label in the UI (the label does not distinguish stub output from a real model's output — both are "AI-generated content" per this arc's labelling rule, and a stub's obviously generic text is itself a signal to the agent that AI is not really configured yet).
- **Provider failure at call time** (network error, rate limit, bad credential after being configured) — caught in `suggest_reply` and degraded to `StubAIProvider` output rather than surfacing a 5xx (see Backend Tasks §1's inline comment) — flagged there as a default to be reconciled with however Story 08 actually handles `AIProviderError` centrally.
- **Long threads** — capped at `THREAD_CONTEXT_LIMIT = 200`, matching the same limit `MessagesPanel` itself fetches (`frontend/src/components/ticket/MessagesPanel.tsx:55`); a thread longer than that is truncated identically for the agent's own view and the AI's context, so the two never disagree about what "the conversation so far" contains.
- **Unauthenticated request** — router-level `dependencies=[Depends(get_current_agent)]` (Backend Tasks §3) means a missing/invalid `X-Agent-Id` is a 401 before the handler body runs, same as every other agent-scoped router.

---

## Test Plan

Backend — create `backend/tests/test_ai_suggested_replies.py`, following `backend/tests/test_quick_replies.py`'s fixture style (`agent_client`, `ticket` from `backend/tests/conftest.py:154-169,222-234`):

1. **Service test** — call `suggest_reply(db, ticket["id"])` directly against a `db` session; with no monkeypatch at all, `get_ai_provider()` already returns `StubAIProvider` by default in the test environment (no `CRM_ANTHROPIC_API_KEY`/`CRM_AI_ENABLED` set). Assert it returns a non-empty `str` and does not raise when the thread is empty. Add a second case that monkeypatches `app.services.ai.suggested_replies.ai_provider.get_ai_provider` to a fake whose `suggest_reply` raises `AIProviderError`, and asserts the function still returns a non-empty string (the local fallback to `StubAIProvider`, not a re-raised exception).
2. **Route test, happy path** — `agent_client.post(f"/api/tickets/{ticket['id']}/ai/suggested-reply")` → `200`, body `{"draft": "..."}` with a non-empty string.
3. **Route test, unknown ticket** — `agent_client.post(f"/api/tickets/{missing_uuid()}/ai/suggested-reply")` → `404`.
4. **Route test, unauthenticated** — plain `client` (no `X-Agent-Id`) hitting the same route → `401`.
5. **No side effects** — around the call in test 2, assert the ticket's event count (`GET /api/tickets/{id}/events`) and message count (`GET /api/tickets/{id}/messages`) are identical before and after the suggestion request — a suggestion must never create a `TicketEvent` or a `ChannelMessage` row as a side effect of merely being requested.
6. **Degrades when AI is disabled/unconfigured** — with whatever Story 08 exposes for this (e.g. `settings.ai_enabled = False`, or simply not overriding `get_ai_provider` so the real factory resolves to `StubAIProvider` by default in tests), assert the route still returns `200` with a usable draft rather than erroring.

Frontend — extend `frontend/src/components/ticket/__tests__/MessagesPanel.test.tsx` (or add a sibling file in the same `__tests__/` directory), reusing the `mockApi` helper (lines 104-139) with a new URL branch for `.../ai/suggested-reply`:

7. **Suggest button populates the compose box** — mock the suggestion endpoint to return a fixed draft string; click "Suggest a reply"; assert `screen.getByLabelText("Message body")` now has that value, and that the "AI-drafted" label (`getByRole("status")` or equivalent) is visible.
8. **Disabled on an empty/no-inbound thread** — with a thread containing only an outbound message (or none at all), assert `screen.getByRole("button", { name: "Suggest a reply" })` is disabled.
9. **Enabled once an inbound message exists** — with at least one `direction: "inbound"` message in the thread, assert the button is enabled.
10. **Confirms before overwriting an existing draft** — type into the compose box, stub `window.confirm` to return `false`, click "Suggest a reply", assert the API was *not* called and the original draft is unchanged; repeat with `window.confirm` returning `true` and assert the draft *is* replaced.
11. **Disabled while a request is in flight** — assert the button is disabled between click and the mocked promise resolving (a deferred/never-resolving mock is the usual way to catch this).
12. **No automatic send** — after a successful suggestion, assert no `POST .../messages` request was made; only clicking the pre-existing "Send" button (already covered by the existing "sends the composed body..." test) triggers one.
13. **Label clears on manual edit** — after a suggestion populates the box, type an additional character into the textarea and assert the "AI-drafted" label disappears.

---

## Verification Steps

1. **Backend tests:** `cd backend && uv run pytest -q` — all existing tests still pass, `test_ai_suggested_replies.py` passes.
2. **Backend serves:** `cd backend && uv run uvicorn app.main:app --reload` — with an agent id in hand (`POST /api/agents`), hit `POST /api/tickets/{ticket_id}/ai/suggested-reply` with header `X-Agent-Id: <id>` against a ticket that has at least one inbound message; inspect the JSON `{"draft": "..."}`. Confirm a request without the header returns 401, and against an unknown ticket id returns 404.
3. **Frontend runs:** `cd frontend && npm run dev` — open a ticket with an existing customer message, click "Suggest a reply" in the Messages tab, confirm the draft appears in the compose box labelled as AI-drafted, edit it, and send it through the unchanged Send button. Also open a ticket with no messages and confirm the button is disabled with a tooltip.
4. **Frontend tests:** `cd frontend && npm test` — new and existing suites green, including the extended `MessagesPanel.test.tsx`.
5. **Regression:** re-run `pytest -q` and `npm test` in full; confirm the pre-existing "sends the composed body..." and quick-reply tests in `MessagesPanel.test.tsx` still pass unmodified in behaviour (only the two `onChange` wiring points changed).

---

## Done Criteria

- [ ] `backend/app/services/ai/suggested_replies.py::suggest_reply(db, ticket_id) -> str` builds context from the ticket (`get_ticket`, with relations) and its thread (`list_messages_for_ticket`), calls `get_ai_provider().suggest_reply(...)`, and never persists anything.
- [ ] `POST /api/tickets/{ticket_id}/ai/suggested-reply` (in `backend/app/api/routes/ai.py`) is `CurrentAgent`-gated, returns `SuggestedReplyRead{draft: str}`, 404s on an unknown ticket, and is registered in `backend/app/main.py` next to the other agent-scoped routers.
- [ ] No `TicketEvent` or `ChannelMessage` is created merely by requesting a suggestion.
- [ ] `frontend/src/api/ai.ts::suggestReply(ticketId)` follows the `request`/`buildQuery` pattern from `frontend/src/api/client.ts`.
- [ ] `MessagesPanel.tsx` has a "Suggest a reply" action that inserts the draft into the same `body` state the compose textarea and `QuickReplyPicker` already use, visibly labelled as an AI suggestion while present, with the label clearing on manual edit or after send.
- [ ] The action is disabled (with an explanatory tooltip) when the thread has no inbound customer message, disabled while a request is in flight, and confirms with the agent before overwriting non-empty draft text.
- [ ] There is no code path anywhere in this story from a suggestion to the existing send-message flow — sending a suggested reply always requires the agent to press the pre-existing Send button.
- [ ] All new backend tests in `test_ai_suggested_replies.py` pass; all new/extended frontend tests in `MessagesPanel.test.tsx` pass.
- [ ] `pytest -q` and `npm test` are green in full (no regression in the pre-existing `MessagesPanel` or channels tests).

**STOP HERE. Report to the user and wait for confirmation before proceeding to Story 11.**
