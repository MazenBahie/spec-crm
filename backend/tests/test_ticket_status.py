"""Status transitions: allowed/forbidden moves, idempotency, terminal stamps."""

from __future__ import annotations

from fastapi.testclient import TestClient

ALLOWED_TRANSITIONS = {
    "open": ("triaged", "in_progress", "closed"),
    "triaged": ("in_progress", "open", "closed"),
    "in_progress": ("waiting_customer", "resolved", "triaged", "closed"),
    "waiting_customer": ("in_progress", "resolved", "closed"),
    "resolved": ("closed", "in_progress"),
    "closed": ("open",),
}


def _move(client: TestClient, ticket_id: str, target: str, **extra: object) -> object:
    return client.post(f"/api/tickets/{ticket_id}/status", json={"status": target, **extra})


def test_every_allowed_transition_succeeds(client: TestClient, customer: dict) -> None:
    for start, targets in ALLOWED_TRANSITIONS.items():
        for target in targets:
            created = client.post(
                "/api/tickets",
                json={"customer_id": customer["id"], "subject": f"{start}->{target}"},
            ).json()
            # Walk from "open" (the creation default) to `start` first when needed.
            if start != "open":
                path = _walk_path_to(start)
                for step in path:
                    r = _move(client, created["id"], step)
                    assert r.status_code == 200, r.text

            res = _move(client, created["id"], target)
            assert res.status_code == 200, res.text
            assert res.json()["status"] == target


def _walk_path_to(target_status: str) -> list[str]:
    """A short, known-valid path from `open` to `target_status`."""
    paths = {
        "open": [],
        "triaged": ["triaged"],
        "in_progress": ["in_progress"],
        "waiting_customer": ["in_progress", "waiting_customer"],
        "resolved": ["in_progress", "resolved"],
        "closed": ["closed"],
    }
    return paths[target_status]


def test_forbidden_move_open_to_resolved_returns_409(
    client: TestClient, ticket: dict
) -> None:
    res = _move(client, ticket["id"], "resolved")
    assert res.status_code == 409
    assert "cannot move ticket from open to resolved" in res.json()["detail"]


def test_forbidden_move_closed_to_resolved_returns_409(
    client: TestClient, ticket: dict
) -> None:
    _move(client, ticket["id"], "closed")
    res = _move(client, ticket["id"], "resolved")
    assert res.status_code == 409


def test_same_status_is_idempotent_and_writes_no_event(
    client: TestClient, ticket: dict
) -> None:
    before = client.get(f"/api/tickets/{ticket['id']}/events").json()["total"]
    res = _move(client, ticket["id"], "open")
    assert res.status_code == 200, res.text
    after = client.get(f"/api/tickets/{ticket['id']}/events").json()["total"]
    assert after == before


def test_resolved_at_stamped_on_entry_and_cleared_on_reopen(
    client: TestClient, ticket: dict
) -> None:
    _move(client, ticket["id"], "in_progress")
    resolved = _move(client, ticket["id"], "resolved").json()
    assert resolved["resolved_at"] is not None
    assert resolved["closed_at"] is None

    reopened = _move(client, ticket["id"], "in_progress").json()
    assert reopened["resolved_at"] is None


def test_closed_at_stamped_on_entry_and_cleared_on_reopen(
    client: TestClient, ticket: dict
) -> None:
    closed = _move(client, ticket["id"], "closed").json()
    assert closed["closed_at"] is not None

    reopened = _move(client, ticket["id"], "open").json()
    assert reopened["closed_at"] is None


def test_status_change_appends_event_with_old_and_new_value(
    client: TestClient, ticket: dict
) -> None:
    _move(client, ticket["id"], "triaged", comment="looked into it", actor="dana")
    events = client.get(f"/api/tickets/{ticket['id']}/events").json()["items"]
    status_events = [e for e in events if e["event_type"] == "status_changed"]
    assert len(status_events) == 1
    event = status_events[0]
    assert event["field"] == "status"
    assert event["old_value"] == "open"
    assert event["new_value"] == "triaged"
    assert event["comment"] == "looked into it"
    assert event["actor"] == "dana"


def test_unknown_target_status_rejected_with_422(client: TestClient, ticket: dict) -> None:
    res = _move(client, ticket["id"], "made-up-status")
    assert res.status_code == 422


def test_status_change_on_unknown_ticket_returns_404(client: TestClient) -> None:
    from tests.conftest import missing_uuid

    res = _move(client, str(missing_uuid()), "triaged")
    assert res.status_code == 404
