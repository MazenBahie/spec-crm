"""The X-Agent-Id gate on every agent-scoped route.

Placeholder auth, but the gate itself is real: no header, a malformed one, an
unknown agent and a deactivated agent all answer 401 so the frontend has a
single branch to handle.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import missing_uuid

# One representative route per agent-scoped router, so a router registered
# without the dependency shows up here rather than in production.
GATED_ROUTES = [
    "/api/dashboard/summary",
    "/api/dashboard/queue",
    "/api/dashboard/recent-customers",
    "/api/dashboard/activity",
    "/api/tasks",
    "/api/quick-replies",
]


@pytest.mark.parametrize("path", GATED_ROUTES)
def test_missing_header_is_unauthorised(client: TestClient, path: str) -> None:
    res = client.get(path)
    assert res.status_code == 401, res.text
    assert "X-Agent-Id" in res.json()["detail"]


@pytest.mark.parametrize("path", GATED_ROUTES)
def test_valid_header_is_accepted(agent_client: TestClient, path: str) -> None:
    assert agent_client.get(path).status_code == 200


def test_unknown_agent_is_unauthorised(client: TestClient) -> None:
    res = client.get("/api/dashboard/summary", headers={"X-Agent-Id": str(missing_uuid())})
    assert res.status_code == 401, res.text


def test_unparseable_agent_id_is_unauthorised(client: TestClient) -> None:
    """A non-uuid header is 401, not a 422 — it is a failed identification,
    not a malformed request body."""
    res = client.get("/api/dashboard/summary", headers={"X-Agent-Id": "not-a-uuid"})
    assert res.status_code == 401, res.text


def test_blank_agent_id_is_unauthorised(client: TestClient) -> None:
    res = client.get("/api/dashboard/summary", headers={"X-Agent-Id": "   "})
    assert res.status_code == 401, res.text


def test_deactivated_agent_is_unauthorised(
    client: TestClient, inactive_agent: dict
) -> None:
    """An agent deactivated mid-session loses access on their next request."""
    res = client.get(
        "/api/dashboard/summary", headers={"X-Agent-Id": inactive_agent["id"]}
    )
    assert res.status_code == 401, res.text


def test_ticket_notes_require_an_agent(client: TestClient, ticket: dict) -> None:
    """The note routes live on the otherwise-open tickets router, so they are
    gated per-route — assert that gate independently."""
    assert client.get(f"/api/tickets/{ticket['id']}/notes").status_code == 401
    assert (
        client.post(f"/api/tickets/{ticket['id']}/notes", json={"body": "psst"}).status_code
        == 401
    )


def test_pre_existing_routes_stay_open(client: TestClient, customer: dict) -> None:
    """Regression guard: gating the new routers must not gate the old ones.

    Real auth is a follow-up story that will close these deliberately; until
    then an accidental router-level dependency would break every existing
    caller.
    """
    assert client.get("/api/customers").status_code == 200
    assert client.get("/api/tickets").status_code == 200
    assert client.get("/api/channels").status_code == 200
    assert client.get("/api/health").status_code == 200
