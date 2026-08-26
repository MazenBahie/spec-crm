"""Category and agent CRUD, duplicate-name rejection, in-use protection."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import missing_uuid


# --------------------------------------------------------------------------- #
# Categories
# --------------------------------------------------------------------------- #
def test_create_and_list_categories(client: TestClient) -> None:
    client.post("/api/ticket-categories", json={"name": "Billing"})
    client.post("/api/ticket-categories", json={"name": "Technical"})

    rows = client.get("/api/ticket-categories").json()
    assert {r["name"] for r in rows} == {"Billing", "Technical"}


def test_create_category_defaults(client: TestClient) -> None:
    res = client.post("/api/ticket-categories", json={"name": "General"})
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["default_priority"] == "normal"
    assert body["is_active"] is True


def test_duplicate_category_name_returns_409(client: TestClient) -> None:
    client.post("/api/ticket-categories", json={"name": "Billing"})
    res = client.post("/api/ticket-categories", json={"name": "Billing"})
    assert res.status_code == 409


def test_duplicate_category_name_case_insensitive(client: TestClient) -> None:
    client.post("/api/ticket-categories", json={"name": "Billing"})
    res = client.post("/api/ticket-categories", json={"name": "billing"})
    assert res.status_code == 409


def test_update_category(client: TestClient, ticket_category: dict) -> None:
    res = client.patch(
        f"/api/ticket-categories/{ticket_category['id']}",
        json={"description": "Payment and invoicing issues"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["description"] == "Payment and invoicing issues"


def test_rename_to_existing_name_returns_409(client: TestClient) -> None:
    client.post("/api/ticket-categories", json={"name": "Billing"})
    other = client.post("/api/ticket-categories", json={"name": "Technical"}).json()

    res = client.patch(f"/api/ticket-categories/{other['id']}", json={"name": "Billing"})
    assert res.status_code == 409


def test_renaming_a_category_to_its_own_name_is_allowed(
    client: TestClient, ticket_category: dict
) -> None:
    res = client.patch(
        f"/api/ticket-categories/{ticket_category['id']}",
        json={"name": ticket_category["name"]},
    )
    assert res.status_code == 200, res.text


def test_deactivate_category_drops_it_from_active_only_filter(
    client: TestClient, ticket_category: dict
) -> None:
    client.patch(f"/api/ticket-categories/{ticket_category['id']}", json={"is_active": False})

    all_rows = client.get("/api/ticket-categories").json()
    active_rows = client.get("/api/ticket-categories", params={"active_only": "true"}).json()
    assert any(r["id"] == ticket_category["id"] for r in all_rows)
    assert not any(r["id"] == ticket_category["id"] for r in active_rows)


def test_delete_unused_category_succeeds(client: TestClient, ticket_category: dict) -> None:
    assert client.delete(f"/api/ticket-categories/{ticket_category['id']}").status_code == 204
    assert client.get("/api/ticket-categories").json() == []


def test_delete_in_use_category_returns_409(
    client: TestClient, customer: dict, ticket_category: dict
) -> None:
    client.post(
        "/api/tickets",
        json={"customer_id": customer["id"], "subject": "x", "category_id": ticket_category["id"]},
    )
    res = client.delete(f"/api/ticket-categories/{ticket_category['id']}")
    assert res.status_code == 409
    assert "in use by 1 ticket" in res.json()["detail"]


def test_unknown_category_returns_404(client: TestClient) -> None:
    unknown = missing_uuid()
    assert client.patch(f"/api/ticket-categories/{unknown}", json={"name": "x"}).status_code == 404
    assert client.delete(f"/api/ticket-categories/{unknown}").status_code == 404


# --------------------------------------------------------------------------- #
# Agents
# --------------------------------------------------------------------------- #
def test_create_and_list_agents(client: TestClient) -> None:
    client.post("/api/agents", json={"display_name": "Dana"})
    client.post("/api/agents", json={"display_name": "Sam"})

    rows = client.get("/api/agents").json()
    assert {r["display_name"] for r in rows} == {"Dana", "Sam"}
    assert all(r["is_active"] for r in rows)


def test_update_agent(client: TestClient, agent: dict) -> None:
    res = client.patch(f"/api/agents/{agent['id']}", json={"email": "new@crm.test"})
    assert res.status_code == 200, res.text
    assert res.json()["email"] == "new@crm.test"


def test_delete_agent_deactivates_rather_than_deletes(
    client: TestClient, agent: dict
) -> None:
    res = client.delete(f"/api/agents/{agent['id']}")
    assert res.status_code == 200, res.text
    assert res.json()["is_active"] is False

    # Still listed (not gone), just inactive.
    all_rows = client.get("/api/agents").json()
    assert any(r["id"] == agent["id"] for r in all_rows)
    active_rows = client.get("/api/agents", params={"active_only": "true"}).json()
    assert not any(r["id"] == agent["id"] for r in active_rows)


def test_unknown_agent_returns_404(client: TestClient) -> None:
    unknown = missing_uuid()
    assert client.patch(f"/api/agents/{unknown}", json={"display_name": "x"}).status_code == 404
    assert client.delete(f"/api/agents/{unknown}").status_code == 404
