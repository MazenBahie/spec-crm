"""Knowledge-base staff search, kind/status filters, and pagination."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _create_article(agent_client: TestClient, **fields) -> dict:
    payload = {"kind": "faq", "body": "generic body", **fields}
    res = agent_client.post("/api/kb/articles", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def test_q_matches_title_case_insensitively(agent_client: TestClient) -> None:
    _create_article(agent_client, slug="one", title="Resetting Your Password")
    _create_article(agent_client, slug="two", title="Billing overview")

    res = agent_client.get("/api/kb/articles", params={"q": "password"})
    assert res.status_code == 200, res.text
    assert [a["slug"] for a in res.json()["items"]] == ["one"]


def test_q_matches_summary(agent_client: TestClient) -> None:
    _create_article(
        agent_client, slug="one", title="Account", summary="How to change your billing plan"
    )
    _create_article(agent_client, slug="two", title="Other", summary="Nothing relevant")

    res = agent_client.get("/api/kb/articles", params={"q": "billing"})
    assert res.status_code == 200, res.text
    assert [a["slug"] for a in res.json()["items"]] == ["one"]


def test_q_matches_body(agent_client: TestClient) -> None:
    _create_article(agent_client, slug="one", title="Account", body="Contact support by email.")
    _create_article(agent_client, slug="two", title="Other", body="Unrelated content.")

    res = agent_client.get("/api/kb/articles", params={"q": "support"})
    assert res.status_code == 200, res.text
    assert [a["slug"] for a in res.json()["items"]] == ["one"]


def test_kind_filter(agent_client: TestClient) -> None:
    _create_article(agent_client, slug="one", title="A", kind="faq")
    _create_article(agent_client, slug="two", title="B", kind="guide")

    res = agent_client.get("/api/kb/articles", params={"kind": "guide"})
    assert res.status_code == 200, res.text
    assert [a["slug"] for a in res.json()["items"]] == ["two"]


def test_status_filter(agent_client: TestClient) -> None:
    draft = _create_article(agent_client, slug="one", title="Draft one")
    published = _create_article(agent_client, slug="two", title="Published one")
    agent_client.post(f"/api/kb/articles/{published['id']}/publish")

    res = agent_client.get("/api/kb/articles", params={"status": "published"})
    assert res.status_code == 200, res.text
    assert [a["slug"] for a in res.json()["items"]] == ["two"]

    res = agent_client.get("/api/kb/articles", params={"status": "draft"})
    assert res.status_code == 200, res.text
    assert [a["slug"] for a in res.json()["items"]] == [draft["slug"]]


def test_category_filter(agent_client: TestClient) -> None:
    category = agent_client.post(
        "/api/kb/categories", json={"slug": "billing", "name": "Billing"}
    ).json()
    _create_article(agent_client, slug="in-cat", title="In category", category_id=category["id"])
    _create_article(agent_client, slug="no-cat", title="No category")

    res = agent_client.get("/api/kb/articles", params={"category_id": category["id"]})
    assert res.status_code == 200, res.text
    assert [a["slug"] for a in res.json()["items"]] == ["in-cat"]


def test_empty_q_is_no_filter(agent_client: TestClient) -> None:
    _create_article(agent_client, slug="one", title="A")
    _create_article(agent_client, slug="two", title="B")

    res = agent_client.get("/api/kb/articles", params={"q": ""})
    assert res.status_code == 200, res.text
    assert res.json()["total"] == 2


def test_pagination(agent_client: TestClient) -> None:
    for i in range(5):
        _create_article(agent_client, slug=f"a-{i}", title=f"Article {i}")

    page1 = agent_client.get("/api/kb/articles", params={"limit": 2, "offset": 0})
    page2 = agent_client.get("/api/kb/articles", params={"limit": 2, "offset": 2})
    assert page1.status_code == 200, page1.text
    assert page2.status_code == 200, page2.text
    assert page1.json()["total"] == 5
    assert len(page1.json()["items"]) == 2
    assert len(page2.json()["items"]) == 2
    assert {a["slug"] for a in page1.json()["items"]}.isdisjoint(
        {a["slug"] for a in page2.json()["items"]}
    )
