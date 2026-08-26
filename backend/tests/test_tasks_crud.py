"""Agent tasks and reminders: CRUD, ownership, and completion idempotency."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from tests.conftest import missing_uuid


def _iso(offset: timedelta) -> str:
    return (datetime.now(timezone.utc) + offset).isoformat()


def _create(agent_client: TestClient, title: str, **extra) -> dict:
    res = agent_client.post("/api/tasks", json={"title": title, **extra})
    assert res.status_code == 201, res.text
    return res.json()


def test_create_and_read_back(agent_client: TestClient, agent: dict) -> None:
    task = _create(agent_client, "call Ali", notes="about the invoice")

    assert task["title"] == "call Ali"
    assert task["notes"] == "about the invoice"
    assert task["status"] == "open"
    assert task["completed_at"] is None
    assert task["agent_id"] == agent["id"]
    assert task["ticket_id"] is None

    fetched = agent_client.get(f"/api/tasks/{task['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == task["id"]


def test_title_is_required_and_bounded(agent_client: TestClient) -> None:
    assert agent_client.post("/api/tasks", json={"title": ""}).status_code == 422
    assert agent_client.post("/api/tasks", json={"title": "x" * 201}).status_code == 422
    assert agent_client.post("/api/tasks", json={"title": "x" * 200}).status_code == 201


def test_tasks_may_link_to_a_ticket_and_customer(
    agent_client: TestClient, ticket: dict, customer: dict
) -> None:
    task = _create(
        agent_client, "chase", ticket_id=ticket["id"], customer_id=customer["id"]
    )
    assert task["ticket_id"] == ticket["id"]
    assert task["customer_id"] == customer["id"]


def test_a_link_to_a_missing_row_is_rejected(agent_client: TestClient) -> None:
    """404 from the service rather than a raw FK error out of the driver."""
    res = agent_client.post(
        "/api/tasks", json={"title": "chase", "ticket_id": str(missing_uuid())}
    )
    assert res.status_code == 404, res.text


def test_a_deleted_ticket_leaves_the_task_behind(
    agent_client: TestClient, client: TestClient, ticket: dict
) -> None:
    """ON DELETE SET NULL: the reminder survives, pointing at nothing."""
    task = _create(agent_client, "chase", ticket_id=ticket["id"])
    assert client.delete(f"/api/tickets/{ticket['id']}").status_code == 204

    survivor = agent_client.get(f"/api/tasks/{task['id']}")
    assert survivor.status_code == 200, survivor.text
    assert survivor.json()["ticket_id"] is None


def test_list_is_scoped_to_the_caller(
    agent_client: TestClient, other_agent_client: TestClient
) -> None:
    _create(agent_client, "mine")
    _create(other_agent_client, "theirs")

    assert [t["title"] for t in agent_client.get("/api/tasks").json()] == ["mine"]
    assert [t["title"] for t in other_agent_client.get("/api/tasks").json()] == ["theirs"]


def test_list_sorts_soonest_reminder_first_with_undated_last(
    agent_client: TestClient,
) -> None:
    _create(agent_client, "undated")
    _create(agent_client, "next week", remind_at=_iso(timedelta(days=7)))
    _create(agent_client, "tomorrow", remind_at=_iso(timedelta(days=1)))

    titles = [t["title"] for t in agent_client.get("/api/tasks").json()]
    assert titles == ["tomorrow", "next week", "undated"]


def test_list_filters_by_status_and_due_date(agent_client: TestClient) -> None:
    soon = _create(agent_client, "soon", remind_at=_iso(timedelta(hours=1)))
    _create(agent_client, "later", remind_at=_iso(timedelta(days=30)))
    _create(agent_client, "undated")
    agent_client.post(f"/api/tasks/{soon['id']}/complete")

    open_titles = [t["title"] for t in agent_client.get("/api/tasks?status=open").json()]
    assert sorted(open_titles) == ["later", "undated"]

    done_titles = [t["title"] for t in agent_client.get("/api/tasks?status=done").json()]
    assert done_titles == ["soon"]

    # An undated task is never "due before" anything. Passed as a param, not
    # interpolated: the "+00:00" offset would decode as a space in a raw query.
    due = agent_client.get(
        "/api/tasks", params={"due_before": _iso(timedelta(days=2))}
    ).json()
    assert [t["title"] for t in due] == ["soon"]


def test_update_edits_fields(agent_client: TestClient) -> None:
    task = _create(agent_client, "draft")
    res = agent_client.patch(
        f"/api/tasks/{task['id']}", json={"title": "final", "notes": "rewritten"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["title"] == "final"
    assert res.json()["notes"] == "rewritten"


def test_complete_stamps_completed_at_and_is_idempotent(
    agent_client: TestClient,
) -> None:
    task = _create(agent_client, "finish me")

    first = agent_client.post(f"/api/tasks/{task['id']}/complete")
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "done"
    assert first.json()["completed_at"] is not None

    second = agent_client.post(f"/api/tasks/{task['id']}/complete")
    assert second.status_code == 200
    # Unchanged, so a double-clicked checkbox does not rewrite history.
    assert second.json()["completed_at"] == first.json()["completed_at"]


def test_reopening_clears_completed_at(agent_client: TestClient) -> None:
    task = _create(agent_client, "not done after all")
    agent_client.post(f"/api/tasks/{task['id']}/complete")

    reopened = agent_client.post(f"/api/tasks/{task['id']}/reopen")
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["status"] == "open"
    assert reopened.json()["completed_at"] is None


def test_status_can_also_be_moved_by_patch(agent_client: TestClient) -> None:
    task = _create(agent_client, "via patch")
    res = agent_client.patch(f"/api/tasks/{task['id']}", json={"status": "done"})
    assert res.status_code == 200, res.text
    assert res.json()["completed_at"] is not None


def test_delete_removes_the_task(agent_client: TestClient) -> None:
    task = _create(agent_client, "gone")
    assert agent_client.delete(f"/api/tasks/{task['id']}").status_code == 204
    assert agent_client.get(f"/api/tasks/{task['id']}").status_code == 404


def test_another_agents_task_is_forbidden_not_hidden(
    agent_client: TestClient, other_agent_client: TestClient
) -> None:
    """403, not 404: both agents are trusted staff, and pretending the row does
    not exist would only make a mis-set X-Agent-Id harder to diagnose."""
    task = _create(agent_client, "mine")

    assert other_agent_client.get(f"/api/tasks/{task['id']}").status_code == 403
    assert (
        other_agent_client.patch(f"/api/tasks/{task['id']}", json={"title": "hijack"}).status_code
        == 403
    )
    assert other_agent_client.post(f"/api/tasks/{task['id']}/complete").status_code == 403
    assert other_agent_client.delete(f"/api/tasks/{task['id']}").status_code == 403

    # And it really was left alone.
    assert agent_client.get(f"/api/tasks/{task['id']}").json()["title"] == "mine"


def test_unknown_task_is_not_found(agent_client: TestClient) -> None:
    assert agent_client.get(f"/api/tasks/{missing_uuid()}").status_code == 404
