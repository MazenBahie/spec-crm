"""Quick replies: visibility, the scope/owner invariant, and mutation rights."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.agent import QuickReply
from tests.conftest import missing_uuid


def _create(agent_client: TestClient, title: str, **extra) -> dict:
    payload = {"title": title, "body": "Hi {{customer.first_name}}!", **extra}
    res = agent_client.post("/api/quick-replies", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def test_personal_reply_is_owned_by_its_creator(
    agent_client: TestClient, agent: dict
) -> None:
    reply = _create(agent_client, "Greeting")

    assert reply["scope"] == "personal"
    assert reply["owner_agent_id"] == agent["id"]


def test_team_reply_has_no_owner(agent_client: TestClient) -> None:
    reply = _create(agent_client, "Shared", scope="team")

    assert reply["scope"] == "team"
    assert reply["owner_agent_id"] is None


def test_the_template_is_stored_unrendered(agent_client: TestClient) -> None:
    """Tokens are rendered at insert time by the picker, never persisted —
    so editing a reply changes every future insertion."""
    reply = _create(agent_client, "Greeting", body="Hi {{customer.first_name}}, re {{ticket.id}}")
    assert reply["body"] == "Hi {{customer.first_name}}, re {{ticket.id}}"


def test_list_shows_team_replies_and_only_my_own_personal_ones(
    agent_client: TestClient, other_agent_client: TestClient
) -> None:
    _create(agent_client, "Mine")
    _create(other_agent_client, "Theirs")
    _create(agent_client, "Shared", scope="team")

    assert sorted(r["title"] for r in agent_client.get("/api/quick-replies").json()) == [
        "Mine",
        "Shared",
    ]
    assert sorted(
        r["title"] for r in other_agent_client.get("/api/quick-replies").json()
    ) == ["Shared", "Theirs"]


def test_list_puts_the_team_library_first(agent_client: TestClient) -> None:
    _create(agent_client, "Apology")
    _create(agent_client, "Zebra", scope="team")

    assert [r["title"] for r in agent_client.get("/api/quick-replies").json()] == [
        "Zebra",
        "Apology",
    ]


def test_promoting_to_team_clears_the_owner(agent_client: TestClient) -> None:
    reply = _create(agent_client, "Greeting")

    res = agent_client.patch(f"/api/quick-replies/{reply['id']}", json={"scope": "team"})
    assert res.status_code == 200, res.text
    assert res.json()["scope"] == "team"
    assert res.json()["owner_agent_id"] is None


def test_demoting_to_personal_sets_the_caller_as_owner(
    agent_client: TestClient, other_agent_client: TestClient, other_agent: dict
) -> None:
    reply = _create(agent_client, "Shared", scope="team")

    res = other_agent_client.patch(
        f"/api/quick-replies/{reply['id']}", json={"scope": "personal"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["owner_agent_id"] == other_agent["id"]

    # And it has left the first agent's library with its new owner.
    assert agent_client.get("/api/quick-replies").json() == []


def test_editing_body_and_shortcut(agent_client: TestClient) -> None:
    reply = _create(agent_client, "Greeting", shortcut="hi")

    res = agent_client.patch(
        f"/api/quick-replies/{reply['id']}", json={"body": "Hello!", "shortcut": "hey"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["body"] == "Hello!"
    assert res.json()["shortcut"] == "hey"
    # An untouched scope keeps its owner.
    assert res.json()["owner_agent_id"] == reply["owner_agent_id"]


def test_only_the_owner_may_mutate_a_personal_reply(
    agent_client: TestClient, other_agent_client: TestClient
) -> None:
    reply = _create(agent_client, "Mine")

    assert (
        other_agent_client.patch(
            f"/api/quick-replies/{reply['id']}", json={"title": "Hijacked"}
        ).status_code
        == 403
    )
    assert other_agent_client.delete(f"/api/quick-replies/{reply['id']}").status_code == 403
    assert agent_client.get("/api/quick-replies").json()[0]["title"] == "Mine"


def test_any_agent_may_curate_the_team_library(
    agent_client: TestClient, other_agent_client: TestClient
) -> None:
    """Deliberate for now — there are no roles yet to say who owns the shared
    library. Hardening this is a follow-up."""
    reply = _create(agent_client, "Shared", scope="team")

    res = other_agent_client.patch(
        f"/api/quick-replies/{reply['id']}", json={"title": "Shared, tidied"}
    )
    assert res.status_code == 200, res.text
    assert other_agent_client.delete(f"/api/quick-replies/{reply['id']}").status_code == 204


def test_delete_removes_it(agent_client: TestClient) -> None:
    reply = _create(agent_client, "Temporary")
    assert agent_client.delete(f"/api/quick-replies/{reply['id']}").status_code == 204
    assert agent_client.get("/api/quick-replies").json() == []


def test_unknown_reply_is_not_found(agent_client: TestClient) -> None:
    assert (
        agent_client.patch(
            f"/api/quick-replies/{missing_uuid()}", json={"title": "x"}
        ).status_code
        == 404
    )


def test_title_and_body_are_validated(agent_client: TestClient) -> None:
    assert (
        agent_client.post("/api/quick-replies", json={"title": "", "body": "x"}).status_code
        == 422
    )
    assert (
        agent_client.post("/api/quick-replies", json={"title": "x", "body": ""}).status_code
        == 422
    )
    assert (
        agent_client.post(
            "/api/quick-replies", json={"title": "x", "body": "y", "shortcut": "s" * 41}
        ).status_code
        == 422
    )
    assert (
        agent_client.post(
            "/api/quick-replies", json={"title": "x", "body": "y", "scope": "everyone"}
        ).status_code
        == 422
    )


def test_the_client_cannot_nominate_an_owner(
    agent_client: TestClient, agent: dict, other_agent: dict
) -> None:
    """`owner_agent_id` is not an input field, so the one way to violate the
    invariant from outside is closed. An attempt is ignored, not honoured."""
    res = agent_client.post(
        "/api/quick-replies",
        json={
            "title": "Sneaky",
            "body": "x",
            "scope": "team",
            "owner_agent_id": other_agent["id"],
        },
    )
    assert res.status_code == 201, res.text
    assert res.json()["owner_agent_id"] is None


@pytest.mark.parametrize(
    ("scope", "with_owner"),
    [("personal", False), ("team", True)],
    ids=["personal-without-owner", "team-with-owner"],
)
def test_the_database_refuses_a_broken_scope_invariant(
    db: Session, agent_client: TestClient, agent: dict, scope: str, with_owner: bool
) -> None:
    """Defence in depth: even a write that bypasses the service is rejected.

    Without this, a personal reply with no owner would read as team-scoped and
    be served to every agent.
    """
    db.add(
        QuickReply(
            scope=scope,
            owner_agent_id=uuid.UUID(agent["id"]) if with_owner else None,
            title="Broken",
            body="x",
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
