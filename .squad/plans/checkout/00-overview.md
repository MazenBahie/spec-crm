# checkout — plan overview

Entry point for the **checkout** feature. Stories execute in order by their `NN` prefix.

## Stories

| NN | File | Title | Tracker id | Depends on |
|----|------|-------|------------|------------|
| 01 | `01-story-project-init-and-structure.md` | Project init and structure | project-init-and-structure | — |
| 02 | `02-story-customer-management.md` | Customer Management | customer-management | 01 |
| 03 | `03-story-ticket-management.md` | Ticket Management | ticket-management | 01, 02 |
| 04 | `04-story-communication-channels.md` | Communication Channels | communication-channels | 01, 02, 03 |
| 05 | `05-story-agent-dashboard.md` | Agent Dashboard | agent-dashboard | 01, 02, 03, 04 |
| 06 | `06-story-customer-portal.md` | Customer Portal | customer-portal | 01, 02, 03 |

## Dependency notes

Strictly sequential — each story assumes the previous one is merged.

- **01 → 02.** Story 02 builds on the backend layering, the `get_db` session dependency, and the Vite/React shell created in Story 01.
- **02 → 03.** Story 03 depends on Story 02 for concrete shared contracts, not just convention:
  - `tickets.customer_id` is a FK to `customers.id` with `ON DELETE CASCADE`, and `Customer` gains a `tickets` relationship.
  - `create_ticket` reuses `_require_active` from `app/services/customers.py` to refuse tickets on archived customers.
  - `TicketDetailRead` embeds `CustomerRead` from `app/schemas/customer.py`.
  - The Alembic chain is linear: `0002_ticket_management` sets `down_revision = '0001'`.
  - The frontend reuses `api/client.ts` (`request`, `buildQuery`), `components/ui.tsx`, and the router introduced in Story 02, and adds a **Tickets** tab to `CustomerDetailPage`.
- **03 → 04.** Story 04 is the *foundation only* of Communication Channels (data model, driver interface, ticket-thread wiring); the five provider adapters are follow-up stories. It depends on Story 03 for concrete contracts:
  - `channel_messages.ticket_id` is a FK to `tickets.id` with `ON DELETE CASCADE`, and `customer_id` is denormalised off the ticket.
  - `app/services/channels/service.py` reuses `get_ticket` from `app/services/tickets.py` for its 404 semantics.
  - The Alembic chain stays linear: `0003_communication_channels` sets `down_revision = '0002'`.
  - The frontend adds a **Messages** tab to `TicketDetailPage` alongside Workflow and History.
- **01–04 → 05.** Story 05 is the first agent-facing story, and depends on all four:
  - The `agents` table from Story 03 is reused as-is, **not** recreated. `0004` only hangs `agent_tasks`, `quick_replies`, `ticket_notes`, `activity_events` and `activity_event_mentions` off it, and `down_revision = '0003'` keeps the chain linear.
  - `list_my_queue` reuses `priority_rank()`, extracted from `list_tickets` in `app/services/tickets.py`, so both order priority through the same CASE.
  - `app/services/tickets.py` and `app/services/channels/service.py` call `activity.record(...)` after assignment, status change and reply. Each takes a new **optional** `actor_agent_id` keyword, so both routes stay callable without agent context.
  - The frontend reuses `api/client.ts` (which now forwards `X-Agent-Id`), `components/ui.tsx`, and adds a **Notes** tab to `TicketDetailPage`.
- **01–03 → 06.** Story 06 (Customer Portal) depends only on Stories 01–03, not on 04 or 05 — it does not touch `channels`, `agent_tasks`, `quick_replies`, or `activity_events`. It introduces the **first real, credential-based principal type** in the codebase (`PortalUser` + `PortalSession`, bcrypt-hashed passwords, SHA-256-hashed bearer session tokens), deliberately distinct from the `Agent`/`X-Agent-Id` placeholder:
  - `portal_users.customer_id` is a FK to `customers.id` with `ON DELETE CASCADE`, and `Customer` gains a `portal_users` relationship; a `Customer` may hold many `PortalUser` logins.
  - `ticket_feedback.ticket_id` is a FK to `tickets.id` with `ON DELETE CASCADE` and a **unique constraint**, so feedback is upserted, not duplicated; `Ticket` gains a `feedback` relationship.
  - `app/api/deps_portal.py` reuses `_require_active`'s reasoning (not the function itself) to gate every portal request live against `Customer.is_archived`.
  - `app/services/portal.py` wraps `create_ticket`/`get_ticket`/`list_customer_tickets` from `app/services/tickets.py` rather than duplicating them, and reuses `Ticket.is_terminal` as the feedback-eligibility gate.
  - The Alembic chain stays linear: `0005_customer_portal` sets `down_revision = '0004'`, and introduces no new named enum types (unlike `0001`–`0004`).
  - The frontend adds a `/portal/*` route subtree (`PortalApp.tsx`) that never renders the agent `<Nav>`, with its own `portalAuth.ts`/`portalClient.ts` parallel to (not shared with) `agentContext.ts`/`client.ts`.

## Shared contracts to respect

- **Service layer never commits.** `get_db` (`backend/app/db/session.py` lines 30–43) owns the transaction; services `flush()` only.
- **Error mapping is centralised.** `NotFound`/`Conflict`/`PayloadTooLarge` → 404/409/413 in `backend/app/main.py` lines 33–35. Add new failure modes as `Conflict`, not as new exception types or per-route `HTTPException`s.
- **Schema changes go in Alembic**, never in `infra/postgres/init.sql`, which stays empty by design.
- **Named enums must be dropped explicitly in `downgrade()`** — `op.drop_table` leaves Postgres enum types behind and breaks the next `upgrade`. See `0001_customer_management.py` lines 116–120 for the pattern.
- **Conditional indexes must set both `postgresql_where` and `sqlite_where`**, or the SQLite-backed test suite enforces a different constraint than production.
- **Seeded reference data needs both paths.** A migration seed alone is invisible to the test suite, which builds its schema with `metadata.create_all`. Story 04 pairs the `0003` seed with an `after_create` hook on `Channel.__table__` and hard-coded row ids, so both paths produce identical rows. Alembic builds its own `Table` object, so the hook never fires during a migration.
- **Migrations are Postgres-only.** They emit `server_default=text('now()')`, which SQLite has no function for — harmless for DDL, fatal for a migration that INSERTs. Supply such values explicitly in a seed.
- **Ordering columns must be stamped in Python, not by the server.** SQLite's `CURRENT_TIMESTAMP` has second resolution, so rows written in one request tie and the order falls to the random uuid4 primary key. `ticket_events.created_at` and `channel_messages.created_at` both set `default=` for this reason.
- **A cross-customer lookup on a portal route returns 404, not 403.** This is a deliberate, documented exception to `Forbidden`'s own docstring reasoning (`backend/app/services/errors.py:18-25`), which justifies 403 only for internal, trusted-staff callers. On the public portal surface, "not yours" and "does not exist" must be indistinguishable, or the response leaks the existence of another customer's record. Story 06 established this; any future public-facing route must follow it too.

## Known cross-story gap

No staff authentication exists yet. Story 02 models `Interaction.author` as free text, Story 03 introduces a standalone `agents` table for assignment, and Story 05 adds an `X-Agent-Id` header (`backend/app/api/deps.py`, `frontend/src/api/agentContext.ts`) that is **trusted outright** — anyone who knows an agent's uuid is that agent. Story 06 adds a **fourth, but real,** identity scheme for customers (`PortalUser` + `PortalSession`, bcrypt + hashed bearer tokens, `backend/app/api/deps_portal.py`) — it does not share any mechanism with the staff side, and is not itself a gap in the same sense (it verifies a real credential), but a future unified-auth story must still reconcile it with the other three so agent and portal identity live in one coherent system rather than two parallel ones.

**A future auth story must reconcile all four** with real users, including a migration for existing `tickets.assignee_id` values. It should also:

- Gate the pre-existing routers, which Story 05 deliberately left open so its regression suite kept proving they work unauthenticated.
- Replace `unread_mentions`, currently approximated as "mentions in the last 7 days" (`activity.MENTION_WINDOW_DAYS`) because there is no per-agent read cursor.
- Give agents a timezone. `tasks_due_today` counts a UTC day while the frontend renders local time, so the two can disagree either side of midnight.
