"""Portal ticket creation, listing, detail scoping, and the event-type filter."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.conftest import missing_uuid


def _second_customer_portal_client(
    client: TestClient, app: FastAPI
) -> tuple[dict, TestClient]:
    """A second customer, with its own email contact and portal login."""
    customer_res = client.post(
        "/api/customers", json={"display_name": "Globex Corp", "company": "Globex"}
    )
    assert customer_res.status_code == 201, customer_res.text
    customer = customer_res.json()

    contact_res = client.post(
        f"/api/customers/{customer['id']}/contacts",
        json={"kind": "email", "value": "globex-owner@example.com", "is_primary": True},
    )
    assert contact_res.status_code == 201, contact_res.text

    signup_res = client.post(
        "/api/portal/auth/signup",
        json={
            "email": "globex-owner@example.com",
            "password": "hunter2pass",
            "display_name": "Globex Owner",
        },
    )
    assert signup_res.status_code == 201, signup_res.text
    token = signup_res.json()["token"]
    portal_client = TestClient(app, headers={"Authorization": f"Bearer {token}"})
    return customer, portal_client


def test_create_ticket_ignores_client_supplied_customer_assignee_and_priority(
    portal_client: TestClient, portal_user: dict, agent: dict
) -> None:
    res = portal_client.post(
        "/api/portal/tickets",
        json={
            "subject": "Cannot log in",
            "description": "Password reset email never arrives.",
            "customer_id": str(missing_uuid()),
            "assignee_id": agent["id"],
            "priority": "urgent",
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["customer_id"] == portal_user["customer_id"]
    assert body["assignee_id"] is None
    assert body["priority"] == "normal"


def test_list_returns_only_the_callers_own_tickets(
    client: TestClient, app: FastAPI, portal_client: TestClient, customer: dict
) -> None:
    own = portal_client.post(
        "/api/portal/tickets", json={"subject": "My own ticket"}
    )
    assert own.status_code == 201, own.text

    other_customer, other_portal_client = _second_customer_portal_client(client, app)
    other = other_portal_client.post(
        "/api/portal/tickets", json={"subject": "Someone else's ticket"}
    )
    assert other.status_code == 201, other.text

    res = portal_client.get("/api/portal/tickets")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["subject"] == "My own ticket"


def test_get_another_customers_ticket_is_404_not_403(
    client: TestClient, app: FastAPI, portal_client: TestClient
) -> None:
    other_customer, other_portal_client = _second_customer_portal_client(client, app)
    other_ticket = other_portal_client.post(
        "/api/portal/tickets", json={"subject": "Not yours"}
    )
    assert other_ticket.status_code == 201, other_ticket.text
    other_ticket_id = other_ticket.json()["id"]

    cross_customer = portal_client.get(f"/api/portal/tickets/{other_ticket_id}")
    genuinely_missing = portal_client.get(f"/api/portal/tickets/{missing_uuid()}")

    assert cross_customer.status_code == 404, cross_customer.text
    assert genuinely_missing.status_code == 404, genuinely_missing.text
    # Same message template for both -- a cross-customer ticket id must not
    # read any differently from one that never existed.
    assert cross_customer.json()["detail"].startswith("ticket ")
    assert cross_customer.json()["detail"].endswith(" not found")
    assert genuinely_missing.json()["detail"].startswith("ticket ")
    assert genuinely_missing.json()["detail"].endswith(" not found")


def test_events_show_only_created_and_status_changed(
    client: TestClient, portal_client: TestClient, agent: dict
) -> None:
    created = portal_client.post("/api/portal/tickets", json={"subject": "Timeline test"})
    assert created.status_code == 201, created.text
    ticket_id = created.json()["id"]

    assign = client.post(
        f"/api/tickets/{ticket_id}/assignment", json={"assignee_id": agent["id"]}
    )
    assert assign.status_code == 200, assign.text
    status_change = client.post(
        f"/api/tickets/{ticket_id}/status", json={"status": "triaged"}
    )
    assert status_change.status_code == 200, status_change.text
    escalate = client.post(f"/api/tickets/{ticket_id}/escalate", json={})
    assert escalate.status_code == 200, escalate.text

    res = portal_client.get(f"/api/portal/tickets/{ticket_id}/events")
    assert res.status_code == 200, res.text
    event_types = {e["event_type"] for e in res.json()}
    assert event_types == {"created", "status_changed"}
    assert len(res.json()) == 2


def test_unauthenticated_requests_to_portal_tickets_are_401(client: TestClient) -> None:
    assert client.get("/api/portal/tickets").status_code == 401
    assert client.post("/api/portal/tickets", json={"subject": "x"}).status_code == 401
    assert client.get(f"/api/portal/tickets/{missing_uuid()}").status_code == 401
