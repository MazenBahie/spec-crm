"""Customer profile CRUD, archive semantics, and hard delete."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import missing_uuid


def test_create_returns_201_with_profile_fields(client: TestClient) -> None:
    res = client.post(
        "/api/customers", json={"display_name": "Globex", "company": "Globex Inc"}
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["display_name"] == "Globex"
    assert body["company"] == "Globex Inc"
    assert body["status"] == "active"
    assert body["archived_at"] is None
    assert body["created_at"] and body["updated_at"]


def test_create_rejects_blank_display_name(client: TestClient) -> None:
    assert client.post("/api/customers", json={"display_name": ""}).status_code == 422


def test_list_returns_items_and_total(client: TestClient) -> None:
    for name in ("Beta", "Alpha"):
        client.post("/api/customers", json={"display_name": name})

    body = client.get("/api/customers").json()
    assert body["total"] == 2
    # Sorted by display name.
    assert [c["display_name"] for c in body["items"]] == ["Alpha", "Beta"]


def test_list_search_matches_name_or_company(client: TestClient) -> None:
    client.post("/api/customers", json={"display_name": "Acme", "company": "Widgets"})
    client.post("/api/customers", json={"display_name": "Zeta", "company": "Acme Sub"})
    client.post("/api/customers", json={"display_name": "Other", "company": None})

    assert client.get("/api/customers", params={"q": "acme"}).json()["total"] == 2
    assert client.get("/api/customers", params={"q": "widgets"}).json()["total"] == 1
    assert client.get("/api/customers", params={"q": "nothing"}).json()["total"] == 0


def test_list_filters_by_status(client: TestClient, customer: dict) -> None:
    client.post("/api/customers", json={"display_name": "Still Active"})
    client.post(f"/api/customers/{customer['id']}/archive")

    active = client.get("/api/customers", params={"status": "active"}).json()
    archived = client.get("/api/customers", params={"status": "archived"}).json()
    assert active["total"] == 1
    assert archived["total"] == 1
    assert archived["items"][0]["id"] == customer["id"]


def test_get_detail_includes_contacts(client: TestClient, customer: dict) -> None:
    client.post(
        f"/api/customers/{customer['id']}/contacts",
        json={"kind": "email", "value": "hi@acme.test", "is_primary": True},
    )
    body = client.get(f"/api/customers/{customer['id']}").json()
    assert [c["value"] for c in body["contacts"]] == ["hi@acme.test"]


def test_patch_updates_only_supplied_fields(client: TestClient, customer: dict) -> None:
    res = client.patch(f"/api/customers/{customer['id']}", json={"company": "Acme Ltd"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["company"] == "Acme Ltd"
    assert body["display_name"] == customer["display_name"]


def test_archive_sets_status_and_timestamp(client: TestClient, customer: dict) -> None:
    res = client.post(f"/api/customers/{customer['id']}/archive")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "archived"
    assert body["archived_at"] is not None

    # Archiving deletes nothing -- the record is still fetchable.
    assert client.get(f"/api/customers/{customer['id']}").status_code == 200


def test_archive_is_idempotent(client: TestClient, customer: dict) -> None:
    first = client.post(f"/api/customers/{customer['id']}/archive").json()
    second = client.post(f"/api/customers/{customer['id']}/archive").json()
    assert first["archived_at"] == second["archived_at"]


def test_patch_status_back_to_active_clears_archived_at(
    client: TestClient, customer: dict
) -> None:
    client.post(f"/api/customers/{customer['id']}/archive")
    body = client.patch(
        f"/api/customers/{customer['id']}", json={"status": "active"}
    ).json()
    assert body["status"] == "active"
    assert body["archived_at"] is None


def test_delete_removes_customer(client: TestClient, customer: dict) -> None:
    assert client.delete(f"/api/customers/{customer['id']}").status_code == 204
    assert client.get(f"/api/customers/{customer['id']}").status_code == 404
    assert client.get("/api/customers").json()["total"] == 0


def test_unknown_id_returns_404_not_500(client: TestClient) -> None:
    unknown = missing_uuid()
    assert client.get(f"/api/customers/{unknown}").status_code == 404
    assert client.patch(f"/api/customers/{unknown}", json={"company": "x"}).status_code == 404
    assert client.post(f"/api/customers/{unknown}/archive").status_code == 404
    assert client.delete(f"/api/customers/{unknown}").status_code == 404


def test_malformed_uuid_returns_422(client: TestClient) -> None:
    assert client.get("/api/customers/not-a-uuid").status_code == 422


def test_unicode_display_name_round_trips(client: TestClient) -> None:
    name = "Ünicode — 客戶 🙂"
    created = client.post("/api/customers", json={"display_name": name}).json()
    assert client.get(f"/api/customers/{created['id']}").json()["display_name"] == name
