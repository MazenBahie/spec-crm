# Story 12 — Suggested Solutions

## Prerequisites

- Story 08 (AI Foundation) completed: `backend/app/services/ai/provider.py` defines the `AIProvider` Protocol (modeled on `backend/app/services/channels/driver.py`'s `ChannelDriver` Protocol), the `AnthropicProvider`/`StubAIProvider` implementations, a test-overridable `get_ai_provider()` factory, the `AIProviderError` exception, and the settings `anthropic_api_key` / `ai_model` / `ai_enabled` in `backend/app/core/config.py`. This story imports that module and does not redefine any of it.
- Story 07 (Knowledge Base) completed: provides the `Article` / `ArticleCategory` models (`backend/app/models/knowledge_base.py`), the `ArticleSummary` schema (`backend/app/schemas/knowledge_base.py:91-102`), and — most importantly — the published-only search function `list_public_articles` in `backend/app/services/knowledge_base.py:298-330`, which this story reuses verbatim rather than writing new search logic.
- Story 03 (Ticket Management) completed: `Ticket.subject` / `Ticket.description` (`backend/app/models/ticket.py:113-114`) are the inputs this story searches on, and `get_ticket` (`backend/app/services/tickets.py:304-317`) is the 404 lookup this story reuses.
- Story 05 (Agent Dashboard) completed: `CurrentAgent` / `get_current_agent` (`backend/app/api/deps.py:47-60,83`) gate the new route the same way they gate every other staff endpoint.

**No Alembic migration in this story.** Suggestions are computed live from existing `Article` and `Ticket` rows on every request and are never written to the database — there is no new table, column, or `down_revision` link to add. The `## Migration / Rollback` section from earlier stories is intentionally omitted.

---

## Story Goal

On the ticket detail page, an agent sees a short, clearly AI-labeled list of knowledge-base articles that might resolve the ticket, computed on demand from the ticket's subject (and, when the provider is enabled, re-ranked by it). Nothing is persisted or auto-applied: it is a live, recomputable suggestion the agent can open in a new tab and read — a list of links, not a ticket mutation.

Two things this story is deliberately **not**:

1. **Not a new search engine.** The candidate set always comes from Story 07's real, published-only `list_public_articles` query. The AI provider, when enabled, only re-ranks/selects among those real rows — it can never introduce an article that does not exist, because its output is validated against the real candidate ids before anything is returned (see Backend Tasks §1).
2. **Not part of the ticket page's own load path.** This ships as its own endpoint, fetched by the frontend independently of `GET /tickets/{id}`, so a slow or failing AI call can never delay or break loading the ticket itself — only the suggestions panel degrades.

**Out of scope:** persisting suggestions, an "apply this article to the ticket" action, portal-facing suggestions (this is agent-only), summarizing the matched article's content (Story 09's territory), and any mapping between `TicketCategory` and `ArticleCategory` (see Edge Cases).

---

## Context — Read These Files First

1. `.squad/stories/checkout/ai-features/intake.md` — this story's line item ("Suggested solutions") in the six-story AI Features intake.
2. `backend/app/services/knowledge_base.py:298-354` — read the whole "Articles — public / portal" section. `list_public_articles(db, *, kind=None, category_slug=None, q=None, limit=20, offset=0) -> tuple[list[Article], int]` is the exact function this story reuses; it already filters `Article.status == "published"` (line 307) before applying `kind`/`category_slug`/`q`, and orders title-matches first via `_search_rank` (lines 141-150, 323-327). Do not call the staff-side `list_articles` (`backend/app/services/knowledge_base.py:153-190`) from this story's service — it returns drafts too, which must never reach an agent's suggestion feed.
3. `backend/app/schemas/knowledge_base.py:91-102` — `ArticleSummary` already carries `id`, `slug`, `title`, `summary`, `kind`, `status`, `category_id`, `updated_at` and is `from_attributes=True`. Reuse it as the response shape; do not add a new schema for this story.
4. `backend/app/services/tickets.py:304-317` — `get_ticket(db, ticket_id, *, with_relations=False) -> Ticket` raises `NotFound` on a missing ticket; reuse it rather than writing a second lookup.
5. `backend/app/models/ticket.py:95-149` — confirms `Ticket.subject: str` (required) and `Ticket.description: str` (required, may be empty string via `server_default=""`), and that `Ticket.category_id` points at `TicketCategory` (`backend/app/models/ticket.py:78-92`), a table wholly unrelated to `ArticleCategory` (`backend/app/models/knowledge_base.py`) — no FK, no shared slug, no shared name convention between the two. This is why the category-based fallback described in the intake is explicitly rejected below (Edge Cases).
6. `backend/app/services/ai/provider.py` (Story 08) — read the `AIProvider` Protocol and `get_ai_provider()` factory before writing Backend Tasks §1. This story requires one specific call shape from `AIProvider.suggest_solutions` (spelled out in §1); if Story 08 lands with a different signature, reconcile `backend/app/services/ai/suggested_solutions.py` to match it rather than changing the protocol.
7. `backend/app/api/deps.py:47-60,83` — `CurrentAgent` / `get_current_agent`; the new route is gated the same way as `backend/app/api/routes/knowledge_base.py:33`.
8. `backend/app/api/routes/knowledge_base.py` — precedent for a small, agent-gated router that calls straight into a service module (`svc = app.services.knowledge_base`) and wraps rows in a schema; mirror the style, not the file.
9. `backend/app/main.py` — see how routers are registered (`app.include_router(..., prefix=settings.api_prefix)`, lines 29-47) and how service errors are mapped centrally (`register_exception_handlers`, lines 52-64). Add the new router next to the other agent-scoped ones (after `knowledge_base.router`, line 47).
10. `backend/tests/conftest.py` — reuse the `agent_client` fixture (line 154) for an authenticated client and the `ticket` fixture (line 222, subject `"Cannot log in"`, description `"Password reset email never arrives."`) as a starting point; you will likely want your own ticket fixture with a subject that deliberately matches seeded articles.
11. `backend/tests/test_kb_search.py` — precedent for seeding articles via `agent_client.post("/api/kb/articles", ...)` then `.../publish`; mirror this to seed published articles in the new test file.
12. `frontend/src/pages/TicketDetailPage.tsx` (182 lines, read in full) — `TABS` (line 14) and the Overview tab body (lines 135-170). The new panel is added inside the `tab === "Overview"` block, after the existing `<dl>` (before line 169's closing `</section>`), since Overview is the tab selected by default when the page first mounts — i.e. "opening the ticket detail page" already satisfies the on-demand trigger without any extra wiring. **Note for reconciliation:** Story 09 (ticket summaries) may also want a panel in this same Overview tab; if it lands first, add this story's panel below Story 09's rather than fighting over placement.
13. `frontend/src/api/tickets.ts:41-43` — `getTicket`'s one-line `request<T>(...)` shape is the pattern to mirror for the new `getSuggestedSolutions`.
14. `frontend/src/api/client.ts` — `request`/`buildQuery`; the pattern for every agent-authenticated call (forwards `X-Agent-Id` via `agentHeaders()`, throws `ApiError` on non-2xx).
15. `frontend/src/App.tsx:82-84` — confirms `/kb/:id` renders `KnowledgeBaseEditPage`, **not** a separate read-only article view. There is no dedicated agent-side "view article" page — the editor doubles as the reader (it renders the full `body` in a form field). Link suggested articles to `/kb/${article.id}`, not to the portal's slug-based `/portal/kb/:slug` (that route is customer-facing and keyed by `slug`, not `id`; an agent has no portal session).
16. `frontend/src/types/knowledgeBase.ts:53-62` — `ArticleSummary` interface to reuse as the new endpoint's response type on the frontend, matching the backend schema field-for-field.
17. `frontend/src/components/ticket/TicketHistoryPanel.tsx` and its test `frontend/src/components/ticket/__tests__/TicketHistoryPanel.test.tsx` — closest precedent for a self-contained panel that loads on mount, shows a loading/empty/error state, and is tested with a stubbed `global.fetch` (`vi.stubGlobal("fetch", fetchMock)`, `mockApi()` helper). Mirror both the component shape and the test's mocked-fetch pattern for the new panel.

---

## Backend Tasks

### 1 — Service layer

Create file: `backend/app/services/ai/suggested_solutions.py`

```python
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.knowledge_base import Article
from app.services import knowledge_base as kb_svc
from app.services import tickets as tickets_svc
from app.services.ai import provider as ai_provider

MIN_QUERY_LENGTH = 3
CANDIDATE_MULTIPLIER = 4
MIN_CANDIDATE_POOL = 20


def suggest_solutions(
    db: Session, ticket_id: uuid.UUID, *, limit: int = 5
) -> list[Article]:
    ...
```

Behaviour, precisely:

- **Look up the ticket** with `tickets_svc.get_ticket(db, ticket_id)` — this is the only place `NotFound` can be raised; let it propagate (the route does not catch it, matching every other route in this codebase — `register_exception_handlers` in `backend/app/main.py` maps it to 404).
- **Build the query string from `ticket.subject` only, not `ticket.subject + ticket.description`.** Justification: `Article` search ranks title matches first (`_search_rank`, `backend/app/services/knowledge_base.py:141-150`), so a short, title-shaped string like a ticket subject ("Cannot log in") is a far better match key against article *titles* than a long, prose `description` would be — concatenating the two would dilute the `ILIKE` pattern into something closer to a paragraph, which matches almost nothing. `strip()` the subject; if the stripped length is below `MIN_QUERY_LENGTH` (3), skip the search entirely and return `[]` (see Edge Cases — this replaces the category-based fallback the intake floated, which this story explicitly rejects).
- **Fetch a candidate pool larger than `limit`**, not just `limit` rows, so the AI re-ranking step (next bullet) has real options to choose among: `pool_size = max(limit * CANDIDATE_MULTIPLIER, MIN_CANDIDATE_POOL)`. Call `candidates, _ = kb_svc.list_public_articles(db, q=query, limit=pool_size, offset=0)` — the published-only function (`backend/app/services/knowledge_base.py:298-330`), never `list_articles`. If `candidates` is empty, return `[]` immediately, **without calling the AI provider** (nothing to rank; skip the round-trip).
- **Dedupe defensively by `Article.id`**, preserving the order `list_public_articles` returned, into an ordered `dict[uuid.UUID, Article]`. A single `list_public_articles` call cannot itself produce duplicate rows, but this keeps the contract honest if a future change (e.g. a second fallback query) is added without re-auditing this function.
- **Re-rank via the AI provider, with a hard fallback to the keyword-search order.** Call:

  ```python
  provider = ai_provider.get_ai_provider()
  selected_ids = provider.suggest_solutions(
      ticket_subject=ticket.subject,
      ticket_description=ticket.description,
      candidates=[
          {"id": str(a.id), "title": a.title, "summary": a.summary or ""}
          for a in candidates
      ],
      limit=limit,
  )
  ```

  This is the exact call shape this story needs from Story 08's `AIProvider.suggest_solutions`: keyword args `ticket_subject: str`, `ticket_description: str`, `candidates: list[dict[str, str]]` (each `{"id", "title", "summary"}`), `limit: int`; return value an ordered `list[str]` of chosen candidate ids (a subset of the ids handed in — never a new id). Wrap the call in `try/except Exception` (catching `ai_provider.AIProviderError` and anything else a provider might raise — this call must never surface as a 500, per the "no AI call may ever block/fail a synchronous request path" rule) and on any exception, or if `selected_ids` is empty, or contains no id from the real candidate set, fall back to the plain keyword-search order.
- **Validate the provider's answer against the real candidate set before trusting it** — never return an id the DB query did not produce, in case a provider hallucinates one:

  ```python
  valid_ids: list[uuid.UUID] = []
  for raw_id in dict.fromkeys(selected_ids):  # de-dupe, preserve order
      try:
          parsed = uuid.UUID(raw_id)
      except (ValueError, TypeError):
          continue
      if parsed in seen:  # `seen` is the ordered dict built above
          valid_ids.append(parsed)
  final_ids = valid_ids[:limit] if valid_ids else list(seen)[:limit]
  return [seen[i] for i in final_ids]
  ```

  This design is intentionally resilient to whatever `StubAIProvider.suggest_solutions` turns out to do — whether it passes candidates through unchanged or returns nothing, the function above still returns a sane, real, published-article list either way. Import the module (`from app.services.ai import provider as ai_provider`), not the bare function (`from app.services.ai.provider import get_ai_provider`) — this lets tests `monkeypatch.setattr(ai_provider, "get_ai_provider", fake_factory)` and have it take effect, since `ai_provider.get_ai_provider()` re-reads the module attribute on every call, whereas an already-bound `from ... import get_ai_provider` name would not see the monkeypatch.

### 2 — API route

Create file: `backend/app/api/routes/ai_suggested_solutions.py`

If Story 08, or an earlier-landing sibling AI story, has already created a shared `backend/app/api/routes/ai.py` for AI-feature routes, add this route there instead of creating a new file, and skip the router registration in `backend/app/main.py` below (it will already be wired) — coordinate with the owners of the other AI stories the same way Story 07 coordinated with `quick_replies.py`/`portal.py`'s owners (`.squad/plans/checkout/07-story-knowledge-base.md` Prerequisites).

```python
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import CurrentAgent, get_current_agent
from app.db.session import get_db
from app.schemas.knowledge_base import ArticleSummary
from app.services.ai import suggested_solutions as svc

router = APIRouter(prefix="/tickets", tags=["ai"], dependencies=[Depends(get_current_agent)])

DbDep = Annotated[Session, Depends(get_db)]


@router.get("/{ticket_id}/ai/suggested-solutions", response_model=list[ArticleSummary])
def get_suggested_solutions(
    ticket_id: uuid.UUID,
    db: DbDep,
    agent: CurrentAgent,
    limit: Annotated[int, Query(ge=1, le=10)] = 5,
) -> list[ArticleSummary]:
    articles = svc.suggest_solutions(db, ticket_id, limit=limit)
    return [ArticleSummary.model_validate(a) for a in articles]
```

**`GET`, not `POST` — justification.** The intake floats a `POST` in case the AI re-ranking step needs a request body. It does not: every input (`ticket_id`, `limit`) fits in the path/query string, matching `GET /api/kb/articles?q=...` (`backend/app/api/routes/knowledge_base.py:79-95`), which already runs a comparable "search plus optional ranking" computation as a `GET`. The endpoint is read-only and side-effect-free (unlike `get_public_article_by_slug`, it does not even bump a `view_count`), so `GET` is both idiomatic and cacheable in principle.

**No `Page[T]` envelope.** This is a small, fixed-size top-N recommendation list (`limit` capped at 10), not a paginated resource a client pages through — there is no `offset`, and returning `{"items": [...], "total": n}` would only add ceremony a consumer immediately unwraps. Return a bare `list[ArticleSummary]`, matching how `backend/app/schemas/customer.py:20-22`'s `Page[T]` is deliberately *not* used for every list-shaped response in this codebase.

### 3 — Wiring

In `backend/app/main.py`:

- Add `ai_suggested_solutions` to the `from app.api.routes import (...)` block (alongside `channels, customers, dashboard, health, knowledge_base, portal, portal_kb, quick_replies, tasks, tickets`, lines 5-16), keeping the import list alphabetical as it already is.
- Register it next to the other agent-scoped routers: `app.include_router(ai_suggested_solutions.router, prefix=settings.api_prefix)`, immediately after line 47 (`app.include_router(knowledge_base.router, prefix=settings.api_prefix)`).

No changes to `backend/app/models/__init__.py` or any Alembic migration — this story adds no model.

---

## Frontend Tasks

### 4 — API client

Create file: `frontend/src/api/ai.ts`

```typescript
/** Typed wrappers for the on-demand AI endpoints under /tickets/{id}/ai/... */

import { buildQuery, request } from "./client";
import type { ArticleSummary } from "../types/knowledgeBase";

export function getSuggestedSolutions(
  ticketId: string,
  params: { limit?: number } = {},
): Promise<ArticleSummary[]> {
  return request<ArticleSummary[]>(
    `/tickets/${ticketId}/ai/suggested-solutions${buildQuery({ ...params })}`,
  );
}
```

Mirrors `frontend/src/api/tickets.ts:41-43`'s `getTicket` shape exactly — a single `request<T>()` call, no extra plumbing.

### 5 — Panel component

Create file: `frontend/src/components/ticket/SuggestedSolutionsPanel.tsx`

- Props: `{ ticketId: string }`, matching `TicketHistoryPanel`'s `Props` shape (`frontend/src/components/ticket/TicketHistoryPanel.tsx:7-9`).
- Loads on mount via `useCallback`/`useEffect`, same shape as `TicketHistoryPanel.tsx:44-59`; also expose a "Refresh" button that re-runs the same load function, since nothing is cached server-side and the story goal explicitly calls this "live, recomputable."
- Header must visually mark the panel as AI-generated and distinct from a plain KB search list — e.g. `<h2>Suggested Solutions <span style={{...badge styles...}}>AI</span></h2>` plus a one-line caption such as "Ranked by AI from published knowledge-base articles — links only, nothing is applied to this ticket automatically." This satisfies the arc-wide rule that AI output must be visibly labeled wherever shown.
- States:
  - Loading → reuse `<Loading />` from `frontend/src/components/ui.tsx` (matches every other panel).
  - Error (network/5xx/4xx other than empty result) → reuse `<ErrorBanner message={error} />`; the panel shows this in place of the list, the rest of `TicketDetailPage` is unaffected (the ticket itself already loaded via a separate `getTicket` call).
  - Empty (`articles.length === 0`) → a single sentence, e.g. `"No matching knowledge base articles found."` — used for every zero-result cause (empty KB, no keyword match, subject too short) alike; see Edge Cases for why the panel does not try to distinguish these causes.
  - Success → an unordered list of `title` (linking to `/kb/${article.id}`, opened via React Router `<Link>` matching `frontend/src/pages/TicketDetailPage.tsx:81-83`'s existing `<Link>` usage) plus `summary` (if present) under each title.
- Wire into `frontend/src/pages/TicketDetailPage.tsx`: import `SuggestedSolutionsPanel` and render `<SuggestedSolutionsPanel ticketId={id} />` inside the `tab === "Overview"` block (`frontend/src/pages/TicketDetailPage.tsx:135-170`), after the closing `</dl>` and before the section's closing `</section>` (line 169). Leave the `TABS` array (`frontend/src/pages/TicketDetailPage.tsx:14`) untouched — this rides inside the existing Overview tab rather than adding a new one, since it is a small supplementary panel, not a whole new audience the way Messages/Notes/History are.

---

## Edge Cases & Failure Modes

- **No published KB articles exist at all** — `list_public_articles` returns `([], 0)`; the service returns `[]` before ever calling the AI provider; the route returns `200` with `[]`; the panel shows the empty-state sentence. Never a 404/500.
- **Ticket subject is empty or below `MIN_QUERY_LENGTH` (3 chars after `strip()`)** — the service returns `[]` without querying the KB at all, rather than sending a near-empty `q` that would `ILIKE`-match almost every row (`_search_filter` turns any non-empty `q` into `%...%`, so a one-character `q` would match nearly the whole table). **Category-based fallback explicitly rejected**: `Ticket.category_id` points at `TicketCategory` and `Article.category_id` points at the unrelated `ArticleCategory` (see Context §5) — there is no FK, shared slug, or naming convention linking the two tables. Joining them by matching `TicketCategory.name` against `ArticleCategory.name` as a string would be an undocumented heuristic with no schema backing it, and a false match (e.g. a ticket category "Billing" auto-matching an unrelated article category also named "Billing") would suggest an article that has nothing to do with the ticket's actual subject. Skipping to the empty state is honest; a fabricated category link is not.
- **Duplicate articles in the candidate set** — defended twice: `list_public_articles` itself cannot return duplicate rows from one query, and the service still folds candidates into an ordered `dict[uuid.UUID, Article]` before ranking, so even a future change that queries twice (e.g. an added fallback path) cannot surface the same article twice.
- **Draft/unpublished articles must never appear** — enforced structurally by calling `kb_svc.list_public_articles` (published-only, `backend/app/services/knowledge_base.py:307`), never `kb_svc.list_articles` (drafts + published, staff-only). Covered by an explicit test (Test Plan item 2) that seeds one draft and one published article sharing the same matching keyword and asserts only the published one is ever returned, from the staff-facing suggestion route.
- **AI provider raises (`AIProviderError` or any other exception), times out, or returns garbage** — caught in the service; falls back to the keyword-search order truncated to `limit`. The route never sees an exception from this path; the response is still `200`. This is the concrete instance of the arc-wide rule "no AI call may ever block/fail a synchronous request path."
- **AI provider returns an id that is not in the real candidate set (hallucination) or a malformed string** — filtered out before the response is built (`uuid.UUID(raw_id)` parse guard plus `parsed in seen` membership check); if filtering leaves zero valid ids, falls back to the keyword-search order rather than returning an empty list when real candidates existed.
- **`ai_enabled=False` / no `anthropic_api_key` configured** — out of this story's hands: `ai_provider.get_ai_provider()` (Story 08) is responsible for returning `StubAIProvider` in that case. This story's fallback logic is written to produce a correct result regardless of what `StubAIProvider.suggest_solutions` does (identity pass-through, empty selection, or anything in between) — see Backend Tasks §1's closing paragraph.
- **Ticket does not exist** — `tickets_svc.get_ticket` raises `NotFound`; the route returns 404 via the central handler (`backend/app/main.py`'s `register_exception_handlers`), same as every other ticket-scoped route.
- **No staff auth header** — `dependencies=[Depends(get_current_agent)]` at router level 401s before the handler body runs, matching `backend/app/api/routes/knowledge_base.py:33`.
- **Frontend: suggestions fetch fails** — caught inside `SuggestedSolutionsPanel`; only that panel shows `<ErrorBanner>`, the rest of `TicketDetailPage` (which already loaded the ticket via its own, independent `getTicket` call) renders normally. This is the frontend half of "never blocks/fails a synchronous request path" — the two fetches are independent network requests, not sequenced.
- **`limit` out of range** — `Query(ge=1, le=10)` rejects with a `422` before the handler runs, same validation style as `backend/app/api/routes/knowledge_base.py:87-88`'s `limit: Annotated[int, Query(ge=1, le=100)]`.

---

## Test Plan

Backend — create `backend/tests/test_ai_suggested_solutions.py`, mirroring `backend/tests/test_kb_search.py`'s seeding style (`agent_client.post("/api/kb/articles", ...)` then `.../publish`) and `backend/tests/conftest.py`'s `agent_client`/`ticket` fixtures:

1. `test_matching_published_article_is_suggested` — seed a published article whose title overlaps a ticket's subject (e.g. subject `"Cannot log in"`, article title `"How to reset your login password"`); call `GET /api/tickets/{id}/ai/suggested-solutions`; assert it appears in the response.
2. `test_draft_article_never_suggested` — seed a draft article and a published article that both match the ticket subject; assert only the published one's id appears in the response, never the draft's.
3. `test_empty_kb_returns_empty_list_without_error` — no articles at all; assert `200` and `[]`.
4. `test_short_subject_skips_search` — a ticket whose subject is very short (e.g. `"Hi"`, 2 chars after strip) even though a published article matching `"Hi"` substring-wise exists; assert the response is `[]` (proves the `MIN_QUERY_LENGTH` guard fires before any KB query, not just that nothing happened to match).
5. `test_limit_is_respected` — seed more matching published articles than `limit`; assert the response length never exceeds the requested `limit` (and defaults to 5 when omitted).
6. `test_stub_provider_reranking` — monkeypatch `app.services.ai.provider.get_ai_provider` (via the `ai_provider` module reference, per Backend Tasks §1's import-the-module note) to a fake provider whose `suggest_solutions` reorders the given candidate ids; assert the response order reflects the fake provider's ordering, proving the re-rank step is wired end to end.
7. `test_provider_hallucinated_id_is_filtered` — fake provider returns an id not present in `candidates`; assert the response falls back to the real keyword-search order instead of erroring or including the bogus id.
8. `test_provider_error_falls_back_gracefully` — fake provider's `suggest_solutions` raises; assert the route still returns `200` with the plain keyword-search order, not a `500`.
9. `test_requires_agent_auth` — call the route with no `X-Agent-Id` header (via `client`, not `agent_client`); assert `401`.
10. `test_unknown_ticket_returns_404` — call with a random UUID (`missing_uuid()` from `backend/tests/conftest.py:237-238`); assert `404`.

Frontend — create `frontend/src/components/ticket/__tests__/SuggestedSolutionsPanel.test.tsx`, following `TicketHistoryPanel.test.tsx`'s mocked-`fetch` pattern (`mockApi()` helper, `vi.stubGlobal("fetch", fetchMock)`):

11. Renders a list of suggested articles with title and a link to `/kb/{id}` when the mocked fetch returns a non-empty array.
12. Renders the empty-state sentence when the mocked fetch returns `[]`.
13. Renders `<ErrorBanner>` (not a page crash) when the mocked fetch rejects/returns a non-2xx status.
14. Renders a visible "AI" label/badge on the panel header (asserts the arc-wide AI-labeling rule is actually implemented, not just documented).

---

## Verification Steps

1. **Backend tests:** `cd backend && uv run pytest -q` — all existing tests still pass; the 10 new cases in `test_ai_suggested_solutions.py` pass.
2. **Backend serves:** `cd backend && uv run uvicorn app.main:app --reload`, then in a second shell, create a ticket and a matching published article, and hit the new route with agent auth:
   ```bash
   AGENT_ID=$(curl -s -X POST localhost:8000/api/agents -H "Content-Type: application/json" -d '{"display_name":"Dana"}' | python -c "import sys,json;print(json.load(sys.stdin)['id'])")
   curl -s localhost:8000/api/tickets/<ticket-id>/ai/suggested-solutions -H "X-Agent-Id: $AGENT_ID" | python -m json.tool
   ```
   Confirm the JSON is a bare array of `ArticleSummary` objects (no `items`/`total` wrapper) and contains only published articles.
3. **Frontend runs:** `cd frontend && npm run dev` — open a ticket's detail page (Overview tab, the default), confirm the "Suggested Solutions" panel renders with its AI badge, shows real linked articles when a match exists, and shows the empty-state sentence when the KB has nothing published yet. Click a suggestion's link and confirm it opens `/kb/:id`.
4. **Frontend tests:** `cd frontend && npm test` — new and existing suites green, including `SuggestedSolutionsPanel.test.tsx`.
5. **Regression:** re-run `pytest -q` and `npm test`; open `/kb` and confirm Story 07's own pages still work unmodified (this story only adds a router and a panel, it does not touch `knowledge_base.py`'s service or routes).

---

## Done Criteria

- [ ] `backend/app/services/ai/suggested_solutions.py::suggest_solutions(db, ticket_id, limit=5)` reuses `kb_svc.list_public_articles` (published-only) and `tickets_svc.get_ticket`, never introduces new search/ranking SQL, and validates any AI-provider re-ranking output against the real candidate set before returning it.
- [ ] `GET /api/tickets/{ticket_id}/ai/suggested-solutions` is agent-gated (`CurrentAgent`), returns a bare `list[ArticleSummary]` capped at `limit` (default 5, max 10), and is registered in `backend/app/main.py`.
- [ ] A draft article sharing every keyword with a published one is never returned by this endpoint (explicit test).
- [ ] An empty knowledge base, an unmatched subject, and an AI-provider failure or hallucinated id all resolve to a `200` response (empty list or the safe keyword-search fallback) — never a `500`, and never a crash of the ticket detail page.
- [ ] The frontend panel (`SuggestedSolutionsPanel.tsx`) is wired into `TicketDetailPage.tsx`'s Overview tab, visibly labeled as AI-generated, links each suggestion to `/kb/:id`, and shows loading/empty/error states without ever taking down the rest of the page.
- [ ] `frontend/src/api/ai.ts::getSuggestedSolutions` mirrors the `request<T>()` pattern used throughout `frontend/src/api/tickets.ts`.
- [ ] All 10 new backend tests in `test_ai_suggested_solutions.py` and all 4 new frontend cases in `SuggestedSolutionsPanel.test.tsx` pass.
- [ ] No Alembic migration was added; no existing model, schema, or Story 07 file was modified.

**STOP HERE. Report to the user and wait for confirmation before proceeding to Story 13.**
