"""Knowledge-base articles: draft/publish lifecycle, editing, deletion."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import missing_uuid


def _create_article(agent_client: TestClient, slug: str = "reset-password", **extra) -> dict:
    payload = {
        "slug": slug,
        "title": "Reset your password",
        "body": "Go to settings and click reset.",
        "kind": "faq",
        **extra,
    }
    res = agent_client.post("/api/kb/articles", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def test_create_draft_article(agent_client: TestClient, agent: dict) -> None:
    article = _create_article(agent_client)

    assert article["status"] == "draft"
    assert article["published_at"] is None
    assert article["view_count"] == 0
    assert article["author_agent_id"] == agent["id"]


def test_patch_fields(agent_client: TestClient) -> None:
    article = _create_article(agent_client)

    res = agent_client.patch(
        f"/api/kb/articles/{article['id']}",
        json={"title": "Reset your password (updated)", "summary": "Quick steps"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["title"] == "Reset your password (updated)"
    assert res.json()["summary"] == "Quick steps"
    assert res.json()["body"] == article["body"]


def test_publish_sets_published_at(agent_client: TestClient) -> None:
    article = _create_article(agent_client)

    res = agent_client.post(f"/api/kb/articles/{article['id']}/publish")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "published"
    assert res.json()["published_at"] is not None


def test_publishing_twice_does_not_move_published_at(agent_client: TestClient) -> None:
    article = _create_article(agent_client)
    first = agent_client.post(f"/api/kb/articles/{article['id']}/publish")
    assert first.status_code == 200, first.text
    first_published_at = first.json()["published_at"]

    second = agent_client.post(f"/api/kb/articles/{article['id']}/publish")
    assert second.status_code == 200, second.text
    assert second.json()["published_at"] == first_published_at


def test_unpublish_keeps_published_at(agent_client: TestClient) -> None:
    article = _create_article(agent_client)
    published = agent_client.post(f"/api/kb/articles/{article['id']}/publish")
    published_at = published.json()["published_at"]

    res = agent_client.post(f"/api/kb/articles/{article['id']}/unpublish")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "draft"
    assert res.json()["published_at"] == published_at


def test_publishing_an_article_with_empty_body_is_rejected(agent_client: TestClient) -> None:
    article = _create_article(agent_client, body=" ")

    res = agent_client.post(f"/api/kb/articles/{article['id']}/publish")
    assert res.status_code == 409, res.text


def test_delete_article(agent_client: TestClient) -> None:
    article = _create_article(agent_client)

    assert agent_client.delete(f"/api/kb/articles/{article['id']}").status_code == 204
    assert agent_client.get(f"/api/kb/articles/{article['id']}").status_code == 404


def test_duplicate_slug_is_conflict(agent_client: TestClient) -> None:
    _create_article(agent_client, slug="reset-password")

    res = agent_client.post(
        "/api/kb/articles",
        json={
            "slug": "reset-password",
            "title": "Different title",
            "body": "x",
            "kind": "help",
        },
    )
    assert res.status_code == 409, res.text


def test_updating_to_a_taken_slug_is_conflict(agent_client: TestClient) -> None:
    _create_article(agent_client, slug="one")
    two = _create_article(agent_client, slug="two")

    res = agent_client.patch(f"/api/kb/articles/{two['id']}", json={"slug": "one"})
    assert res.status_code == 409, res.text


def test_unknown_article_is_not_found(agent_client: TestClient) -> None:
    assert agent_client.get(f"/api/kb/articles/{missing_uuid()}").status_code == 404


def test_invalid_kind_is_validation_error(agent_client: TestClient) -> None:
    res = agent_client.post(
        "/api/kb/articles",
        json={"slug": "x", "title": "x", "body": "x", "kind": "unknown"},
    )
    assert res.status_code == 422, res.text


def test_articles_require_agent_auth(client: TestClient) -> None:
    assert client.get("/api/kb/articles").status_code == 401
    assert (
        client.post(
            "/api/kb/articles",
            json={"slug": "x", "title": "x", "body": "x", "kind": "faq"},
        ).status_code
        == 401
    )
