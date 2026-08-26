"""Internal ticket notes.

The load-bearing assertion in this file is that posting a note never reaches a
channel driver. Notes live in their own table precisely so that no code path
exists from here to the outside world.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.agent import ActivityEvent
from app.models.channel import ChannelMessage
from tests.conftest import missing_uuid


@pytest.fixture()
def spy_driver(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace the driver lookup with one that records every call.

    Patched on the send path's own module reference, which is the thing a note
    would have to touch to leak.
    """
    calls: list[str] = []

    def fake_get_driver(slug: str):
        calls.append(slug)
        raise AssertionError(f"a channel driver was invoked for {slug!r}")

    monkeypatch.setattr(
        "app.services.channels.service.get_driver", fake_get_driver
    )
    return calls


def test_posting_a_note_never_touches_a_channel_driver(
    agent_client: TestClient, ticket: dict, spy_driver: list[str], db: Session
) -> None:
    res = agent_client.post(
        f"/api/tickets/{ticket['id']}/notes", json={"body": "billing looks wrong"}
    )
    assert res.status_code == 201, res.text
    assert spy_driver == []

    # And nothing landed in the customer-facing thread either.
    assert db.scalar(select(func.count()).select_from(ChannelMessage)) == 0


def test_a_note_is_returned_by_the_notes_endpoint(
    agent_client: TestClient, ticket: dict, agent: dict
) -> None:
    agent_client.post(f"/api/tickets/{ticket['id']}/notes", json={"body": "first"})
    agent_client.post(f"/api/tickets/{ticket['id']}/notes", json={"body": "second"})

    res = agent_client.get(f"/api/tickets/{ticket['id']}/notes")
    assert res.status_code == 200, res.text
    page = res.json()
    assert page["total"] == 2
    # Oldest first: the thread reads as a conversation.
    assert [n["body"] for n in page["items"]] == ["first", "second"]
    assert page["items"][0]["author_agent_id"] == agent["id"]
    assert page["items"][0]["author_display_name"] == agent["display_name"]


def test_notes_do_not_appear_in_the_customer_message_thread(
    agent_client: TestClient, ticket: dict
) -> None:
    """The separation is structural — the two live in different tables."""
    agent_client.post(f"/api/tickets/{ticket['id']}/notes", json={"body": "internal"})

    thread = agent_client.get(f"/api/tickets/{ticket['id']}/messages").json()
    assert thread["total"] == 0


def test_a_note_records_an_activity_event(
    agent_client: TestClient, ticket: dict, agent: dict, db: Session
) -> None:
    agent_client.post(f"/api/tickets/{ticket['id']}/notes", json={"body": "look here"})

    event = db.scalars(
        select(ActivityEvent).where(ActivityEvent.event_type == "note.added")
    ).one()
    assert str(event.agent_id) == agent["id"]
    assert str(event.ticket_id) == ticket["id"]
    assert str(event.customer_id) == ticket["customer_id"]
    assert event.payload["excerpt"] == "look here"


def test_mentions_are_resolved_to_agent_ids(
    agent_client: TestClient, ticket: dict, other_agent: dict, db: Session
) -> None:
    agent_client.post(
        f"/api/tickets/{ticket['id']}/notes", json={"body": "@omar please take a look"}
    )

    event = db.scalars(
        select(ActivityEvent).where(ActivityEvent.event_type == "note.added")
    ).one()
    assert [str(m) for m in event.mentions] == [other_agent["id"]]


def test_a_display_name_also_resolves(
    agent_client: TestClient, ticket: dict, other_agent: dict, db: Session
) -> None:
    """"Omar Night" answers to @omarnight as well as to @omar."""
    agent_client.post(
        f"/api/tickets/{ticket['id']}/notes", json={"body": "cc @OmarNight"}
    )

    event = db.scalars(select(ActivityEvent)).one()
    assert [str(m) for m in event.mentions] == [other_agent["id"]]


def test_an_unknown_handle_is_dropped_not_raised(
    agent_client: TestClient, ticket: dict, db: Session
) -> None:
    """Typing a colleague's name slightly wrong must not block the note."""
    res = agent_client.post(
        f"/api/tickets/{ticket['id']}/notes",
        json={"body": "@nobody @not-an-agent heads up"},
    )
    assert res.status_code == 201, res.text

    event = db.scalars(select(ActivityEvent)).one()
    assert event.mentions == []


def test_a_repeated_mention_counts_once(
    agent_client: TestClient, ticket: dict, other_agent: dict, db: Session
) -> None:
    agent_client.post(
        f"/api/tickets/{ticket['id']}/notes", json={"body": "@omar @omar @omar"}
    )

    event = db.scalars(select(ActivityEvent)).one()
    assert [str(m) for m in event.mentions] == [other_agent["id"]]


def test_notes_on_a_missing_ticket_are_not_found(agent_client: TestClient) -> None:
    assert agent_client.get(f"/api/tickets/{missing_uuid()}/notes").status_code == 404
    assert (
        agent_client.post(
            f"/api/tickets/{missing_uuid()}/notes", json={"body": "x"}
        ).status_code
        == 404
    )


def test_an_empty_note_is_rejected(agent_client: TestClient, ticket: dict) -> None:
    assert (
        agent_client.post(f"/api/tickets/{ticket['id']}/notes", json={"body": ""}).status_code
        == 422
    )


def test_deleting_a_ticket_takes_its_notes(
    agent_client: TestClient, client: TestClient, ticket: dict, db: Session
) -> None:
    agent_client.post(f"/api/tickets/{ticket['id']}/notes", json={"body": "gone soon"})
    assert client.delete(f"/api/tickets/{ticket['id']}").status_code == 204

    assert agent_client.get(f"/api/tickets/{ticket['id']}/notes").status_code == 404
