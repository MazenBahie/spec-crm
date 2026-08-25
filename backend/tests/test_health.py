import pytest
from fastapi.testclient import TestClient

from app.api.routes import health as health_route
from app.main import create_app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def test_health_returns_ok(client: TestClient) -> None:
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_health_db_degrades_when_engine_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom() -> None:
        raise RuntimeError("connection refused")

    monkeypatch.setattr(health_route, "get_engine", boom)

    res = client.get("/api/health/db")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "degraded"
    assert body["database"] == "unreachable"
    assert "connection refused" in body["detail"]
