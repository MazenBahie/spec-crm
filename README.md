# CRM

A CRM product. **Status: scaffold only** — this repository currently contains the
full-stack skeleton (FastAPI + React + Postgres) and no CRM domain logic. Customers,
deals, pipelines, auth, and migrations arrive in later stories.

## Layout

```
backend/            FastAPI service
  app/
    main.py         app factory + CORS + router wiring
    core/config.py  pydantic-settings (env prefix CRM_)
    api/routes/     HTTP routes (health.py)
    db/session.py   lazy SQLAlchemy engine factory
  tests/            pytest suite
  Dockerfile
frontend/           React 18 + Vite + TypeScript
  src/
    main.tsx        React entry
    App.tsx
    api/client.ts   typed backend client
    pages/          HealthPage.tsx
  Dockerfile
infra/              container topology
  docker-compose.yml
  postgres/init.sql (reserved, intentionally empty)
```

The three concerns are **backend/**, **frontend/**, and **infra/**. Future CRM domain
modules go under `backend/app/` as sibling packages to `api/` and `db/` (e.g.
`backend/app/customers/`, `backend/app/deals/`).

## Quickstart (Docker)

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
docker compose -f infra/docker-compose.yml up --build
```

Then open <http://localhost:5173> — the page must show `status: ok` from the backend.

| Service  | URL                            |
| -------- | ------------------------------ |
| frontend | http://localhost:5173          |
| backend  | http://localhost:8000/api/health |
| db       | postgres://crm:crm@localhost:5432/crm |

Postgres is gated by a `pg_isready` healthcheck and the backend waits on it via
`depends_on.condition: service_healthy`.

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
uvicorn app.main:app --reload
```

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

| Method | Path              | Behaviour                                                     |
| ------ | ----------------- | ------------------------------------------------------------- |
| GET    | `/api/health`     | `{"status": "ok"}` — never touches the database                |
| GET    | `/api/health/db`  | `reachable`, or `degraded` + driver error when Postgres is down |

## Tests

```bash
cd backend && pytest
```

Frontend automated tests are out of scope for the scaffold; verify manually by loading
the health page.

## Configuration

Backend settings are read from `backend/.env` with the `CRM_` prefix (see
`backend/.env.example`). Only `.env.example` files are tracked — `.env` is gitignored.
