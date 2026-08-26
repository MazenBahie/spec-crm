"""Ticket queue: priority/created ordering, search, filters, pagination bounds."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _create(client: TestClient, customer_id: str, **overrides: object) -> dict:
    payload = {"customer_id": customer_id, "subject": "ticket"}
    payload.update(overrides)
    res = client.post("/api/tickets", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def test_default_ordering_is_urgent_first_then_low_last(
    client: TestClient, customer: dict
) -> None:
    """Regression guard: SQLite stores the priority enum as VARCHAR and would
    sort it alphabetically (high < low < normal < urgent) unless list_tickets
    orders by an explicit CASE expression instead of the raw column."""
    _create(client, customer["id"], subject="low one", priority="low")
    _create(client, customer["id"], subject="urgent one", priority="urgent")
    _create(client, customer["id"], subject="normal one", priority="normal")
    _create(client, customer["id"], subject="high one", priority="high")

    body = client.get("/api/tickets").json()
    priorities = [t["priority"] for t in body["items"]]
    assert priorities == ["urgent", "high", "normal", "low"]


def test_search_matches_reference_subject_and_description(
    client: TestClient, customer: dict
) -> None:
    target = _create(
        client, customer["id"], subject="Password reset", description="user forgot login"
    )
    _create(client, customer["id"], subject="Unrelated", description="nothing to do with it")

    by_subject = client.get("/api/tickets", params={"q": "password"}).json()
    assert [t["id"] for t in by_subject["items"]] == [target["id"]]

    by_description = client.get("/api/tickets", params={"q": "forgot"}).json()
    assert [t["id"] for t in by_description["items"]] == [target["id"]]

    by_reference = client.get("/api/tickets", params={"q": target["reference"].lower()}).json()
    assert [t["id"] for t in by_reference["items"]] == [target["id"]]


def test_filters_compose(client: TestClient, customer: dict, ticket_category: dict) -> None:
    match = _create(
        client, customer["id"], subject="matches all filters",
        priority="high", category_id=ticket_category["id"],
    )
    _create(client, customer["id"], subject="wrong priority", priority="low", category_id=ticket_category["id"])

    body = client.get(
        "/api/tickets",
        params={"priority": "high", "category_id": ticket_category["id"]},
    ).json()
    assert [t["id"] for t in body["items"]] == [match["id"]]


def test_status_filter(client: TestClient, ticket: dict) -> None:
    client.post(f"/api/tickets/{ticket['id']}/status", json={"status": "triaged"})

    open_page = client.get("/api/tickets", params={"status": "open"}).json()
    triaged_page = client.get("/api/tickets", params={"status": "triaged"}).json()
    assert ticket["id"] not in [t["id"] for t in open_page["items"]]
    assert ticket["id"] in [t["id"] for t in triaged_page["items"]]


def test_customer_id_filter(client: TestClient, customer: dict, ticket: dict) -> None:
    other_customer = client.post("/api/customers", json={"display_name": "Other"}).json()
    _create(client, other_customer["id"], subject="belongs to other")

    body = client.get("/api/tickets", params={"customer_id": customer["id"]}).json()
    assert [t["id"] for t in body["items"]] == [ticket["id"]]


def test_limit_above_max_returns_422(client: TestClient) -> None:
    assert client.get("/api/tickets", params={"limit": 101}).status_code == 422


def test_limit_below_one_returns_422(client: TestClient) -> None:
    assert client.get("/api/tickets", params={"limit": 0}).status_code == 422


def test_negative_offset_returns_422(client: TestClient) -> None:
    assert client.get("/api/tickets", params={"offset": -1}).status_code == 422


def test_total_reflects_filters_not_page_size(client: TestClient, customer: dict) -> None:
    for i in range(5):
        _create(client, customer["id"], subject=f"t{i}")

    filtered = client.get("/api/tickets", params={"limit": 1, "q": "t3"}).json()
    assert filtered["total"] == 1

    everything = client.get("/api/tickets", params={"limit": 1}).json()
    assert everything["total"] == 5
    assert len(everything["items"]) == 1


def test_empty_list_shape(client: TestClient) -> None:
    assert client.get("/api/tickets").json() == {"items": [], "total": 0}


def test_customer_scoped_ticket_list(client: TestClient, customer: dict, ticket: dict) -> None:
    other_customer = client.post("/api/customers", json={"display_name": "Other"}).json()
    _create(client, other_customer["id"], subject="not this customer's")

    body = client.get(f"/api/customers/{customer['id']}/tickets").json()
    assert [t["id"] for t in body["items"]] == [ticket["id"]]


def test_customer_scoped_ticket_list_404_for_unknown_customer(client: TestClient) -> None:
    from tests.conftest import missing_uuid

    res = client.get(f"/api/customers/{missing_uuid()}/tickets")
    assert res.status_code == 404
