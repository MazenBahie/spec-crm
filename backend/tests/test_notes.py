"""Notes: CRUD, verbatim content preservation, archived guard, cascade."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.customer import Note
from tests.conftest import missing_uuid


def _note(client: TestClient, customer_id: str, body: str = "First note") -> dict:
    res = client.post(f"/api/customers/{customer_id}/notes", json={"body": body})
    assert res.status_code == 201, res.text
    return res.json()


def test_create_and_list_notes(client: TestClient, customer: dict) -> None:
    _note(client, customer["id"], "alpha")
    _note(client, customer["id"], "beta")

    rows = client.get(f"/api/customers/{customer['id']}/notes").json()
    assert {r["body"] for r in rows} == {"alpha", "beta"}


def test_update_note(client: TestClient, customer: dict) -> None:
    note = _note(client, customer["id"])
    res = client.patch(f"/api/notes/{note['id']}", json={"body": "edited"})
    assert res.status_code == 200, res.text
    assert res.json()["body"] == "edited"
    assert client.get(f"/api/notes/{note['id']}").json()["body"] == "edited"


def test_delete_note(client: TestClient, customer: dict) -> None:
    note = _note(client, customer["id"])
    assert client.delete(f"/api/notes/{note['id']}").status_code == 204
    assert client.get(f"/api/notes/{note['id']}").status_code == 404
    assert client.get(f"/api/customers/{customer['id']}/notes").json() == []


def test_content_preserved_verbatim_including_unicode(
    client: TestClient, customer: dict
) -> None:
    body = (
        "Line one\n"
        "  indented\ttabbed\n"
        "Unicode: éàü 客戶 🙂 — em-dash\n"
        "Quotes: \"double\" 'single' `tick`\n"
        "Markup-ish: <script>alert(1)</script> & ampersand"
    )
    note = _note(client, customer["id"], body)
    assert note["body"] == body
    assert client.get(f"/api/notes/{note['id']}").json()["body"] == body


def test_blank_body_rejected(client: TestClient, customer: dict) -> None:
    res = client.post(f"/api/customers/{customer['id']}/notes", json={"body": ""})
    assert res.status_code == 422


def test_create_on_archived_customer_returns_409(
    client: TestClient, customer: dict
) -> None:
    client.post(f"/api/customers/{customer['id']}/archive")
    res = client.post(f"/api/customers/{customer['id']}/notes", json={"body": "nope"})
    assert res.status_code == 409
    assert res.json()["detail"] == "customer is archived"


def test_unknown_customer_and_note_return_404(client: TestClient) -> None:
    res = client.post(f"/api/customers/{missing_uuid()}/notes", json={"body": "x"})
    assert res.status_code == 404
    assert client.get(f"/api/notes/{missing_uuid()}").status_code == 404
    assert client.patch(f"/api/notes/{missing_uuid()}", json={"body": "x"}).status_code == 404
    assert client.delete(f"/api/notes/{missing_uuid()}").status_code == 404


def test_delete_customer_cascades_notes(
    client: TestClient, customer: dict, db: Session
) -> None:
    _note(client, customer["id"], "one")
    _note(client, customer["id"], "two")
    assert db.scalar(select(func.count()).select_from(Note)) == 2

    client.delete(f"/api/customers/{customer['id']}")

    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Note)) == 0
