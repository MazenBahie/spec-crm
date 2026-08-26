"""Shared test fixtures.

The suite runs against a file-backed SQLite database created fresh per test, so
no live Postgres is required. Postgres-specific behaviour (the partial unique
index, named enums) is exercised by the Alembic migration itself; SQLite honours
``sqlite_where`` so the single-primary-per-kind index is real here too.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.session import get_db
from app.main import create_app
from app.models import Base
from app.services.storage import LocalFileStorage, get_storage


@event.listens_for(Engine, "connect")
def _sqlite_enforce_foreign_keys(dbapi_connection, _record) -> None:
    """SQLite ignores FK constraints unless asked; cascades depend on this."""
    if type(dbapi_connection).__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


@pytest.fixture()
def attachments_dir(tmp_path: Path) -> Path:
    path = tmp_path / "attachments"
    path.mkdir()
    return path


@pytest.fixture()
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = create_engine(f"sqlite+pysqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def db(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """Direct session for service-layer assertions."""
    with session_factory() as session:
        yield session


@pytest.fixture()
def storage(attachments_dir: Path) -> LocalFileStorage:
    return LocalFileStorage(root=attachments_dir)


@pytest.fixture()
def app(
    session_factory: sessionmaker[Session], attachments_dir: Path
) -> Iterator[FastAPI]:
    application = create_app()

    def override_get_db() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # Built per request so a test can shrink settings.max_upload_bytes mid-run.
    def override_get_storage() -> LocalFileStorage:
        return LocalFileStorage(root=attachments_dir)

    application.dependency_overrides[get_db] = override_get_db
    application.dependency_overrides[get_storage] = override_get_storage
    yield application
    application.dependency_overrides.clear()


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def customer(client: TestClient) -> dict:
    """One persisted active customer."""
    res = client.post(
        "/api/customers", json={"display_name": "Acme Corp", "company": "Acme"}
    )
    assert res.status_code == 201, res.text
    return res.json()


@pytest.fixture()
def small_upload_limit(monkeypatch: pytest.MonkeyPatch) -> int:
    """Shrink the upload ceiling so oversize tests stay fast."""
    limit = 1024
    monkeypatch.setattr(settings, "max_upload_bytes", limit)
    return limit


@pytest.fixture()
def agent(client: TestClient) -> dict:
    """One active agent."""
    res = client.post(
        "/api/agents", json={"display_name": "Dana Support", "email": "dana@crm.test"}
    )
    assert res.status_code == 201, res.text
    return res.json()


@pytest.fixture()
def inactive_agent(client: TestClient) -> dict:
    """One deactivated agent — assignment to them must be refused."""
    res = client.post(
        "/api/agents", json={"display_name": "Retired Agent", "email": "retired@crm.test"}
    )
    assert res.status_code == 201, res.text
    created = res.json()
    deactivated = client.delete(f"/api/agents/{created['id']}")
    assert deactivated.status_code == 200, deactivated.text
    return deactivated.json()


@pytest.fixture()
def other_agent(client: TestClient) -> dict:
    """A second active agent, for "not yours" and mention assertions."""
    res = client.post(
        "/api/agents", json={"display_name": "Omar Night", "email": "omar@crm.test"}
    )
    assert res.status_code == 201, res.text
    return res.json()


@pytest.fixture()
def agent_client(app: FastAPI, agent: dict) -> Iterator[TestClient]:
    """A client that identifies as `agent` on every request.

    Separate from `client` on purpose: the pre-existing routers are still
    unauthenticated, and their tests must keep proving that.
    """
    with TestClient(app, headers={"X-Agent-Id": agent["id"]}) as test_client:
        yield test_client


@pytest.fixture()
def other_agent_client(app: FastAPI, other_agent: dict) -> Iterator[TestClient]:
    """A client that identifies as `other_agent`."""
    with TestClient(app, headers={"X-Agent-Id": other_agent["id"]}) as test_client:
        yield test_client


@pytest.fixture()
def ticket_category(client: TestClient) -> dict:
    """One active category with a non-default priority, to prove inheritance."""
    res = client.post(
        "/api/ticket-categories",
        json={"name": "Billing", "default_priority": "high"},
    )
    assert res.status_code == 201, res.text
    return res.json()


@pytest.fixture()
def ticket(client: TestClient, customer: dict) -> dict:
    """One open ticket on `customer`, with no category or assignee."""
    res = client.post(
        "/api/tickets",
        json={
            "customer_id": customer["id"],
            "subject": "Cannot log in",
            "description": "Password reset email never arrives.",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def missing_uuid() -> uuid.UUID:
    return uuid.uuid4()
