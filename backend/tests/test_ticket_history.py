"""Ticket event history: one row per mutation, ordering, immutability, cascade."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ticket import TicketEvent


def test_created_event_exists_immediately(client: TestClient, ticket: dict) -> None:
    body = client.get(f"/api/tickets/{ticket['id']}/events").json()
    assert body["total"] == 1
    assert body["items"][0]["event_type"] == "created"


def test_created_ticket_with_assignee_also_writes_assigned_event(
    client: TestClient, customer: dict, agent: dict
) -> None:
    created = client.post(
        "/api/tickets",
        json={
            "customer_id": customer["id"],
            "subject": "born assigned",
            "assignee_id": agent["id"],
        },
    ).json()

    events = client.get(f"/api/tickets/{created['id']}/events").json()["items"]
    types = {e["event_type"] for e in events}
    assert types == {"created", "assigned"}


def test_each_mutation_appends_exactly_one_correctly_typed_event(
    client: TestClient, ticket: dict, ticket_category: dict, agent: dict
) -> None:
    client.patch(f"/api/tickets/{ticket['id']}", json={"priority": "urgent"})
    client.patch(f"/api/tickets/{ticket['id']}", json={"category_id": ticket_category["id"]})
    client.post(f"/api/tickets/{ticket['id']}/status", json={"status": "triaged"})
    client.post(f"/api/tickets/{ticket['id']}/assignment", json={"assignee_id": agent["id"]})
    client.post(f"/api/tickets/{ticket['id']}/escalate", json={"raise_priority": False})

    events = client.get(f"/api/tickets/{ticket['id']}/events").json()["items"]
    counts: dict[str, int] = {}
    for e in events:
        counts[e["event_type"]] = counts.get(e["event_type"], 0) + 1

    assert counts == {
        "created": 1,
        "priority_changed": 1,
        "category_changed": 1,
        "status_changed": 1,
        "assigned": 1,
        "escalated": 1,
    }

    category_event = next(e for e in events if e["event_type"] == "category_changed")
    assert category_event["old_value"] is None
    assert category_event["new_value"] == ticket_category["id"]


def test_patch_with_unchanged_value_emits_no_event(client: TestClient, ticket: dict) -> None:
    before = client.get(f"/api/tickets/{ticket['id']}/events").json()["total"]
    res = client.patch(f"/api/tickets/{ticket['id']}", json={"priority": ticket["priority"]})
    assert res.status_code == 200, res.text
    after = client.get(f"/api/tickets/{ticket['id']}/events").json()["total"]
    assert after == before


def test_comment_adds_a_commented_event(client: TestClient, ticket: dict) -> None:
    res = client.post(
        f"/api/tickets/{ticket['id']}/events",
        json={"comment": "Called the customer back.", "actor": "dana"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["event_type"] == "commented"
    assert body["comment"] == "Called the customer back."
    assert body["actor"] == "dana"

    listed = client.get(f"/api/tickets/{ticket['id']}/events").json()["items"]
    assert any(e["event_type"] == "commented" for e in listed)


def test_blank_comment_rejected(client: TestClient, ticket: dict) -> None:
    res = client.post(f"/api/tickets/{ticket['id']}/events", json={"comment": ""})
    assert res.status_code == 422


def test_events_list_is_newest_first(client: TestClient, ticket: dict) -> None:
    client.post(f"/api/tickets/{ticket['id']}/status", json={"status": "triaged"})
    client.post(f"/api/tickets/{ticket['id']}/status", json={"status": "in_progress"})

    items = client.get(f"/api/tickets/{ticket['id']}/events").json()["items"]
    timestamps = [e["created_at"] for e in items]
    assert timestamps == sorted(timestamps, reverse=True)
    assert items[0]["new_value"] == "in_progress"


def test_events_paginate(client: TestClient, ticket: dict) -> None:
    for target in ("triaged", "in_progress", "waiting_customer", "in_progress"):
        client.post(f"/api/tickets/{ticket['id']}/status", json={"status": target})

    page = client.get(
        f"/api/tickets/{ticket['id']}/events", params={"limit": 2, "offset": 0}
    ).json()
    assert page["total"] == 5  # created + 4 status changes
    assert len(page["items"]) == 2


def test_no_route_edits_or_deletes_an_event(client: TestClient, ticket: dict) -> None:
    events_url = f"/api/tickets/{ticket['id']}/events"
    assert client.patch(events_url, json={}).status_code == 405
    assert client.delete(events_url).status_code == 405


def test_deleting_ticket_removes_its_events(
    client: TestClient, ticket: dict, db: Session
) -> None:
    client.post(f"/api/tickets/{ticket['id']}/status", json={"status": "triaged"})
    assert client.delete(f"/api/tickets/{ticket['id']}").status_code == 204

    db.expire_all()
    remaining = db.scalar(
        select(func.count())
        .select_from(TicketEvent)
        .where(TicketEvent.ticket_id == uuid.UUID(ticket["id"]))
    )
    assert remaining == 0


def test_deleting_customer_cascades_tickets_and_events(
    client: TestClient, ticket: dict, db: Session
) -> None:
    client.post(f"/api/tickets/{ticket['id']}/status", json={"status": "triaged"})

    assert client.delete(f"/api/customers/{ticket['customer_id']}").status_code == 204

    assert client.get(f"/api/tickets/{ticket['id']}").status_code == 404
    db.expire_all()
    remaining = db.scalar(
        select(func.count())
        .select_from(TicketEvent)
        .where(TicketEvent.ticket_id == uuid.UUID(ticket["id"]))
    )
    assert remaining == 0
