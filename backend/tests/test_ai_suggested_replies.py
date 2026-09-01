"""Story 10 -- suggested replies. No persistence, never auto-sent."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services.ai import provider as ai_provider
from app.services.ai.provider import AIProviderError
from app.services.ai.suggested_replies import suggest_reply
from tests.conftest import missing_uuid


def test_service_returns_nonempty_string_with_stub(db: Session, ticket: dict):
    draft = suggest_reply(db, uuid.UUID(ticket["id"]))
    assert isinstance(draft, str) and draft


def test_service_falls_back_to_stub_on_provider_error(
    db: Session, ticket: dict, monkeypatch: pytest.MonkeyPatch
):
    class FailingProvider:
        slug = "failing"

        def suggest_reply(self, ticket, messages):
            raise AIProviderError("boom")

    monkeypatch.setattr(ai_provider, "get_ai_provider", lambda: FailingProvider())
    draft = suggest_reply(db, uuid.UUID(ticket["id"]))
    assert isinstance(draft, str) and draft


def test_route_happy_path(agent_client: TestClient, ticket: dict):
    res = agent_client.post(f"/api/tickets/{ticket['id']}/ai/suggested-reply")
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body["draft"], str) and body["draft"]


def test_route_unknown_ticket_404(agent_client: TestClient):
    res = agent_client.post(f"/api/tickets/{missing_uuid()}/ai/suggested-reply")
    assert res.status_code == 404


def test_route_unauthenticated_401(client: TestClient, ticket: dict):
    res = client.post(f"/api/tickets/{ticket['id']}/ai/suggested-reply")
    assert res.status_code == 401


def test_no_side_effects(agent_client: TestClient, ticket: dict):
    before_events = agent_client.get(f"/api/tickets/{ticket['id']}/events").json()["total"]
    before_messages = agent_client.get(f"/api/tickets/{ticket['id']}/messages").json()["total"]

    agent_client.post(f"/api/tickets/{ticket['id']}/ai/suggested-reply")

    after_events = agent_client.get(f"/api/tickets/{ticket['id']}/events").json()["total"]
    after_messages = agent_client.get(f"/api/tickets/{ticket['id']}/messages").json()["total"]

    assert before_events == after_events
    assert before_messages == after_messages
