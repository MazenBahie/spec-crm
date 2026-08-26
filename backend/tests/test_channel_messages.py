"""Outbound messages: persistence, stub-driver failure, thread order, cascade."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.channel import ChannelMessage
from tests.conftest import missing_uuid


def send(client: TestClient, ticket_id: str, body: str, slug: str = "email"):
    return client.post(
        f"/api/tickets/{ticket_id}/messages", json={"channel_slug": slug, "body": body}
    )


def test_a_new_thread_is_empty(client: TestClient, ticket: dict) -> None:
    body = client.get(f"/api/tickets/{ticket['id']}/messages").json()
    assert body == {"items": [], "total": 0}


def test_send_persists_the_row_and_records_the_stub_failure(
    client: TestClient, ticket: dict, customer: dict
) -> None:
    res = send(client, ticket["id"], "Have you tried the reset link?")
    assert res.status_code == 201, res.text
    message = res.json()

    assert message["direction"] == "outbound"
    assert message["channel_slug"] == "email"
    assert message["ticket_id"] == ticket["id"]
    # Denormalised off the ticket so a customer's whole history is one scan.
    assert message["customer_id"] == customer["id"]
    assert message["body"] == "Have you tried the reset link?"
    # The expected state until story 21 replaces the email stub.
    assert message["status"] == "failed"
    assert "not implemented" in message["error_reason"]
    assert "email" in message["error_reason"]
    assert message["provider_message_id"] is None


def test_a_failed_send_is_still_readable_in_the_thread(
    client: TestClient, ticket: dict
) -> None:
    send(client, ticket["id"], "first attempt")
    body = client.get(f"/api/tickets/{ticket['id']}/messages").json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "failed"


def test_every_stubbed_channel_fails_the_same_way(client: TestClient, ticket: dict) -> None:
    for slug in ("email", "whatsapp", "live_chat", "sms", "web_form"):
        message = send(client, ticket["id"], f"hello over {slug}", slug=slug).json()
        assert message["status"] == "failed", slug
        assert slug in message["error_reason"], slug


def test_thread_is_ordered_oldest_first(client: TestClient, ticket: dict) -> None:
    for text in ("one", "two", "three"):
        assert send(client, ticket["id"], text).status_code == 201

    items = client.get(f"/api/tickets/{ticket['id']}/messages").json()["items"]
    assert [m["body"] for m in items] == ["one", "two", "three"]
    stamps = [m["created_at"] for m in items]
    assert stamps == sorted(stamps)


def test_thread_paginates(client: TestClient, ticket: dict) -> None:
    for text in ("one", "two", "three"):
        send(client, ticket["id"], text)

    page = client.get(f"/api/tickets/{ticket['id']}/messages?limit=2").json()
    assert page["total"] == 3
    assert [m["body"] for m in page["items"]] == ["one", "two"]

    page = client.get(f"/api/tickets/{ticket['id']}/messages?limit=2&offset=2").json()
    assert [m["body"] for m in page["items"]] == ["three"]


def test_unknown_channel_slug_is_rejected(client: TestClient, ticket: dict) -> None:
    assert send(client, ticket["id"], "hi", slug="telegram").status_code == 422
    assert send(client, ticket["id"], "hi", slug="").status_code == 422


def test_empty_body_is_rejected(client: TestClient, ticket: dict) -> None:
    assert send(client, ticket["id"], "").status_code == 422
    res = client.post(f"/api/tickets/{ticket['id']}/messages", json={"channel_slug": "email"})
    assert res.status_code == 422


def test_missing_ticket_is_404_on_both_verbs(client: TestClient) -> None:
    ghost = missing_uuid()
    assert send(client, str(ghost), "hi").status_code == 404
    assert client.get(f"/api/tickets/{ghost}/messages").status_code == 404


def test_disabled_channel_refuses_outbound(client: TestClient, ticket: dict) -> None:
    client.patch("/api/channels/sms", json={"is_enabled": False})
    res = send(client, ticket["id"], "hi", slug="sms")
    assert res.status_code == 409
    assert "disabled" in res.json()["detail"]
    # Nothing was written for the refused attempt.
    assert client.get(f"/api/tickets/{ticket['id']}/messages").json()["total"] == 0


def test_unicode_body_round_trips_unchanged(client: TestClient, ticket: dict) -> None:
    body = "شكراً جزيلاً — refund sent 🎉 ¥1,200"
    assert send(client, ticket["id"], body).json()["body"] == body
    items = client.get(f"/api/tickets/{ticket['id']}/messages").json()["items"]
    assert items[0]["body"] == body


def test_concurrent_sends_each_get_their_own_row(client: TestClient, ticket: dict) -> None:
    ids = {send(client, ticket["id"], "same text").json()["id"] for _ in range(3)}
    assert len(ids) == 3
    assert client.get(f"/api/tickets/{ticket['id']}/messages").json()["total"] == 3


def test_deleting_the_ticket_removes_its_messages(
    client: TestClient, db: Session, ticket: dict
) -> None:
    send(client, ticket["id"], "will be gone")
    assert client.delete(f"/api/tickets/{ticket['id']}").status_code == 204
    assert db.scalar(select(func.count()).select_from(ChannelMessage)) == 0


def test_messages_are_scoped_to_their_own_ticket(
    client: TestClient, customer: dict, ticket: dict
) -> None:
    other = client.post(
        "/api/tickets", json={"customer_id": customer["id"], "subject": "unrelated"}
    ).json()
    send(client, ticket["id"], "mine")

    assert client.get(f"/api/tickets/{other['id']}/messages").json()["total"] == 0
    assert client.get(f"/api/tickets/{ticket['id']}/messages").json()["total"] == 1
