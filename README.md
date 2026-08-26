# CRM

A CRM product built on FastAPI + React + Postgres.

**Status:** customer management and ticket management are implemented — customer
profiles, contact details, interaction history, notes, file attachments, plus tickets
with categories, priorities, assignment, a guarded status/escalation workflow, and an
append-only history. The communication-channel **foundation** is in place: a ticket
accumulates inbound and outbound messages across five channels behind a driver
interface, but **no provider adapter is written yet** — every outbound send fails by
design until its adapter story lands (see [Communication channels](#communication-channels)).
Deals, pipelines, and authentication arrive in later stories.

## Layout

```
backend/            FastAPI service
  app/
    main.py         app factory + CORS + router wiring + error handlers
    core/config.py  pydantic-settings (env prefix CRM_)
    api/routes/     HTTP routes (health.py, customers.py, tickets.py, channels.py)
    db/
      base.py       declarative Base
      session.py    lazy engine + get_db dependency
    models/         ORM models (customer.py, ticket.py, channel.py)
    schemas/        Pydantic request/response models
    services/       business logic, attachment storage, error types
      channels/     channel service + driver protocol + one module per channel
  alembic/          migrations (0001_customer_management, 0002_ticket_management,
                    0003_communication_channels)
  tests/            pytest suite
  Dockerfile
frontend/           React 18 + Vite + TypeScript
  src/
    main.tsx        React entry (BrowserRouter)
    App.tsx         nav + routes
    api/            client.ts (fetch helpers) + customers.ts, tickets.ts, channels.ts
    types/          TypeScript mirrors of the API schemas
    pages/          Health/Customers*/Tickets* pages
    components/     ui.tsx atoms + customer/ and ticket/ panels
  Dockerfile
infra/              container topology
  docker-compose.yml
  postgres/init.sql (reserved, intentionally empty — schema lives in Alembic)
```

The three concerns are **backend/**, **frontend/**, and **infra/**. Future CRM domain
modules go under `backend/app/` as sibling packages to `api/` and `db/` (e.g.
`backend/app/deals/`), with models added to `backend/app/models/`.

## Quickstart (Docker)

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
docker compose -f infra/docker-compose.yml up --build

# Apply migrations once the stack is up:
docker compose -f infra/docker-compose.yml exec backend alembic upgrade head
```

Then open <http://localhost:5173> — the health page shows `status: ok`,
<http://localhost:5173/customers> lists the customer directory, and
<http://localhost:5173/tickets> lists the ticket queue.

| Service  | URL                                   |
| -------- | ------------------------------------- |
| frontend | http://localhost:5173                 |
| backend  | http://localhost:8000/api/health      |
| API docs | http://localhost:8000/docs            |
| db       | postgres://crm:crm@localhost:5432/crm |

Postgres is gated by a `pg_isready` healthcheck and the backend waits on it via
`depends_on.condition: service_healthy`. Attachment blobs are written to the
`crm-attachments` named volume, so they survive container rebuilds.

### Port collisions

5432, 8000, and 5173 are the defaults. To use different host ports, edit the left-hand
side of the `ports` mappings in `infra/docker-compose.yml` (e.g. `"5433:5432"`), or
override them from a `docker-compose.override.yml`. Container-internal ports must stay
as-is — the compose network and the Vite proxy target reference them.

## Running outside Docker

Backend:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Point `CRM_DATABASE_URL` at a reachable Postgres — for the compose one, use
`postgresql+psycopg://crm:crm@localhost:5432/crm`.

Frontend (in another shell):

```bash
cd frontend
npm install
VITE_API_TARGET=http://localhost:8000 npm run dev
```

The Vite dev server proxies `/api` to `VITE_API_TARGET`, so no CORS handling is needed.
For direct cross-origin calls the backend whitelists `http://localhost:5173` and
`http://localhost:3000`.

## Endpoints

### Health

| Method | Path              | Behaviour                                                       |
| ------ | ----------------- | --------------------------------------------------------------- |
| GET    | `/api/health`     | `{"status": "ok"}` — never touches the database                  |
| GET    | `/api/health/db`  | `reachable`, or `degraded` + driver error when Postgres is down  |

### Customers

| Method | Path                          | Behaviour                                        |
| ------ | ----------------------------- | ------------------------------------------------ |
| GET    | `/api/customers`              | Paginated list; `q`, `status`, `limit`, `offset`  |
| POST   | `/api/customers`              | Create (201)                                     |
| GET    | `/api/customers/{id}`         | Detail, including contacts                       |
| PATCH  | `/api/customers/{id}`         | Partial update (last-write-wins)                 |
| POST   | `/api/customers/{id}/archive` | Soft archive; deletes nothing                    |
| DELETE | `/api/customers/{id}`         | Hard delete; cascades all children               |

Contacts live at `/api/customers/{id}/contacts[/{contact_id}]`; interactions at
`/api/customers/{id}/interactions` and `/api/interactions/{id}`; notes at
`/api/customers/{id}/notes` and `/api/notes/{id}`; attachments at
`/api/customers/{id}/attachments` and `/api/attachments/{id}`. The full contract is
browsable at `/docs`.

Behaviour worth knowing:

- **One primary contact per kind.** A second primary of the same kind returns **409**,
  enforced by a Postgres *partial* unique index plus a service-layer pre-check. Multiple
  non-primary contacts of one kind are fine.
- **Archived customers** still accept `PATCH`, but posting a note or interaction returns
  **409 "customer is archived"**. Existing history stays readable.
- **Uploads** stream to disk and are capped by `CRM_MAX_UPLOAD_BYTES` (default 10 MB);
  oversize requests return **413** and leave no partial file behind. Filenames are
  sanitised on disk while the original is preserved for display.
- **Deleting** a customer or a note removes the attachment rows *and* their files.
- Pagination clamps `limit` to `[1, 100]` and requires `offset >= 0`; violations are
  **422**.
- Concurrent `PATCH`es are last-write-wins; optimistic locking is out of scope.

### Tickets

| Method | Path                          | Behaviour                                        |
| ------ | ----------------------------- | ------------------------------------------------ |
| GET    | `/api/tickets`                | Paginated queue; `q`, `status`, `priority`, `customer_id`, `assignee_id`, `category_id`, `unassigned`, `limit`, `offset` — urgent-first, then newest-first |
| POST   | `/api/tickets`                | Create (201); inherits the category's `default_priority` when `priority` is omitted |
| GET    | `/api/tickets/{id}`           | Detail, including customer, category, and assignee |
| PATCH  | `/api/tickets/{id}`           | Editable fields only — **not** `status` or `assignee_id` (see below) |
| DELETE | `/api/tickets/{id}`           | Hard delete; cascades all history                |
| POST   | `/api/tickets/{id}/status`    | Guarded status transition (409 on a forbidden move) |
| POST   | `/api/tickets/{id}/assignment`| Assign/reassign/unassign (`assignee_id: null` unassigns) |
| POST   | `/api/tickets/{id}/escalate`  | Bump escalation level, optionally raise priority  |
| GET    | `/api/tickets/{id}/events`    | Append-only history, newest-first (no `PATCH`/`DELETE`) |
| POST   | `/api/tickets/{id}/events`    | Add a comment (the only client-authored event)    |
| GET    | `/api/customers/{id}/tickets` | Tickets for one customer                          |
| GET/POST/PATCH/DELETE | `/api/ticket-categories[/{id}]` | Category CRUD; delete refused (409) while in use |
| GET/POST/PATCH | `/api/agents[/{id}]`  | Agent CRUD; `DELETE` deactivates rather than deletes, so assignment history stays readable |

Behaviour worth knowing:

- **`status` and `assignee_id` are absent from the `PATCH` body on purpose** — they are
  only mutable through their dedicated endpoints, so every change to them is guaranteed
  to append a `ticket_events` row.
- **Status transitions are guarded** by a permitted-move map; a forbidden move (e.g.
  `open` → `resolved`) returns **409**. Moving to the current status is a no-op: 200, no
  new event.
- **Escalation** is refused past level 3 or on a resolved/closed ticket (**409**); raising
  priority on an already-`urgent` ticket leaves it at `urgent` with no extra event.
- **Assigning to an inactive agent** returns **409**. Deactivating an agent does not
  unassign their open tickets — their assignment history stays intact.
- **Deleting an in-use category** returns **409** with the referencing count.
- Ticket references (`TCK-XXXXXXXX`) are derived from the ticket's own UUID, so they are
  unique without a shared counter or extra locking.

### Communication channels

Five channels — `email`, `whatsapp`, `live_chat`, `sms`, `web_form` — form a **fixed
catalogue**, seeded by migration `0003` with hard-coded ids. There is no create or
delete: only `is_enabled` and the provider `config` blob are mutable, because each slug
is what a transport driver is registered against.

| Method | Path                            | Behaviour                                       |
| ------ | ------------------------------- | ----------------------------------------------- |
| GET    | `/api/channels`                 | The catalogue; `enabled_only` filters it        |
| PATCH  | `/api/channels/{slug}`          | Enable/disable, or rewrite `config`             |
| GET    | `/api/tickets/{id}/messages`    | The ticket's thread, **oldest-first**, paginated |
| POST   | `/api/tickets/{id}/messages`    | Send an outbound reply (201)                    |
| POST   | `/api/channels/{slug}/inbound`  | Provider webhook; takes arbitrary JSON (201)    |

Behaviour worth knowing:

- **No provider adapter exists yet.** Every driver under
  `app/services/channels/` is a stub whose `send()` raises, so a `POST .../messages`
  returns **201** with `status: "failed"` and a readable `error_reason`. That is the
  expected state, not a bug — stories 21–25 replace one stub at a time.
- **Sending is best-effort by design.** The row is persisted as `queued` *before* the
  driver is called, so a transport failure is recorded on the row rather than raised.
  A send therefore never loses the attempt, and the thread stays an honest record of
  what was tried. Failed sends are not retried — an agent re-sends, appending a new row.
- **An unknown slug is a 422, not a 404** — the channel set is a `Literal` in
  `app/schemas/channel.py`, so it is rejected at the edge before any lookup.
- **A disabled channel refuses outbound (409) but still accepts inbound.** Disabling
  stops agents replying; a provider can still deliver a webhook for a conversation
  already in flight, and dropping it would lose the customer's message.
- **Inbound requires an explicit `ticket_id`.** Real routing (match by sender address,
  thread id, or reply token) belongs with the adapter that knows its provider's shape.
  Webhooks are also **unauthenticated and unverified** for the same reason.
- A ticket's **primary channel** is not a stored column — it is the channel of the
  oldest message in the thread, which is what the UI's reply box defaults to.
- `channel_messages.created_at` is stamped in Python, not by the server: SQLite's
  `CURRENT_TIMESTAMP` has only second resolution, which cannot order replies posted in
  the same second. `ticket_events.created_at` does the same, for the same reason.

## Migrations

Schema changes are Alembic migrations, never edits to `infra/postgres/init.sql`.

```bash
cd backend
alembic upgrade head            # apply
alembic downgrade -1            # roll back one revision
alembic revision --autogenerate -m "describe change"
```

`downgrade` drops the tables and their named enum types, but **not** attachment files on
disk (customer migration) or ticket history (ticket migration) — the latter is destroyed
irrecoverably on downgrade, as is every stored channel message (channel migration).

Migrations target Postgres: they emit `server_default` values such as `now()`, which
SQLite has no function for. The seed in `0003` therefore supplies its timestamps
explicitly rather than leaning on the column default.

## Tests

```bash
cd backend && pytest            # API + service tests (SQLite-backed, no live DB needed)
cd frontend && npm test         # Vitest + React Testing Library
```

The backend suite runs against a throwaway SQLite database per test, so no Postgres is
required. Postgres-specific behaviour (the partial unique index, named enums, `JSONB`) is
verified by applying the Alembic migration to the compose Postgres.

The channel catalogue is present in both places: the migration seeds it on Postgres, and
an `after_create` hook in `app/models/channel.py` seeds it on a `metadata.create_all`
database. Alembic builds its own `Table` object, so the hook cannot double-insert.

## Configuration

Backend settings are read from `backend/.env` with the `CRM_` prefix (see
`backend/.env.example`). Only `.env.example` files are tracked — `.env` is gitignored.

| Variable               | Default             | Purpose                          |
| ---------------------- | ------------------- | -------------------------------- |
| `CRM_DATABASE_URL`     | `…@db:5432/crm`     | SQLAlchemy URL                   |
| `CRM_ATTACHMENTS_DIR`  | `./var/attachments` | Attachment storage root          |
| `CRM_MAX_UPLOAD_BYTES` | `10485760` (10 MB)  | Upload ceiling; over it is a 413 |

## Known gaps

- No authentication or authorisation — `author` on interactions, and `actor` on ticket
  events, are free text. Ticket assignment uses a standalone `agents` table rather than
  real users; reconciling the two is deferred to the auth story.
- No SLA timers or scheduled auto-escalation — `Ticket.is_overdue` is computed on read
  only; nothing acts on it.
- **No channel provider is integrated** — all five drivers are stubs, so nothing is
  actually sent or received; inbound only arrives if something posts to the webhook
  endpoint directly. Channel-message attachments, live-chat presence/typing, webhook
  signature verification, and automatic inbound→ticket routing are all deferred to the
  per-channel stories.
- Attachments are not virus-scanned (`TODO` marked in `app/services/storage.py`).
- Attachment storage is local-filesystem only; S3 would slot in behind the `Storage`
  protocol in the same module.
