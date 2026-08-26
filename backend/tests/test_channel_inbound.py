"""Inbound webhook ingestion: arbitrary provider payloads onto a ticket thread."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import missing_uuid


def test_inbound_lands_as_a_received_message(
    client: TestClient, ticket: dict, customer: dict
) -> None:
    res = client.post(
        "/api/channels/email/inbound",
        json={"ticket_id": ticket["id"], "body": "Still cannot log in."},
    )
    assert res.status_code == 201, res.text
    message = res.json()

    assert message["direction"] == "inbound"
    # Terminal on arrival — an inbound message is never queued or sent.
    assert message["status"] == "received"
    assert message["channel_slug"] == "email"
    assert message["body"] == "Still cannot log in."
    assert message["customer_id"] == customer["id"]
    assert message["error_reason"] is None


def test_inbound_and_outbound_share_one_thread(client: TestClient, ticket: dict) -> None:
    client.post(
        "/api/channels/email/inbound",
        json={"ticket_id": ticket["id"], "body": "customer asks"},
    )
    client.post(
        f"/api/tickets/{ticket['id']}/messages",
        json={"channel_slug": "email", "body": "agent answers"},
    )

    items = client.get(f"/api/tickets/{ticket['id']}/messages").json()["items"]
    assert [(m["direction"], m["body"]) for m in items] == [
        ("inbound", "customer asks"),
        ("outbound", "agent answers"),
    ]


def test_provider_message_id_is_captured_when_supplied(
    client: TestClient, ticket: dict
) -> None:
    message = client.post(
        "/api/channels/whatsapp/inbound",
        json={
            "ticket_id": ticket["id"],
            "body": "any update?",
            "provider_message_id": "wamid.HBgL123",
        },
    ).json()
    assert message["provider_message_id"] == "wamid.HBgL123"


def test_unrecognised_provider_fields_are_tolerated(
    client: TestClient, ticket: dict
) -> None:
    """The endpoint takes provider-shaped JSON; the driver picks what it needs."""
    res = client.post(
        "/api/channels/sms/inbound",
        json={
            "ticket_id": ticket["id"],
            "body": "reply via sms",
            "SmsStatus": "received",
            "NumSegments": 1,
            "nested": {"anything": ["at", "all"]},
        },
    )
    assert res.status_code == 201, res.text
    assert res.json()["body"] == "reply via sms"


def test_inbound_works_on_every_channel(client: TestClient, ticket: dict) -> None:
    for slug in ("email", "whatsapp", "live_chat", "sms", "web_form"):
        res = client.post(
            f"/api/channels/{slug}/inbound",
            json={"ticket_id": ticket["id"], "body": f"hello from {slug}"},
        )
        assert res.status_code == 201, (slug, res.text)
        assert res.json()["channel_slug"] == slug


def test_inbound_is_accepted_on_a_disabled_channel(
    client: TestClient, ticket: dict
) -> None:
    """Disabling stops agents replying; it must not drop a customer's message."""
    client.patch("/api/channels/live_chat", json={"is_enabled": False})
    res = client.post(
        "/api/channels/live_chat/inbound",
        json={"ticket_id": ticket["id"], "body": "already in flight"},
    )
    assert res.status_code == 201, res.text


def test_missing_ticket_id_is_rejected(client: TestClient) -> None:
    res = client.post("/api/channels/email/inbound", json={"body": "orphan"})
    assert res.status_code == 422


def test_unknown_ticket_id_is_404(client: TestClient) -> None:
    res = client.post(
        "/api/channels/email/inbound",
        json={"ticket_id": str(missing_uuid()), "body": "nowhere to go"},
    )
    assert res.status_code == 404


def test_payload_with_no_usable_body_is_rejected(client: TestClient, ticket: dict) -> None:
    for payload in ({"ticket_id": ticket["id"]}, {"ticket_id": ticket["id"], "body": "   "}):
        res = client.post("/api/channels/email/inbound", json=payload)
        assert res.status_code == 409, res.text
        assert "body" in res.json()["detail"]

    assert client.get(f"/api/tickets/{ticket['id']}/messages").json()["total"] == 0


def test_unknown_channel_slug_is_rejected(client: TestClient, ticket: dict) -> None:
    res = client.post(
        "/api/channels/telegram/inbound",
        json={"ticket_id": ticket["id"], "body": "wrong channel"},
    )
    assert res.status_code == 422


def test_unicode_inbound_round_trips_unchanged(client: TestClient, ticket: dict) -> None:
    body = "مرحبا — the reset link 404s 😞"
    message = client.post(
        "/api/channels/whatsapp/inbound",
        json={"ticket_id": ticket["id"], "body": body},
    ).json()
    assert message["body"] == body
