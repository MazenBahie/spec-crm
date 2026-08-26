"""Ticket profile CRUD, reference/priority resolution, and hard delete."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import missing_uuid


def test_create_returns_201_with_reference_and_defaults(
    client: TestClient, customer: dict
) -> None:
    res = client.post(
        "/api/tickets",
        json={"customer_id": customer["id"], "subject": "Cannot log in"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["reference"].startswith("TCK-")
    assert len(body["reference"]) == len("TCK-") + 8
    assert body["subject"] == "Cannot log in"
    assert body["description"] == ""
    assert body["status"] == "open"
    assert body["priority"] == "normal"
    assert body["escalation_level"] == 0
    assert body["category_id"] is None
    assert body["assignee_id"] is None
    assert body["is_overdue"] is False
    assert body["created_at"] and body["updated_at"]


def test_create_inherits_category_default_priority(
    client: TestClient, customer: dict, ticket_category: dict
) -> None:
    assert ticket_category["default_priority"] == "high"
    res = client.post(
        "/api/tickets",
        json={
            "customer_id": customer["id"],
            "subject": "Billing question",
            "category_id": ticket_category["id"],
        },
    )
    assert res.status_code == 201, res.text
    assert res.json()["priority"] == "high"


def test_explicit_priority_overrides_category_default(
    client: TestClient, customer: dict, ticket_category: dict
) -> None:
    res = client.post(
        "/api/tickets",
        json={
            "customer_id": customer["id"],
            "subject": "Billing question",
            "category_id": ticket_category["id"],
            "priority": "low",
        },
    )
    assert res.status_code == 201, res.text
    assert res.json()["priority"] == "low"


def test_create_with_assignee_returns_it(
    client: TestClient, customer: dict, agent: dict
) -> None:
    res = client.post(
        "/api/tickets",
        json={
            "customer_id": customer["id"],
            "subject": "Needs routing",
            "assignee_id": agent["id"],
        },
    )
    assert res.status_code == 201, res.text
    assert res.json()["assignee_id"] == agent["id"]


def test_create_with_inactive_assignee_returns_409(
    client: TestClient, customer: dict, inactive_agent: dict
) -> None:
    res = client.post(
        "/api/tickets",
        json={
            "customer_id": customer["id"],
            "subject": "x",
            "assignee_id": inactive_agent["id"],
        },
    )
    assert res.status_code == 409


def test_create_with_inactive_category_returns_409(
    client: TestClient, customer: dict, ticket_category: dict
) -> None:
    client.patch(f"/api/ticket-categories/{ticket_category['id']}", json={"is_active": False})
    res = client.post(
        "/api/tickets",
        json={
            "customer_id": customer["id"],
            "subject": "x",
            "category_id": ticket_category["id"],
        },
    )
    assert res.status_code == 409


def test_create_for_archived_customer_returns_409(
    client: TestClient, customer: dict
) -> None:
    client.post(f"/api/customers/{customer['id']}/archive")
    res = client.post(
        "/api/tickets", json={"customer_id": customer["id"], "subject": "nope"}
    )
    assert res.status_code == 409
    assert res.json()["detail"] == "customer is archived"


def test_create_for_unknown_customer_returns_404(client: TestClient) -> None:
    res = client.post(
        "/api/tickets", json={"customer_id": str(missing_uuid()), "subject": "x"}
    )
    assert res.status_code == 404


def test_blank_subject_rejected(client: TestClient, customer: dict) -> None:
    res = client.post(
        "/api/tickets", json={"customer_id": customer["id"], "subject": ""}
    )
    assert res.status_code == 422


def test_get_detail_embeds_customer_category_and_assignee(
    client: TestClient, customer: dict, ticket_category: dict, agent: dict
) -> None:
    created = client.post(
        "/api/tickets",
        json={
            "customer_id": customer["id"],
            "subject": "Full detail",
            "category_id": ticket_category["id"],
            "assignee_id": agent["id"],
        },
    ).json()

    body = client.get(f"/api/tickets/{created['id']}").json()
    assert body["customer"]["id"] == customer["id"]
    assert body["category"]["id"] == ticket_category["id"]
    assert body["assignee"]["id"] == agent["id"]


def test_get_detail_with_no_category_or_assignee_are_null(
    client: TestClient, ticket: dict
) -> None:
    body = client.get(f"/api/tickets/{ticket['id']}").json()
    assert body["category"] is None
    assert body["assignee"] is None


def test_patch_updates_only_supplied_fields(client: TestClient, ticket: dict) -> None:
    res = client.patch(f"/api/tickets/{ticket['id']}", json={"subject": "Renamed"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["subject"] == "Renamed"
    assert body["description"] == ticket["description"]


def test_patch_cannot_change_status_or_assignee(client: TestClient, ticket: dict) -> None:
    """status/assignee_id are absent from TicketUpdate; extras are ignored, not errors."""
    res = client.patch(
        f"/api/tickets/{ticket['id']}",
        json={"subject": "still editable", "status": "closed"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "open"


def test_delete_removes_ticket(client: TestClient, ticket: dict) -> None:
    assert client.delete(f"/api/tickets/{ticket['id']}").status_code == 204
    assert client.get(f"/api/tickets/{ticket['id']}").status_code == 404


def test_unknown_id_returns_404_not_500(client: TestClient) -> None:
    unknown = missing_uuid()
    assert client.get(f"/api/tickets/{unknown}").status_code == 404
    assert client.patch(f"/api/tickets/{unknown}", json={"subject": "x"}).status_code == 404
    assert client.delete(f"/api/tickets/{unknown}").status_code == 404


def test_malformed_uuid_returns_422(client: TestClient) -> None:
    assert client.get("/api/tickets/not-a-uuid").status_code == 422


def test_unicode_subject_and_description_round_trip(
    client: TestClient, customer: dict
) -> None:
    subject = "Ünicode — 客戶 subject 🙂"
    description = "Body with é à ü and 客戶 — em-dash.\nSecond line."
    created = client.post(
        "/api/tickets",
        json={"customer_id": customer["id"], "subject": subject, "description": description},
    ).json()

    body = client.get(f"/api/tickets/{created['id']}").json()
    assert body["subject"] == subject
    assert body["description"] == description
