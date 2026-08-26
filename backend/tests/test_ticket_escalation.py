"""Escalation: level increments, priority bump, and the guard rails around it."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _escalate(client: TestClient, ticket_id: str, **body: object):
    return client.post(f"/api/tickets/{ticket_id}/escalate", json=body)


def test_escalate_increments_level_and_stamps_escalated_at(
    client: TestClient, ticket: dict
) -> None:
    assert ticket["escalation_level"] == 0
    res = _escalate(client, ticket["id"], comment="customer is furious")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["escalation_level"] == 1
    assert body["escalated_at"] is not None


def test_escalate_writes_an_escalated_event(client: TestClient, ticket: dict) -> None:
    _escalate(client, ticket["id"], actor="dana", comment="bumping")
    events = client.get(f"/api/tickets/{ticket['id']}/events").json()["items"]
    escalated = [e for e in events if e["event_type"] == "escalated"]
    assert len(escalated) == 1
    assert escalated[0]["old_value"] == "0"
    assert escalated[0]["new_value"] == "1"
    assert escalated[0]["actor"] == "dana"
    assert escalated[0]["comment"] == "bumping"


def test_raise_priority_true_bumps_normal_to_high(client: TestClient, ticket: dict) -> None:
    assert ticket["priority"] == "normal"
    res = _escalate(client, ticket["id"], raise_priority=True)
    assert res.status_code == 200, res.text
    assert res.json()["priority"] == "high"

    events = client.get(f"/api/tickets/{ticket['id']}/events").json()["items"]
    priority_events = [e for e in events if e["event_type"] == "priority_changed"]
    assert len(priority_events) == 1
    assert priority_events[0]["old_value"] == "normal"
    assert priority_events[0]["new_value"] == "high"


def test_raise_priority_false_leaves_priority_unchanged(
    client: TestClient, ticket: dict
) -> None:
    res = _escalate(client, ticket["id"], raise_priority=False)
    assert res.status_code == 200, res.text
    assert res.json()["priority"] == "normal"

    events = client.get(f"/api/tickets/{ticket['id']}/events").json()["items"]
    assert not [e for e in events if e["event_type"] == "priority_changed"]


def test_escalating_urgent_ticket_keeps_urgent_and_emits_no_priority_event(
    client: TestClient, customer: dict
) -> None:
    urgent = client.post(
        "/api/tickets",
        json={"customer_id": customer["id"], "subject": "already urgent", "priority": "urgent"},
    ).json()

    res = _escalate(client, urgent["id"], raise_priority=True)
    assert res.status_code == 200, res.text
    assert res.json()["priority"] == "urgent"

    events = client.get(f"/api/tickets/{urgent['id']}/events").json()["items"]
    assert not [e for e in events if e["event_type"] == "priority_changed"]


def test_escalate_past_max_level_returns_409(client: TestClient, ticket: dict) -> None:
    for _ in range(3):
        res = _escalate(client, ticket["id"], raise_priority=False)
        assert res.status_code == 200, res.text
    assert res.json()["escalation_level"] == 3

    res = _escalate(client, ticket["id"], raise_priority=False)
    assert res.status_code == 409
    assert "maximum escalation level" in res.json()["detail"]


def test_escalate_resolved_ticket_returns_409(client: TestClient, ticket: dict) -> None:
    client.post(f"/api/tickets/{ticket['id']}/status", json={"status": "in_progress"})
    client.post(f"/api/tickets/{ticket['id']}/status", json={"status": "resolved"})
    res = _escalate(client, ticket["id"])
    assert res.status_code == 409


def test_escalate_closed_ticket_returns_409(client: TestClient, ticket: dict) -> None:
    client.post(f"/api/tickets/{ticket['id']}/status", json={"status": "closed"})
    res = _escalate(client, ticket["id"])
    assert res.status_code == 409
