"""Ticket assignment: assign, reassign, unassign, and the filters that use it."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import missing_uuid


def _assign(client: TestClient, ticket_id: str, assignee_id: str | None, **extra: object):
    return client.post(
        f"/api/tickets/{ticket_id}/assignment",
        json={"assignee_id": assignee_id, **extra},
    )


def test_assign_sets_assignee_and_writes_event(
    client: TestClient, ticket: dict, agent: dict
) -> None:
    res = _assign(client, ticket["id"], agent["id"], actor="ops")
    assert res.status_code == 200, res.text
    assert res.json()["assignee_id"] == agent["id"]

    events = client.get(f"/api/tickets/{ticket['id']}/events").json()["items"]
    assigned = [e for e in events if e["event_type"] == "assigned"]
    assert len(assigned) == 1
    assert assigned[0]["new_value"] == agent["id"]
    assert assigned[0]["old_value"] is None
    assert assigned[0]["actor"] == "ops"


def test_reassign_to_a_different_agent(client: TestClient, ticket: dict) -> None:
    first = client.post("/api/agents", json={"display_name": "First"}).json()
    second = client.post("/api/agents", json={"display_name": "Second"}).json()

    _assign(client, ticket["id"], first["id"])
    res = _assign(client, ticket["id"], second["id"])
    assert res.status_code == 200, res.text
    assert res.json()["assignee_id"] == second["id"]

    events = [
        e
        for e in client.get(f"/api/tickets/{ticket['id']}/events").json()["items"]
        if e["event_type"] == "assigned"
    ]
    assert len(events) == 2


def test_unassign_clears_assignee_and_writes_event(
    client: TestClient, ticket: dict, agent: dict
) -> None:
    _assign(client, ticket["id"], agent["id"])
    res = _assign(client, ticket["id"], None)
    assert res.status_code == 200, res.text
    assert res.json()["assignee_id"] is None

    events = client.get(f"/api/tickets/{ticket['id']}/events").json()["items"]
    unassigned = [e for e in events if e["event_type"] == "unassigned"]
    assert len(unassigned) == 1
    assert unassigned[0]["old_value"] == agent["id"]
    assert unassigned[0]["new_value"] is None


def test_reassigning_same_agent_is_idempotent_and_writes_no_event(
    client: TestClient, ticket: dict, agent: dict
) -> None:
    _assign(client, ticket["id"], agent["id"])
    before = client.get(f"/api/tickets/{ticket['id']}/events").json()["total"]

    res = _assign(client, ticket["id"], agent["id"])
    assert res.status_code == 200, res.text

    after = client.get(f"/api/tickets/{ticket['id']}/events").json()["total"]
    assert after == before


def test_assign_to_inactive_agent_returns_409(
    client: TestClient, ticket: dict, inactive_agent: dict
) -> None:
    res = _assign(client, ticket["id"], inactive_agent["id"])
    assert res.status_code == 409


def test_assign_to_unknown_agent_returns_404(client: TestClient, ticket: dict) -> None:
    res = _assign(client, ticket["id"], str(missing_uuid()))
    assert res.status_code == 404


def test_assign_on_terminal_ticket_returns_409(client: TestClient, ticket: dict, agent: dict) -> None:
    client.post(f"/api/tickets/{ticket['id']}/status", json={"status": "closed"})
    res = _assign(client, ticket["id"], agent["id"])
    assert res.status_code == 409


def test_deactivating_agent_leaves_existing_assignment_intact(
    client: TestClient, ticket: dict, agent: dict
) -> None:
    _assign(client, ticket["id"], agent["id"])
    client.delete(f"/api/agents/{agent['id']}")

    body = client.get(f"/api/tickets/{ticket['id']}").json()
    assert body["assignee_id"] == agent["id"]


def test_unassigned_filter(client: TestClient, ticket: dict, agent: dict) -> None:
    other = client.post(
        "/api/tickets",
        json={"customer_id": ticket["customer_id"], "subject": "has an owner"},
    ).json()
    _assign(client, other["id"], agent["id"])

    body = client.get("/api/tickets", params={"unassigned": "true"}).json()
    ids = {t["id"] for t in body["items"]}
    assert ticket["id"] in ids
    assert other["id"] not in ids


def test_assignee_id_filter(client: TestClient, ticket: dict, agent: dict) -> None:
    _assign(client, ticket["id"], agent["id"])
    body = client.get("/api/tickets", params={"assignee_id": agent["id"]}).json()
    assert [t["id"] for t in body["items"]] == [ticket["id"]]
