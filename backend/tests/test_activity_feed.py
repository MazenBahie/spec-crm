"""The team activity feed.

Two things matter here: that the four interesting ticket events are recorded at
all, and that ``feed_for_agent`` shows each of them to exactly the right people
— the actor, the assignee, and anyone named — and to nobody else.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def third_agent(client: TestClient) -> dict:
    """An agent with no stake in anything, to prove the feed is not a firehose."""
    res = client.post(
        "/api/agents", json={"display_name": "Sara Bystander", "email": "sara@crm.test"}
    )
    assert res.status_code == 201, res.text
    return res.json()


@pytest.fixture()
def third_agent_client(app, third_agent: dict):
    with TestClient(app, headers={"X-Agent-Id": third_agent["id"]}) as test_client:
        yield test_client


def _feed(client: TestClient) -> list[dict]:
    res = client.get("/api/dashboard/activity")
    assert res.status_code == 200, res.text
    return res.json()


def _types(client: TestClient) -> set[str]:
    return {e["event_type"] for e in _feed(client)}


def test_an_empty_feed(agent_client: TestClient) -> None:
    assert _feed(agent_client) == []


def test_creating_a_ticket_already_assigned_is_an_assignment(
    client: TestClient, agent_client: TestClient, customer: dict, agent: dict
) -> None:
    res = client.post(
        "/api/tickets",
        json={
            "customer_id": customer["id"],
            "subject": "Pre-assigned",
            "assignee_id": agent["id"],
        },
    )
    assert res.status_code == 201, res.text

    events = _feed(agent_client)
    assert [e["event_type"] for e in events] == ["ticket.assigned"]
    assert events[0]["payload"]["from"] is None
    assert events[0]["payload"]["to"] == agent["id"]


def test_assignment_is_recorded_and_reaches_the_new_assignee(
    client: TestClient, agent_client: TestClient, ticket: dict, agent: dict
) -> None:
    assert (
        client.post(
            f"/api/tickets/{ticket['id']}/assignment", json={"assignee_id": agent["id"]}
        ).status_code
        == 200
    )

    events = _feed(agent_client)
    assert [e["event_type"] for e in events] == ["ticket.assigned"]
    assert events[0]["payload"]["to"] == agent["id"]
    assert events[0]["payload"]["reference"] == ticket["reference"]


def test_the_actor_is_named_when_the_caller_identifies_itself(
    agent_client: TestClient, other_agent_client: TestClient, ticket: dict,
    agent: dict, other_agent: dict,
) -> None:
    """X-Agent-Id is optional on the assignment route, but supplying it is what
    turns "someone took #145" into "Omar took #145"."""
    other_agent_client.post(
        f"/api/tickets/{ticket['id']}/assignment", json={"assignee_id": agent["id"]}
    )

    assert _feed(agent_client)[0]["agent_id"] == other_agent["id"]


def test_an_unidentified_caller_still_records_the_event(
    client: TestClient, agent_client: TestClient, ticket: dict, agent: dict
) -> None:
    """No header means no actor — not a missing entry."""
    client.post(f"/api/tickets/{ticket['id']}/assignment", json={"assignee_id": agent["id"]})

    assert _feed(agent_client)[0]["agent_id"] is None


def test_status_changes_reply_and_note_all_land_in_the_assignees_feed(
    client: TestClient, agent_client: TestClient, ticket: dict, agent: dict
) -> None:
    client.post(f"/api/tickets/{ticket['id']}/assignment", json={"assignee_id": agent["id"]})
    client.post(f"/api/tickets/{ticket['id']}/status", json={"status": "in_progress"})
    agent_client.post(
        f"/api/tickets/{ticket['id']}/messages",
        json={"channel_slug": "email", "body": "on it"},
    )
    agent_client.post(f"/api/tickets/{ticket['id']}/notes", json={"body": "internal"})

    assert _types(agent_client) == {
        "ticket.assigned",
        "ticket.status_changed",
        "ticket.replied",
        "note.added",
    }


def test_the_feed_is_newest_first(
    client: TestClient, agent_client: TestClient, ticket: dict, agent: dict
) -> None:
    client.post(f"/api/tickets/{ticket['id']}/assignment", json={"assignee_id": agent["id"]})
    client.post(f"/api/tickets/{ticket['id']}/status", json={"status": "in_progress"})

    assert [e["event_type"] for e in _feed(agent_client)] == [
        "ticket.status_changed",
        "ticket.assigned",
    ]


def test_a_failed_reply_is_still_news(
    client: TestClient, agent_client: TestClient, ticket: dict, agent: dict
) -> None:
    """Every driver fails until its adapter story lands, and "Omar tried to
    reply and it bounced" is exactly what a teammate needs to see."""
    client.post(f"/api/tickets/{ticket['id']}/assignment", json={"assignee_id": agent["id"]})
    sent = agent_client.post(
        f"/api/tickets/{ticket['id']}/messages",
        json={"channel_slug": "email", "body": "hello"},
    ).json()
    assert sent["status"] == "failed"

    replied = [e for e in _feed(agent_client) if e["event_type"] == "ticket.replied"]
    assert replied[0]["payload"] == {
        "channel": "email",
        "status": "failed",
        "reference": ticket["reference"],
    }


def test_a_mentioned_agent_sees_the_note_without_being_the_assignee(
    agent_client: TestClient,
    other_agent_client: TestClient,
    ticket: dict,
    agent: dict,
    other_agent: dict,
) -> None:
    # Nobody is assigned, so a mention is the only way in.
    assert ticket["assignee_id"] is None

    other_agent_client.post(
        f"/api/tickets/{ticket['id']}/notes", json={"body": "@dana thoughts?"}
    )

    events = _feed(agent_client)
    assert [e["event_type"] for e in events] == ["note.added"]
    assert events[0]["mentions"] == [agent["id"]]
    assert events[0]["agent_id"] == other_agent["id"]


def test_an_unrelated_agent_sees_nothing(
    client: TestClient,
    agent_client: TestClient,
    third_agent_client: TestClient,
    ticket: dict,
    agent: dict,
) -> None:
    client.post(f"/api/tickets/{ticket['id']}/assignment", json={"assignee_id": agent["id"]})
    client.post(f"/api/tickets/{ticket['id']}/status", json={"status": "in_progress"})
    agent_client.post(f"/api/tickets/{ticket['id']}/notes", json={"body": "mine only"})

    assert len(_feed(agent_client)) == 3
    assert _feed(third_agent_client) == []


def test_reassignment_moves_the_feed_with_the_ticket(
    client: TestClient,
    agent_client: TestClient,
    other_agent_client: TestClient,
    ticket: dict,
    agent: dict,
    other_agent: dict,
) -> None:
    """Visibility follows the *current* assignee: handing a ticket over hands
    over its history too, and the previous holder stops being paged about it."""
    client.post(f"/api/tickets/{ticket['id']}/assignment", json={"assignee_id": agent["id"]})
    assert len(_feed(agent_client)) == 1

    client.post(
        f"/api/tickets/{ticket['id']}/assignment", json={"assignee_id": other_agent["id"]}
    )

    assert len(_feed(other_agent_client)) == 2
    assert _feed(agent_client) == []


def test_the_actor_keeps_seeing_what_they_did(
    client: TestClient,
    agent_client: TestClient,
    other_agent_client: TestClient,
    ticket: dict,
    other_agent: dict,
) -> None:
    """Even after the ticket moves away — you did it, so it stays in your feed."""
    agent_client.post(
        f"/api/tickets/{ticket['id']}/assignment", json={"assignee_id": other_agent["id"]}
    )

    assert [e["event_type"] for e in _feed(agent_client)] == ["ticket.assigned"]


def test_the_feed_respects_its_limit(
    client: TestClient, agent_client: TestClient, ticket: dict, agent: dict
) -> None:
    client.post(f"/api/tickets/{ticket['id']}/assignment", json={"assignee_id": agent["id"]})
    for target in ("in_progress", "waiting_customer", "in_progress"):
        client.post(f"/api/tickets/{ticket['id']}/status", json={"status": target})

    assert len(_feed(agent_client)) == 4
    assert len(agent_client.get("/api/dashboard/activity?limit=2").json()) == 2
    assert agent_client.get("/api/dashboard/activity?limit=101").status_code == 422


def test_deleting_a_ticket_takes_its_events(
    client: TestClient, agent_client: TestClient, ticket: dict, agent: dict
) -> None:
    client.post(f"/api/tickets/{ticket['id']}/assignment", json={"assignee_id": agent["id"]})
    assert len(_feed(agent_client)) == 1

    assert client.delete(f"/api/tickets/{ticket['id']}").status_code == 204
    assert _feed(agent_client) == []
