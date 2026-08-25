"""Contact-detail CRUD, the single-primary-per-kind rule, and cascade delete."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.customer import ContactDetail
from tests.conftest import missing_uuid


def _contact(client: TestClient, customer_id: str, **overrides: object) -> dict:
    payload = {"kind": "phone", "value": "+1 555 0100", "is_primary": False}
    payload.update(overrides)
    res = client.post(f"/api/customers/{customer_id}/contacts", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def test_create_and_list_contacts(client: TestClient, customer: dict) -> None:
    _contact(client, customer["id"], kind="phone", value="+1 555 0100")
    _contact(client, customer["id"], kind="email", value="ops@acme.test")

    rows = client.get(f"/api/customers/{customer['id']}/contacts").json()
    assert {(r["kind"], r["value"]) for r in rows} == {
        ("phone", "+1 555 0100"),
        ("email", "ops@acme.test"),
    }


def test_multiple_non_primary_contacts_of_same_kind_allowed(
    client: TestClient, customer: dict
) -> None:
    """The partial index must not degenerate into a plain unique index."""
    _contact(client, customer["id"], kind="phone", value="+1 555 0001")
    _contact(client, customer["id"], kind="phone", value="+1 555 0002")
    _contact(client, customer["id"], kind="phone", value="+1 555 0003")

    rows = client.get(f"/api/customers/{customer['id']}/contacts").json()
    assert len([r for r in rows if r["kind"] == "phone"]) == 3


def test_second_primary_of_same_kind_rejected_with_409(
    client: TestClient, customer: dict
) -> None:
    _contact(client, customer["id"], kind="phone", value="+1 555 0001", is_primary=True)
    res = client.post(
        f"/api/customers/{customer['id']}/contacts",
        json={"kind": "phone", "value": "+1 555 0002", "is_primary": True},
    )
    assert res.status_code == 409
    assert "primary" in res.json()["detail"]


def test_primary_of_different_kind_allowed(client: TestClient, customer: dict) -> None:
    _contact(client, customer["id"], kind="phone", value="+1 555 0001", is_primary=True)
    _contact(client, customer["id"], kind="email", value="a@acme.test", is_primary=True)
    _contact(client, customer["id"], kind="address", value="1 Main St", is_primary=True)

    rows = client.get(f"/api/customers/{customer['id']}/contacts").json()
    assert sum(1 for r in rows if r["is_primary"]) == 3


def test_promoting_second_contact_to_primary_rejected(
    client: TestClient, customer: dict
) -> None:
    _contact(client, customer["id"], kind="email", value="a@acme.test", is_primary=True)
    other = _contact(client, customer["id"], kind="email", value="b@acme.test")

    res = client.patch(
        f"/api/customers/{customer['id']}/contacts/{other['id']}",
        json={"is_primary": True},
    )
    assert res.status_code == 409


def test_patching_the_existing_primary_is_allowed(
    client: TestClient, customer: dict
) -> None:
    """Re-saving the current primary must not collide with itself."""
    primary = _contact(
        client, customer["id"], kind="email", value="a@acme.test", is_primary=True
    )
    res = client.patch(
        f"/api/customers/{customer['id']}/contacts/{primary['id']}",
        json={"value": "changed@acme.test", "is_primary": True},
    )
    assert res.status_code == 200, res.text
    assert res.json()["value"] == "changed@acme.test"


def test_demote_then_promote_another(client: TestClient, customer: dict) -> None:
    first = _contact(
        client, customer["id"], kind="phone", value="+1 555 0001", is_primary=True
    )
    second = _contact(client, customer["id"], kind="phone", value="+1 555 0002")

    client.patch(
        f"/api/customers/{customer['id']}/contacts/{first['id']}",
        json={"is_primary": False},
    )
    res = client.patch(
        f"/api/customers/{customer['id']}/contacts/{second['id']}",
        json={"is_primary": True},
    )
    assert res.status_code == 200, res.text
    assert res.json()["is_primary"] is True


def test_get_and_delete_contact(client: TestClient, customer: dict) -> None:
    contact = _contact(client, customer["id"], label="work")
    got = client.get(f"/api/customers/{customer['id']}/contacts/{contact['id']}")
    assert got.status_code == 200
    assert got.json()["label"] == "work"

    assert (
        client.delete(
            f"/api/customers/{customer['id']}/contacts/{contact['id']}"
        ).status_code
        == 204
    )
    assert (
        client.get(
            f"/api/customers/{customer['id']}/contacts/{contact['id']}"
        ).status_code
        == 404
    )


def test_contact_for_unknown_customer_returns_404(client: TestClient) -> None:
    res = client.post(
        f"/api/customers/{missing_uuid()}/contacts",
        json={"kind": "phone", "value": "+1 555 0000"},
    )
    assert res.status_code == 404


def test_contact_of_other_customer_not_reachable(client: TestClient, customer: dict) -> None:
    other = client.post("/api/customers", json={"display_name": "Other"}).json()
    contact = _contact(client, other["id"])
    res = client.get(f"/api/customers/{customer['id']}/contacts/{contact['id']}")
    assert res.status_code == 404


def test_invalid_kind_rejected(client: TestClient, customer: dict) -> None:
    res = client.post(
        f"/api/customers/{customer['id']}/contacts",
        json={"kind": "carrier-pigeon", "value": "x"},
    )
    assert res.status_code == 422


def test_delete_customer_cascades_contacts(
    client: TestClient, customer: dict, db: Session
) -> None:
    _contact(client, customer["id"], kind="phone", value="+1 555 0001")
    _contact(client, customer["id"], kind="email", value="a@acme.test")
    assert db.scalar(select(func.count()).select_from(ContactDetail)) == 2

    assert client.delete(f"/api/customers/{customer['id']}").status_code == 204

    db.expire_all()
    assert db.scalar(select(func.count()).select_from(ContactDetail)) == 0
