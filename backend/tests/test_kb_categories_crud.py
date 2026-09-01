"""Knowledge-base categories: CRUD, unique slug, and delete-with-children."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import missing_uuid


def _create_category(agent_client: TestClient, slug: str = "billing", **extra) -> dict:
    payload = {"slug": slug, "name": "Billing", **extra}
    res = agent_client.post("/api/kb/categories", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def _create_article(agent_client: TestClient, category_id: str | None = None, **extra) -> dict:
    payload = {
        "slug": extra.pop("slug", "how-to-pay"),
        "title": "How to pay",
        "body": "Body text",
        "kind": "help",
        "category_id": category_id,
        **extra,
    }
    res = agent_client.post("/api/kb/articles", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def test_create_and_get_category(agent_client: TestClient) -> None:
    created = _create_category(agent_client)

    res = agent_client.get(f"/api/kb/categories/{created['id']}")
    assert res.status_code == 200, res.text
    assert res.json()["slug"] == "billing"
    assert res.json()["name"] == "Billing"


def test_list_categories_ordered_by_sort_order_then_name(agent_client: TestClient) -> None:
    _create_category(agent_client, slug="zeta", name="Zeta", sort_order=1)
    _create_category(agent_client, slug="alpha", name="Alpha", sort_order=0)

    res = agent_client.get("/api/kb/categories")
    assert res.status_code == 200, res.text
    assert [c["slug"] for c in res.json()["items"]] == ["alpha", "zeta"]


def test_update_category(agent_client: TestClient) -> None:
    created = _create_category(agent_client)

    res = agent_client.patch(
        f"/api/kb/categories/{created['id']}", json={"name": "Billing & Payments"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["name"] == "Billing & Payments"
    assert res.json()["slug"] == "billing"


def test_duplicate_category_slug_is_conflict(agent_client: TestClient) -> None:
    _create_category(agent_client, slug="billing")

    res = agent_client.post("/api/kb/categories", json={"slug": "billing", "name": "Other"})
    assert res.status_code == 409, res.text


def test_delete_category_without_articles(agent_client: TestClient) -> None:
    created = _create_category(agent_client)

    res = agent_client.delete(f"/api/kb/categories/{created['id']}")
    assert res.status_code == 204, res.text
    assert agent_client.get(f"/api/kb/categories/{created['id']}").status_code == 404


def test_delete_category_with_articles_requires_force(agent_client: TestClient) -> None:
    category = _create_category(agent_client)
    article = _create_article(agent_client, category_id=category["id"])

    blocked = agent_client.delete(f"/api/kb/categories/{category['id']}")
    assert blocked.status_code == 409, blocked.text

    forced = agent_client.delete(f"/api/kb/categories/{category['id']}?force=true")
    assert forced.status_code == 204, forced.text

    # The article survives, just uncategorised.
    survivor = agent_client.get(f"/api/kb/articles/{article['id']}")
    assert survivor.status_code == 200, survivor.text
    assert survivor.json()["category_id"] is None


def test_unknown_category_is_not_found(agent_client: TestClient) -> None:
    assert agent_client.get(f"/api/kb/categories/{missing_uuid()}").status_code == 404
    assert (
        agent_client.patch(
            f"/api/kb/categories/{missing_uuid()}", json={"name": "x"}
        ).status_code
        == 404
    )


def test_categories_require_agent_auth(client: TestClient) -> None:
    assert client.get("/api/kb/categories").status_code == 401
    assert client.post("/api/kb/categories", json={"slug": "x", "name": "x"}).status_code == 401
