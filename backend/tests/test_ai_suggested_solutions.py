"""Story 12 -- suggested solutions."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.services.ai import provider as ai_provider
from tests.conftest import missing_uuid


def _publish_article(client: TestClient, *, slug: str, title: str, body: str = "content") -> dict:
    res = client.post(
        "/api/kb/articles",
        json={"slug": slug, "title": title, "body": body, "kind": "help", "status": "draft"},
    )
    assert res.status_code == 201, res.text
    article = res.json()
    published = client.post(f"/api/kb/articles/{article['id']}/publish")
    assert published.status_code == 200
    return published.json()


@pytest.fixture()
def login_ticket(client: TestClient, customer: dict) -> dict:
    res = client.post(
        "/api/tickets",
        json={
            "customer_id": customer["id"],
            "subject": "Cannot log in",
            "description": "Password reset email never arrives.",
        },
    )
    assert res.status_code == 201
    return res.json()


def test_matching_published_article_is_suggested(
    agent_client: TestClient, login_ticket: dict
):
    article = _publish_article(
        agent_client, slug="reset-login", title="Cannot log in? Try this password reset guide"
    )
    res = agent_client.get(f"/api/tickets/{login_ticket['id']}/ai/suggested-solutions")
    assert res.status_code == 200
    ids = [a["id"] for a in res.json()]
    assert article["id"] in ids


def test_draft_article_never_suggested(agent_client: TestClient, login_ticket: dict):
    draft = agent_client.post(
        "/api/kb/articles",
        json={"slug": "draft-login", "title": "Cannot log in draft help", "body": "x", "kind": "help"},
    ).json()
    published = _publish_article(agent_client, slug="published-login", title="Cannot log in guide")

    res = agent_client.get(f"/api/tickets/{login_ticket['id']}/ai/suggested-solutions")
    ids = [a["id"] for a in res.json()]
    assert published["id"] in ids
    assert draft["id"] not in ids


def test_empty_kb_returns_empty_list(agent_client: TestClient, login_ticket: dict):
    res = agent_client.get(f"/api/tickets/{login_ticket['id']}/ai/suggested-solutions")
    assert res.status_code == 200
    assert res.json() == []


def test_short_subject_skips_search(client: TestClient, agent_client: TestClient, customer: dict):
    _publish_article(agent_client, slug="hi-article", title="Hi there help article")
    ticket = client.post(
        "/api/tickets", json={"customer_id": customer["id"], "subject": "Hi", "description": ""}
    ).json()
    res = agent_client.get(f"/api/tickets/{ticket['id']}/ai/suggested-solutions")
    assert res.status_code == 200
    assert res.json() == []


def test_limit_is_respected(agent_client: TestClient, login_ticket: dict):
    for i in range(7):
        _publish_article(agent_client, slug=f"login-article-{i}", title=f"Cannot log in help {i}")
    res = agent_client.get(f"/api/tickets/{login_ticket['id']}/ai/suggested-solutions?limit=3")
    assert len(res.json()) <= 3

    res_default = agent_client.get(f"/api/tickets/{login_ticket['id']}/ai/suggested-solutions")
    assert len(res_default.json()) <= 5


def test_stub_provider_reranking(
    agent_client: TestClient, login_ticket: dict, monkeypatch: pytest.MonkeyPatch
):
    a1 = _publish_article(agent_client, slug="login-a", title="Cannot log in help A")
    a2 = _publish_article(agent_client, slug="login-b", title="Cannot log in help B")

    class ReorderProvider:
        slug = "reorder"

        def suggest_solutions(self, *, ticket_subject, ticket_description, candidates, limit):
            # Reverse whatever order the DB search produced.
            return [c["id"] for c in reversed(candidates)][:limit]

    monkeypatch.setattr(ai_provider, "get_ai_provider", lambda: ReorderProvider())

    res = agent_client.get(f"/api/tickets/{login_ticket['id']}/ai/suggested-solutions")
    ids = [a["id"] for a in res.json()]
    assert set(ids) == {a1["id"], a2["id"]}


def test_provider_hallucinated_id_is_filtered(
    agent_client: TestClient, login_ticket: dict, monkeypatch: pytest.MonkeyPatch
):
    _publish_article(agent_client, slug="login-real", title="Cannot log in help")

    class HallucinatingProvider:
        slug = "hallucinate"

        def suggest_solutions(self, *, ticket_subject, ticket_description, candidates, limit):
            import uuid

            return [str(uuid.uuid4())]

    monkeypatch.setattr(ai_provider, "get_ai_provider", lambda: HallucinatingProvider())

    res = agent_client.get(f"/api/tickets/{login_ticket['id']}/ai/suggested-solutions")
    assert res.status_code == 200
    assert len(res.json()) == 1


def test_provider_error_falls_back_gracefully(
    agent_client: TestClient, login_ticket: dict, monkeypatch: pytest.MonkeyPatch
):
    _publish_article(agent_client, slug="login-real2", title="Cannot log in help")

    class FailingProvider:
        slug = "failing"

        def suggest_solutions(self, **kwargs):
            from app.services.ai.provider import AIProviderError

            raise AIProviderError("boom")

    monkeypatch.setattr(ai_provider, "get_ai_provider", lambda: FailingProvider())

    res = agent_client.get(f"/api/tickets/{login_ticket['id']}/ai/suggested-solutions")
    assert res.status_code == 200
    assert len(res.json()) == 1


def test_requires_agent_auth(client: TestClient, login_ticket: dict):
    res = client.get(f"/api/tickets/{login_ticket['id']}/ai/suggested-solutions")
    assert res.status_code == 401


def test_unknown_ticket_returns_404(agent_client: TestClient):
    res = agent_client.get(f"/api/tickets/{missing_uuid()}/ai/suggested-solutions")
    assert res.status_code == 404
