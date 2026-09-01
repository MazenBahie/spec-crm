"""Portal knowledge-base browsing: published-only, search, view-count bump."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _create_article(agent_client: TestClient, **fields) -> dict:
    payload = {"kind": "faq", "body": "generic body", **fields}
    res = agent_client.post("/api/kb/articles", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def _published_article(agent_client: TestClient, **fields) -> dict:
    article = _create_article(agent_client, **fields)
    res = agent_client.post(f"/api/kb/articles/{article['id']}/publish")
    assert res.status_code == 200, res.text
    return res.json()


def test_portal_list_excludes_drafts(client: TestClient, agent_client: TestClient) -> None:
    _published_article(agent_client, slug="published-one", title="Published")
    _create_article(agent_client, slug="draft-one", title="Draft")

    res = client.get("/api/portal/kb/articles")
    assert res.status_code == 200, res.text
    assert [a["slug"] for a in res.json()["items"]] == ["published-one"]


def test_portal_search_returns_only_published(client: TestClient, agent_client: TestClient) -> None:
    _published_article(agent_client, slug="published-help", title="Password help")
    _create_article(agent_client, slug="draft-help", title="Password help draft")

    res = client.get("/api/portal/kb/articles", params={"q": "password"})
    assert res.status_code == 200, res.text
    assert [a["slug"] for a in res.json()["items"]] == ["published-help"]


def test_portal_get_by_slug_returns_full_article(
    client: TestClient, agent_client: TestClient
) -> None:
    _published_article(agent_client, slug="published-one", title="Published", body="Full body")

    res = client.get("/api/portal/kb/articles/published-one")
    assert res.status_code == 200, res.text
    assert res.json()["body"] == "Full body"


def test_portal_get_draft_by_slug_is_404(client: TestClient, agent_client: TestClient) -> None:
    _create_article(agent_client, slug="draft-only", title="Draft only")

    res = client.get("/api/portal/kb/articles/draft-only")
    assert res.status_code == 404, res.text


def test_view_count_increments_on_detail_fetch(
    client: TestClient, agent_client: TestClient
) -> None:
    published = _published_article(agent_client, slug="published-one", title="Published")
    assert published["view_count"] == 0

    first = client.get("/api/portal/kb/articles/published-one")
    assert first.status_code == 200, first.text
    assert first.json()["view_count"] == 1

    second = client.get("/api/portal/kb/articles/published-one")
    assert second.status_code == 200, second.text
    assert second.json()["view_count"] == 2


def test_portal_categories_only_list_categories_with_published_articles(
    client: TestClient, agent_client: TestClient
) -> None:
    with_published = agent_client.post(
        "/api/kb/categories", json={"slug": "with-published", "name": "With published"}
    ).json()
    empty = agent_client.post(
        "/api/kb/categories", json={"slug": "empty", "name": "Empty"}
    ).json()
    _published_article(
        agent_client, slug="in-cat", title="In category", category_id=with_published["id"]
    )
    _create_article(
        agent_client, slug="draft-in-empty", title="Draft only", category_id=empty["id"]
    )

    res = client.get("/api/portal/kb/categories")
    assert res.status_code == 200, res.text
    slugs = [c["slug"] for c in res.json()["items"]]
    assert slugs == ["with-published"]


def test_portal_kind_filter(client: TestClient, agent_client: TestClient) -> None:
    _published_article(agent_client, slug="faq-one", title="FAQ", kind="faq")
    _published_article(agent_client, slug="guide-one", title="Guide", kind="guide")

    res = client.get("/api/portal/kb/articles", params={"kind": "guide"})
    assert res.status_code == 200, res.text
    assert [a["slug"] for a in res.json()["items"]] == ["guide-one"]


def test_portal_category_slug_filter(client: TestClient, agent_client: TestClient) -> None:
    category = agent_client.post(
        "/api/kb/categories", json={"slug": "billing", "name": "Billing"}
    ).json()
    _published_article(
        agent_client, slug="in-cat", title="In category", category_id=category["id"]
    )
    _published_article(agent_client, slug="no-cat", title="No category")

    res = client.get("/api/portal/kb/articles", params={"category_slug": "billing"})
    assert res.status_code == 200, res.text
    assert [a["slug"] for a in res.json()["items"]] == ["in-cat"]


def test_portal_kb_needs_no_auth(client: TestClient) -> None:
    assert client.get("/api/portal/kb/articles").status_code == 200
    assert client.get("/api/portal/kb/categories").status_code == 200
