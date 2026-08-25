"""Pagination bounds, clamping, and total-count correctness."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _seed(client: TestClient, count: int) -> None:
    for i in range(count):
        res = client.post("/api/customers", json={"display_name": f"Customer {i:03d}"})
        assert res.status_code == 201, res.text


def test_default_limit_is_20(client: TestClient) -> None:
    _seed(client, 25)
    body = client.get("/api/customers").json()
    assert body["total"] == 25
    assert len(body["items"]) == 20


def test_offset_walks_the_whole_set_without_gaps(client: TestClient) -> None:
    _seed(client, 12)
    seen: list[str] = []
    for offset in range(0, 12, 5):
        page = client.get(
            "/api/customers", params={"limit": 5, "offset": offset}
        ).json()
        seen.extend(c["display_name"] for c in page["items"])

    assert seen == [f"Customer {i:03d}" for i in range(12)]
    assert len(set(seen)) == 12


def test_offset_past_the_end_returns_empty_but_keeps_total(client: TestClient) -> None:
    _seed(client, 3)
    body = client.get("/api/customers", params={"offset": 100}).json()
    assert body["items"] == []
    assert body["total"] == 3


def test_total_reflects_filters_not_page_size(client: TestClient) -> None:
    _seed(client, 7)
    client.post("/api/customers", json={"display_name": "Zzz Special"})

    filtered = client.get("/api/customers", params={"q": "special", "limit": 1}).json()
    assert filtered["total"] == 1
    assert len(filtered["items"]) == 1

    everything = client.get("/api/customers", params={"limit": 1}).json()
    assert everything["total"] == 8
    assert len(everything["items"]) == 1


def test_limit_above_max_is_rejected_with_422(client: TestClient) -> None:
    assert client.get("/api/customers", params={"limit": 101}).status_code == 422


def test_limit_at_max_is_accepted(client: TestClient) -> None:
    assert client.get("/api/customers", params={"limit": 100}).status_code == 200


def test_limit_below_one_is_rejected_with_422(client: TestClient) -> None:
    assert client.get("/api/customers", params={"limit": 0}).status_code == 422
    assert client.get("/api/customers", params={"limit": -5}).status_code == 422


def test_negative_offset_is_rejected_with_422(client: TestClient) -> None:
    assert client.get("/api/customers", params={"offset": -1}).status_code == 422


def test_non_numeric_paging_params_rejected(client: TestClient) -> None:
    assert client.get("/api/customers", params={"limit": "many"}).status_code == 422
    assert client.get("/api/customers", params={"offset": "start"}).status_code == 422


def test_invalid_status_filter_rejected(client: TestClient) -> None:
    assert client.get("/api/customers", params={"status": "banana"}).status_code == 422


def test_interaction_list_paging_bounds(client: TestClient, customer: dict) -> None:
    url = f"/api/customers/{customer['id']}/interactions"
    assert client.get(url, params={"limit": 101}).status_code == 422
    assert client.get(url, params={"limit": 0}).status_code == 422
    assert client.get(url, params={"offset": -1}).status_code == 422
    assert client.get(url, params={"limit": 100, "offset": 0}).status_code == 200


def test_empty_list_shape(client: TestClient) -> None:
    assert client.get("/api/customers").json() == {"items": [], "total": 0}
