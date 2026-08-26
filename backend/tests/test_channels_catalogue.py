"""The channel catalogue: five fixed rows, enable/disable, no create or delete."""

from __future__ import annotations

from fastapi.testclient import TestClient

EXPECTED_SLUGS = {"email", "whatsapp", "live_chat", "sms", "web_form"}


def test_catalogue_holds_exactly_the_five_seeded_channels(client: TestClient) -> None:
    body = client.get("/api/channels").json()
    assert {c["slug"] for c in body} == EXPECTED_SLUGS
    assert len(body) == 5
    assert all(c["is_enabled"] for c in body)
    assert all(c["config"] is None for c in body)


def test_catalogue_ids_are_stable_across_databases(client: TestClient) -> None:
    """Seed ids are hard-coded so a migrated DB and a created one agree."""
    by_slug = {c["slug"]: c["id"] for c in client.get("/api/channels").json()}
    assert by_slug["email"] == "c8a1c0de-0000-4000-8000-000000000001"
    assert by_slug["web_form"] == "c8a1c0de-0000-4000-8000-000000000005"


def test_display_names_are_human_readable(client: TestClient) -> None:
    by_slug = {c["slug"]: c["display_name"] for c in client.get("/api/channels").json()}
    assert by_slug == {
        "email": "Email",
        "whatsapp": "WhatsApp",
        "live_chat": "Live chat",
        "sms": "SMS",
        "web_form": "Web forms",
    }


def test_disabling_a_channel_removes_it_from_the_enabled_list(client: TestClient) -> None:
    patched = client.patch("/api/channels/sms", json={"is_enabled": False})
    assert patched.status_code == 200, patched.text
    assert patched.json()["is_enabled"] is False

    enabled = {c["slug"] for c in client.get("/api/channels?enabled_only=true").json()}
    assert enabled == EXPECTED_SLUGS - {"sms"}
    # Still in the full catalogue — disabling is not deleting.
    assert len(client.get("/api/channels").json()) == 5


def test_config_can_be_written_and_read_back(client: TestClient) -> None:
    res = client.patch(
        "/api/channels/email", json={"config": {"host": "smtp.test", "port": 587}}
    )
    assert res.status_code == 200, res.text
    assert res.json()["config"] == {"host": "smtp.test", "port": 587}


def test_patch_leaves_unmentioned_fields_alone(client: TestClient) -> None:
    client.patch("/api/channels/email", json={"config": {"host": "smtp.test"}})
    res = client.patch("/api/channels/email", json={"is_enabled": False})
    assert res.json()["config"] == {"host": "smtp.test"}


def test_unknown_slug_is_rejected_before_any_lookup(client: TestClient) -> None:
    assert client.patch("/api/channels/telegram", json={"is_enabled": False}).status_code == 422
    assert client.get("/api/channels/email").status_code == 405


def test_channels_cannot_be_created_or_deleted(client: TestClient) -> None:
    assert client.post("/api/channels", json={"slug": "telegram"}).status_code == 405
    assert client.delete("/api/channels/email").status_code == 405
