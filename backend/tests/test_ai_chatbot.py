"""Story 13 -- AI chatbot."""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.services.ai.provider import AIProviderError, StubAIProvider, get_ai_provider


def _second_customer_portal_client(app: FastAPI, session_factory: sessionmaker[Session]) -> TestClient:
    """Independent second portal identity, mirroring test_portal_tickets.py's helper."""
    with TestClient(app) as bootstrap:
        customer = bootstrap.post(
            "/api/customers", json={"display_name": "Second Co", "company": "Second"}
        ).json()
        contact = bootstrap.post(
            f"/api/customers/{customer['id']}/contacts",
            json={"kind": "email", "value": "second-owner@example.com", "is_primary": True},
        ).json()
        signup = bootstrap.post(
            "/api/portal/auth/signup",
            json={
                "email": contact["value"],
                "password": "hunter2pass",
                "display_name": "Second Owner",
            },
        ).json()
    return TestClient(app, headers={"Authorization": f"Bearer {signup['token']}"})


def test_session_get_or_create_is_idempotent(portal_client: TestClient):
    first = portal_client.post("/api/portal/chat/sessions")
    second = portal_client.post("/api/portal/chat/sessions")
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


def test_send_and_receive_round_trip_with_stub_provider(app: FastAPI, portal_client: TestClient):
    app.dependency_overrides[get_ai_provider] = lambda: StubAIProvider()
    try:
        session = portal_client.post("/api/portal/chat/sessions").json()
        res = portal_client.post(
            f"/api/portal/chat/sessions/{session['id']}/messages",
            json={"content": "How do I reset my password?"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["user_message"]["content"] == "How do I reset my password?"
        assert body["assistant_message"]["role"] == "assistant"

        messages = portal_client.get(f"/api/portal/chat/sessions/{session['id']}/messages").json()
        assert len(messages) == 2
    finally:
        app.dependency_overrides.pop(get_ai_provider, None)


def test_unauthenticated_requests_are_401(client: TestClient):
    res = client.post("/api/portal/chat/sessions")
    assert res.status_code == 401


def test_cross_user_session_access_is_404(
    app: FastAPI, session_factory: sessionmaker[Session], portal_client: TestClient
):
    session = portal_client.post("/api/portal/chat/sessions").json()

    other_client = _second_customer_portal_client(app, session_factory)
    with other_client:
        res = other_client.get(f"/api/portal/chat/sessions/{session['id']}/messages")
        assert res.status_code == 404

        res_post = other_client.post(
            f"/api/portal/chat/sessions/{session['id']}/messages", json={"content": "hi"}
        )
        assert res_post.status_code == 404


def test_rate_limit_returns_409(app: FastAPI, portal_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from app.services.ai import chatbot as chatbot_svc

    monkeypatch.setattr(chatbot_svc, "RATE_LIMIT_MAX_MESSAGES", 2)
    app.dependency_overrides[get_ai_provider] = lambda: StubAIProvider()
    try:
        session = portal_client.post("/api/portal/chat/sessions").json()
        for _ in range(2):
            res = portal_client.post(
                f"/api/portal/chat/sessions/{session['id']}/messages", json={"content": "hi"}
            )
            assert res.status_code == 200

        before = len(portal_client.get(f"/api/portal/chat/sessions/{session['id']}/messages").json())
        res = portal_client.post(
            f"/api/portal/chat/sessions/{session['id']}/messages", json={"content": "one more"}
        )
        assert res.status_code == 409
        after = len(portal_client.get(f"/api/portal/chat/sessions/{session['id']}/messages").json())
        assert after == before
    finally:
        app.dependency_overrides.pop(get_ai_provider, None)


def test_provider_error_degrades_to_clean_reply(app: FastAPI, portal_client: TestClient):
    class FailingProvider:
        slug = "failing"

        def chat(self, message, history, *, context=None):
            raise AIProviderError("boom")

    app.dependency_overrides[get_ai_provider] = lambda: FailingProvider()
    try:
        session = portal_client.post("/api/portal/chat/sessions").json()
        res = portal_client.post(
            f"/api/portal/chat/sessions/{session['id']}/messages", json={"content": "hello"}
        )
        assert res.status_code == 200
        body = res.json()
        assert "unavailable" in body["assistant_message"]["content"].lower()

        messages = portal_client.get(f"/api/portal/chat/sessions/{session['id']}/messages").json()
        assert any(m["content"] == "hello" for m in messages)
    finally:
        app.dependency_overrides.pop(get_ai_provider, None)


def test_malformed_session_id_is_422(portal_client: TestClient):
    res = portal_client.get("/api/portal/chat/sessions/not-a-uuid/messages")
    assert res.status_code == 422


def test_message_over_max_length_is_422(portal_client: TestClient):
    session = portal_client.post("/api/portal/chat/sessions").json()
    res = portal_client.post(
        f"/api/portal/chat/sessions/{session['id']}/messages",
        json={"content": "x" * 4001},
    )
    assert res.status_code == 422
