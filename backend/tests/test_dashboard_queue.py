"""GET /api/dashboard/queue — "what am I working on".

Covers the two rules that make the queue useful: only *my* *open* tickets, and
the ordering urgent-first, then soonest due, with undated tickets last.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient


def _iso(offset_days: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=offset_days)).isoformat()


def _make_ticket(
    client: TestClient,
    customer: dict,
    subject: str,
    *,
    assignee_id: str | None = None,
    priority: str = "normal",
    due_at: str | None = None,
) -> dict:
    res = client.post(
        "/api/tickets",
        json={
            "customer_id": customer["id"],
            "subject": subject,
            "priority": priority,
            "assignee_id": assignee_id,
            "due_at": due_at,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _subjects(res) -> list[str]:
    assert res.status_code == 200, res.text
    return [t["subject"] for t in res.json()]


def test_empty_queue(agent_client: TestClient) -> None:
    assert agent_client.get("/api/dashboard/queue").json() == []


def test_queue_holds_only_my_open_tickets(
    client: TestClient, agent_client: TestClient, customer: dict, agent: dict, other_agent: dict
) -> None:
    mine = _make_ticket(client, customer, "mine open", assignee_id=agent["id"])
    _make_ticket(client, customer, "theirs", assignee_id=other_agent["id"])
    _make_ticket(client, customer, "nobody's")

    closed = _make_ticket(client, customer, "mine closed", assignee_id=agent["id"])
    assert (
        client.post(f"/api/tickets/{closed['id']}/status", json={"status": "closed"}).status_code
        == 200
    )

    resolved = _make_ticket(client, customer, "mine resolved", assignee_id=agent["id"])
    for target in ("in_progress", "resolved"):
        assert (
            client.post(
                f"/api/tickets/{resolved['id']}/status", json={"status": target}
            ).status_code
            == 200
        )

    assert _subjects(agent_client.get("/api/dashboard/queue")) == [mine["subject"]]


def test_queue_keeps_non_terminal_statuses(
    client: TestClient, agent_client: TestClient, customer: dict, agent: dict
) -> None:
    """`waiting_customer` is still my problem — only resolved/closed drop out."""
    ticket = _make_ticket(client, customer, "waiting", assignee_id=agent["id"])
    for target in ("in_progress", "waiting_customer"):
        client.post(f"/api/tickets/{ticket['id']}/status", json={"status": target})

    assert _subjects(agent_client.get("/api/dashboard/queue")) == ["waiting"]


def test_queue_sorts_by_priority_then_due_date(
    client: TestClient, agent_client: TestClient, customer: dict, agent: dict
) -> None:
    """Urgent before high before normal; within a priority, soonest due first
    and undated last."""
    # Created deliberately out of order, so passing cannot be an accident of
    # insertion order.
    _make_ticket(client, customer, "normal", assignee_id=agent["id"], priority="normal")
    _make_ticket(
        client, customer, "urgent undated", assignee_id=agent["id"], priority="urgent"
    )
    _make_ticket(
        client,
        customer,
        "urgent later",
        assignee_id=agent["id"],
        priority="urgent",
        due_at=_iso(3),
    )
    _make_ticket(
        client, customer, "high", assignee_id=agent["id"], priority="high", due_at=_iso(1)
    )
    _make_ticket(
        client,
        customer,
        "urgent overdue",
        assignee_id=agent["id"],
        priority="urgent",
        due_at=_iso(-1),
    )

    assert _subjects(agent_client.get("/api/dashboard/queue")) == [
        "urgent overdue",
        "urgent later",
        "urgent undated",
        "high",
        "normal",
    ]


def test_queue_marks_overdue_tickets(
    client: TestClient, agent_client: TestClient, customer: dict, agent: dict
) -> None:
    _make_ticket(
        client, customer, "late", assignee_id=agent["id"], due_at=_iso(-2)
    )
    _make_ticket(client, customer, "fine", assignee_id=agent["id"], due_at=_iso(2))

    by_subject = {t["subject"]: t for t in agent_client.get("/api/dashboard/queue").json()}
    assert by_subject["late"]["is_overdue"] is True
    assert by_subject["fine"]["is_overdue"] is False


def test_queue_respects_the_limit(
    client: TestClient, agent_client: TestClient, customer: dict, agent: dict
) -> None:
    for index in range(3):
        _make_ticket(client, customer, f"t{index}", assignee_id=agent["id"])

    assert len(agent_client.get("/api/dashboard/queue?limit=2").json()) == 2
    assert agent_client.get("/api/dashboard/queue?limit=0").status_code == 422


def test_recent_customers_lists_who_i_helped(
    client: TestClient, agent_client: TestClient, customer: dict, agent: dict, other_agent: dict
) -> None:
    other = client.post("/api/customers", json={"display_name": "Globex"}).json()
    _make_ticket(client, customer, "mine", assignee_id=agent["id"])
    _make_ticket(client, other, "theirs", assignee_id=other_agent["id"])

    res = agent_client.get("/api/dashboard/recent-customers")
    assert res.status_code == 200, res.text
    assert [c["display_name"] for c in res.json()] == [customer["display_name"]]


def test_recent_customers_deduplicates(
    client: TestClient, agent_client: TestClient, customer: dict, agent: dict
) -> None:
    """Two tickets on one customer is still one row in the snapshot."""
    _make_ticket(client, customer, "one", assignee_id=agent["id"])
    _make_ticket(client, customer, "two", assignee_id=agent["id"])

    assert len(agent_client.get("/api/dashboard/recent-customers").json()) == 1


def test_recent_customers_includes_finished_work(
    client: TestClient, agent_client: TestClient, customer: dict, agent: dict
) -> None:
    """Unlike the queue, this panel keeps closed tickets — "who did I just
    finish with" is the whole point."""
    ticket = _make_ticket(client, customer, "done", assignee_id=agent["id"])
    client.post(f"/api/tickets/{ticket['id']}/status", json={"status": "closed"})

    assert len(agent_client.get("/api/dashboard/recent-customers").json()) == 1
