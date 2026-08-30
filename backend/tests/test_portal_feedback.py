"""Per-ticket feedback: terminal-state gating and upsert-on-resubmit."""

from __future__ import annotations

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.portal import TicketFeedback
from tests.test_portal_tickets import _second_customer_portal_client


def _resolve(client: TestClient, ticket_id: str) -> None:
    for target in ("triaged", "in_progress", "resolved"):
        res = client.post(f"/api/tickets/{ticket_id}/status", json={"status": target})
        assert res.status_code == 200, res.text


def test_feedback_on_non_terminal_ticket_is_409(
    portal_client: TestClient,
) -> None:
    created = portal_client.post("/api/portal/tickets", json={"subject": "Open ticket"})
    ticket_id = created.json()["id"]

    res = portal_client.post(
        f"/api/portal/tickets/{ticket_id}/feedback", json={"rating": 5}
    )
    assert res.status_code == 409, res.text


def test_feedback_succeeds_once_resolved(
    client: TestClient, portal_client: TestClient
) -> None:
    created = portal_client.post("/api/portal/tickets", json={"subject": "Resolve me"})
    ticket_id = created.json()["id"]
    _resolve(client, ticket_id)

    res = portal_client.post(
        f"/api/portal/tickets/{ticket_id}/feedback",
        json={"rating": 4, "comment": "Handled quickly"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["rating"] == 4
    assert body["comment"] == "Handled quickly"


def test_feedback_get_returns_null_before_any_submission(
    client: TestClient, portal_client: TestClient
) -> None:
    created = portal_client.post("/api/portal/tickets", json={"subject": "No feedback yet"})
    ticket_id = created.json()["id"]
    _resolve(client, ticket_id)

    res = portal_client.get(f"/api/portal/tickets/{ticket_id}/feedback")
    assert res.status_code == 200, res.text
    assert res.json() is None


def test_resubmitting_feedback_updates_the_existing_row(
    client: TestClient, db: Session, portal_client: TestClient
) -> None:
    created = portal_client.post("/api/portal/tickets", json={"subject": "Change my mind"})
    ticket_id = created.json()["id"]
    _resolve(client, ticket_id)

    first = portal_client.post(
        f"/api/portal/tickets/{ticket_id}/feedback", json={"rating": 2}
    )
    assert first.status_code == 200, first.text
    second = portal_client.post(
        f"/api/portal/tickets/{ticket_id}/feedback",
        json={"rating": 5, "comment": "Actually, great"},
    )
    assert second.status_code == 200, second.text
    assert first.json()["id"] == second.json()["id"]

    rows = db.scalars(
        select(TicketFeedback).where(TicketFeedback.ticket_id == uuid.UUID(ticket_id))
    ).all()
    assert len(rows) == 1
    assert rows[0].rating == 5
    assert rows[0].comment == "Actually, great"


def test_rating_outside_1_to_5_is_422(
    client: TestClient, portal_client: TestClient
) -> None:
    created = portal_client.post("/api/portal/tickets", json={"subject": "Bad rating"})
    ticket_id = created.json()["id"]
    _resolve(client, ticket_id)

    too_low = portal_client.post(
        f"/api/portal/tickets/{ticket_id}/feedback", json={"rating": 0}
    )
    too_high = portal_client.post(
        f"/api/portal/tickets/{ticket_id}/feedback", json={"rating": 6}
    )
    assert too_low.status_code == 422, too_low.text
    assert too_high.status_code == 422, too_high.text


def test_feedback_on_another_customers_ticket_is_404(
    client: TestClient, app: FastAPI, portal_client: TestClient
) -> None:
    _other_customer, other_portal_client = _second_customer_portal_client(client, app)
    other_ticket = other_portal_client.post(
        "/api/portal/tickets", json={"subject": "Not yours"}
    )
    other_ticket_id = other_ticket.json()["id"]
    _resolve(client, other_ticket_id)

    res = portal_client.post(
        f"/api/portal/tickets/{other_ticket_id}/feedback", json={"rating": 3}
    )
    assert res.status_code == 404, res.text
