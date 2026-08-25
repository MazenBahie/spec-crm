# CRM

A CRM product built on FastAPI + React + Postgres.

**Status:** customer management is implemented — profiles, contact details, interaction
history, notes, and file attachments. Deals, pipelines, and authentication arrive in
later stories.

## Layout

```
backend/            FastAPI service
  app/
    main.py         app factory + CORS + router wiring + error handlers
    core/config.py  pydantic-settings (env prefix CRM_)
    api/routes/     HTTP routes (health.py, customers.py)
    db/
      base.py       declarative Base
      session.py    lazy engine + get_db dependency
    models/         ORM models (customer.py)
    schemas/        Pydantic request/response models
    services/       business logic, attachment storage, error types
  alembic/          migrations (versions/0001_customer_management.py)
  tests/            pytest suite
  Dockerfile
frontend/           React 18 + Vite + TypeScript
  src/
    main.tsx        React entry (BrowserRouter)
    App.tsx         nav + routes
    api/            client.ts (fetch helpers) + customers.ts (endpoints)
    types/          TypeScript mirrors of the API schemas
    pages/          HealthPage, CustomersListPage, CustomerDetailPage, CustomerEditPage
    components/     ui.tsx atoms + customer/ panels
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

Then open <http://localhost:5173> — the health page shows `status: ok`, and
<http://localhost:5173/customers> lists the customer directory.

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

## Migrations

Schema changes are Alembic migrations, never edits to `infra/postgres/init.sql`.

```bash
cd backend
alembic upgrade head            # apply
alembic downgrade -1            # roll back one revision
alembic revision --autogenerate -m "describe change"
```

`downgrade` drops the tables and their named enum types, but **not** attachment files on
disk — clean those up manually under `CRM_ATTACHMENTS_DIR`.

## Tests

```bash
cd backend && pytest            # API + service tests (SQLite-backed, no live DB needed)
cd frontend && npm test         # Vitest + React Testing Library
```

The backend suite runs against a throwaway SQLite database per test, so no Postgres is
required. Postgres-specific behaviour (the partial unique index, named enums) is verified
by applying the Alembic migration to the compose Postgres.

## Configuration

Backend settings are read from `backend/.env` with the `CRM_` prefix (see
`backend/.env.example`). Only `.env.example` files are tracked — `.env` is gitignored.

| Variable               | Default             | Purpose                          |
| ---------------------- | ------------------- | -------------------------------- |
| `CRM_DATABASE_URL`     | `…@db:5432/crm`     | SQLAlchemy URL                   |
| `CRM_ATTACHMENTS_DIR`  | `./var/attachments` | Attachment storage root          |
| `CRM_MAX_UPLOAD_BYTES` | `10485760` (10 MB)  | Upload ceiling; over it is a 413 |

## Known gaps

- No authentication or authorisation — `author` on interactions is free text.
- Attachments are not virus-scanned (`TODO` marked in `app/services/storage.py`).
- Attachment storage is local-filesystem only; S3 would slot in behind the `Storage`
  protocol in the same module.
