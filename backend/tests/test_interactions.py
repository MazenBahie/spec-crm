"""Interaction history: ordering, CRUD, and the archived-customer guard."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.customer import Interaction
from tests.conftest import missing_uuid


def _interaction(client: TestClient, customer_id: str, **overrides: object) -> dict:
    payload = {
        "kind": "call",
        "subject": "Intro call",
        "body": "Discussed pricing.",
        "occurred_at": "2026-01-15T10:00:00Z",
        "author": "operator@crm.test",
    }
    payload.update(overrides)
    res = client.post(f"/api/customers/{customer_id}/interactions", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def test_create_returns_stored_fields(client: TestClient, customer: dict) -> None:
    body = _interaction(client, customer["id"])
    assert body["kind"] == "call"
    assert body["subject"] == "Intro call"
    assert body["body"] == "Discussed pricing."
    assert body["author"] == "operator@crm.test"
    assert body["customer_id"] == customer["id"]


def test_list_is_newest_first_by_occurred_at(client: TestClient, customer: dict) -> None:
    _interaction(client, customer["id"], subject="oldest", occurred_at="2026-01-01T09:00:00Z")
    _interaction(client, customer["id"], subject="newest", occurred_at="2026-03-01T09:00:00Z")
    _interaction(client, customer["id"], subject="middle", occurred_at="2026-02-01T09:00:00Z")

    body = client.get(f"/api/customers/{customer['id']}/interactions").json()
    assert body["total"] == 3
    assert [i["subject"] for i in body["items"]] == ["newest", "middle", "oldest"]


def test_list_pagination(client: TestClient, customer: dict) -> None:
    for day in range(1, 6):
        _interaction(
            client,
            customer["id"],
            subject=f"day-{day}",
            occurred_at=f"2026-01-0{day}T09:00:00Z",
        )

    page = client.get(
        f"/api/customers/{customer['id']}/interactions",
        params={"limit": 2, "offset": 0},
    ).json()
    assert page["total"] == 5
    assert [i["subject"] for i in page["items"]] == ["day-5", "day-4"]

    page2 = client.get(
        f"/api/customers/{customer['id']}/interactions",
        params={"limit": 2, "offset": 2},
    ).json()
    assert [i["subject"] for i in page2["items"]] == ["day-3", "day-2"]


def test_get_patch_delete_interaction(client: TestClient, customer: dict) -> None:
    created = _interaction(client, customer["id"])

    assert client.get(f"/api/interactions/{created['id']}").status_code == 200

    patched = client.patch(
        f"/api/interactions/{created['id']}",
        json={"subject": "Follow-up call", "kind": "meeting"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["subject"] == "Follow-up call"
    assert patched.json()["kind"] == "meeting"
    # Untouched field survives the partial update.
    assert patched.json()["body"] == "Discussed pricing."

    assert client.delete(f"/api/interactions/{created['id']}").status_code == 204
    assert client.get(f"/api/interactions/{created['id']}").status_code == 404


def test_create_on_archived_customer_returns_409(
    client: TestClient, customer: dict
) -> None:
    client.post(f"/api/customers/{customer['id']}/archive")

    res = client.post(
        f"/api/customers/{customer['id']}/interactions",
        json={"kind": "call", "body": "nope", "occurred_at": "2026-01-15T10:00:00Z"},
    )
    assert res.status_code == 409
    assert res.json()["detail"] == "customer is archived"


def test_existing_interactions_still_readable_when_archived(
    client: TestClient, customer: dict
) -> None:
    _interaction(client, customer["id"], subject="before archive")
    client.post(f"/api/customers/{customer['id']}/archive")

    body = client.get(f"/api/customers/{customer['id']}/interactions").json()
    assert body["total"] == 1


def test_occurred_at_is_required(client: TestClient, customer: dict) -> None:
    res = client.post(
        f"/api/customers/{customer['id']}/interactions",
        json={"kind": "call", "body": "no timestamp"},
    )
    assert res.status_code == 422


def test_unknown_customer_and_interaction_return_404(client: TestClient) -> None:
    res = client.post(
        f"/api/customers/{missing_uuid()}/interactions",
        json={"kind": "call", "body": "x", "occurred_at": "2026-01-15T10:00:00Z"},
    )
    assert res.status_code == 404
    assert client.get(f"/api/interactions/{missing_uuid()}").status_code == 404
    assert client.delete(f"/api/interactions/{missing_uuid()}").status_code == 404


def test_delete_customer_cascades_interactions(
    client: TestClient, customer: dict, db: Session
) -> None:
    _interaction(client, customer["id"])
    _interaction(client, customer["id"], occurred_at="2026-02-01T09:00:00Z")
    assert db.scalar(select(func.count()).select_from(Interaction)) == 2

    client.delete(f"/api/customers/{customer['id']}")

    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Interaction)) == 0
