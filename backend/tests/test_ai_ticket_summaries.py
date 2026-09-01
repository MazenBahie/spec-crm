"""Story 09 -- AI ticket summaries."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services.ai import provider as ai_provider
from app.services.ai.provider import AIProviderError
from app.services.ai.ticket_summary import generate_summary
from tests.conftest import missing_uuid


def test_generate_summary_with_stub_provider(db: Session, ticket: dict):
    """No monkeypatch: get_ai_provider() already returns StubAIProvider by
    default in the test environment."""
    updated = generate_summary(db, uuid.UUID(ticket["id"]))
    assert updated.ai_summary
    assert updated.ai_summary_generated_at is not None


def test_route_requires_agent_auth(client: TestClient, agent_client: TestClient, ticket: dict):
    res = client.post(f"/api/tickets/{ticket['id']}/ai/summary")
    assert res.status_code == 401

    res = agent_client.post(f"/api/tickets/{ticket['id']}/ai/summary")
    assert res.status_code == 200
    body = res.json()
    assert body["ai_summary"]
    assert body["ai_summary_generated_at"]


def test_event_history_records_generation(agent_client: TestClient, ticket: dict):
    agent_client.post(f"/api/tickets/{ticket['id']}/ai/summary")
    events = agent_client.get(f"/api/tickets/{ticket['id']}/events").json()["items"]
    matches = [e for e in events if e["event_type"] == "ai_summary_generated"]
    assert len(matches) == 1


def test_empty_thread_still_succeeds(agent_client: TestClient, ticket: dict):
    res = agent_client.post(f"/api/tickets/{ticket['id']}/ai/summary")
    assert res.status_code == 200


def test_provider_failure_returns_502(
    agent_client: TestClient, ticket: dict, monkeypatch: pytest.MonkeyPatch
):
    class FailingProvider:
        slug = "failing"

        def summarize_ticket(self, ticket, messages):
            raise AIProviderError("boom")

    monkeypatch.setattr(ai_provider, "get_ai_provider", lambda: FailingProvider())

    res = agent_client.post(f"/api/tickets/{ticket['id']}/ai/summary")
    assert res.status_code == 502
    assert "detail" in res.json()


def test_unknown_ticket_returns_404(agent_client: TestClient):
    res = agent_client.post(f"/api/tickets/{missing_uuid()}/ai/summary")
    assert res.status_code == 404
