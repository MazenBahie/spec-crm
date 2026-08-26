"""GET /api/dashboard/summary — the four counts along the top of the screen."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient


def _iso(offset: timedelta) -> str:
    return (datetime.now(timezone.utc) + offset).isoformat()


def _ticket(
    client: TestClient,
    customer: dict,
    subject: str,
    *,
    assignee_id: str | None = None,
    due_at: str | None = None,
) -> dict:
    res = client.post(
        "/api/tickets",
        json={
            "customer_id": customer["id"],
            "subject": subject,
            "assignee_id": assignee_id,
            "due_at": due_at,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _summary(agent_client: TestClient) -> dict:
    res = agent_client.get("/api/dashboard/summary")
    assert res.status_code == 200, res.text
    return res.json()


def test_summary_starts_at_zero(agent_client: TestClient) -> None:
    assert _summary(agent_client) == {
        "open_assigned": 0,
        "overdue": 0,
        "tasks_due_today": 0,
        "unread_mentions": 0,
    }


def test_open_assigned_counts_only_my_open_tickets(
    client: TestClient, agent_client: TestClient, customer: dict, agent: dict, other_agent: dict
) -> None:
    _ticket(client, customer, "mine a", assignee_id=agent["id"])
    _ticket(client, customer, "mine b", assignee_id=agent["id"])
    _ticket(client, customer, "theirs", assignee_id=other_agent["id"])
    _ticket(client, customer, "unassigned")

    closed = _ticket(client, customer, "mine closed", assignee_id=agent["id"])
    client.post(f"/api/tickets/{closed['id']}/status", json={"status": "closed"})

    assert _summary(agent_client)["open_assigned"] == 2


def test_overdue_counts_past_due_dates_only(
    client: TestClient, agent_client: TestClient, customer: dict, agent: dict
) -> None:
    _ticket(client, customer, "late", assignee_id=agent["id"], due_at=_iso(-timedelta(days=1)))
    _ticket(client, customer, "soon", assignee_id=agent["id"], due_at=_iso(timedelta(days=1)))
    _ticket(client, customer, "undated", assignee_id=agent["id"])

    summary = _summary(agent_client)
    assert summary["open_assigned"] == 3
    assert summary["overdue"] == 1


def test_a_closed_ticket_is_never_overdue(
    client: TestClient, agent_client: TestClient, customer: dict, agent: dict
) -> None:
    """Overdue is a subset of the queue: finishing late still means finished."""
    late = _ticket(
        client, customer, "late", assignee_id=agent["id"], due_at=_iso(-timedelta(days=1))
    )
    client.post(f"/api/tickets/{late['id']}/status", json={"status": "closed"})

    assert _summary(agent_client)["overdue"] == 0


def test_tasks_due_today_counts_open_reminders_inside_the_utc_day(
    agent_client: TestClient,
) -> None:
    now = datetime.now(timezone.utc)
    # Nudged off both boundaries so a run near midnight cannot straddle the day.
    inside = now.replace(hour=12, minute=0, second=0, microsecond=0)

    agent_client.post("/api/tasks", json={"title": "today", "remind_at": inside.isoformat()})
    agent_client.post(
        "/api/tasks",
        json={"title": "in three days", "remind_at": _iso(timedelta(days=3))},
    )
    agent_client.post(
        "/api/tasks",
        json={"title": "three days ago", "remind_at": _iso(-timedelta(days=3))},
    )
    agent_client.post("/api/tasks", json={"title": "someday, no date"})

    done = agent_client.post(
        "/api/tasks", json={"title": "already done", "remind_at": inside.isoformat()}
    ).json()
    agent_client.post(f"/api/tasks/{done['id']}/complete")

    assert _summary(agent_client)["tasks_due_today"] == 1


def test_unread_mentions_counts_being_named_by_someone_else(
    client: TestClient,
    agent_client: TestClient,
    other_agent_client: TestClient,
    customer: dict,
    agent: dict,
) -> None:
    res = client.post(
        "/api/tickets", json={"customer_id": customer["id"], "subject": "shared"}
    )
    ticket_id = res.json()["id"]

    other_agent_client.post(
        f"/api/tickets/{ticket_id}/notes", json={"body": "@dana can you take this?"}
    )

    assert _summary(agent_client)["unread_mentions"] == 1


def test_mentioning_yourself_does_not_count(
    client: TestClient, agent_client: TestClient, customer: dict
) -> None:
    """Otherwise every note you write about yourself lights up your own badge."""
    res = client.post(
        "/api/tickets", json={"customer_id": customer["id"], "subject": "solo"}
    )
    agent_client.post(
        f"/api/tickets/{res.json()['id']}/notes", json={"body": "note to @dana: follow up"}
    )

    assert _summary(agent_client)["unread_mentions"] == 0


def test_summary_is_per_agent(
    client: TestClient,
    agent_client: TestClient,
    other_agent_client: TestClient,
    customer: dict,
    agent: dict,
) -> None:
    _ticket(client, customer, "mine", assignee_id=agent["id"])
    agent_client.post("/api/tasks", json={"title": "mine too"})

    assert _summary(agent_client)["open_assigned"] == 1
    assert _summary(other_agent_client) == {
        "open_assigned": 0,
        "overdue": 0,
        "tasks_due_today": 0,
        "unread_mentions": 0,
    }
