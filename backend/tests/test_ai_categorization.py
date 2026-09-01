"""Story 11 -- automatic categorization."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services.ai import provider as ai_provider
from app.services.ai.categorization import suggest_category
from app.services.ai.provider import AIProviderError


def test_suggest_category_stores_stub_match(
    db: Session, ticket_category: dict, ticket: dict, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        ai_provider, "get_ai_provider", lambda: _fake_provider(ticket_category["id"])
    )
    result = suggest_category(db, uuid.UUID(ticket["id"]))
    assert result is not None
    assert str(result.id) == ticket_category["id"]


def test_suggest_category_short_circuits_with_no_categories(db: Session, ticket: dict):
    def spy_provider():
        raise AssertionError("provider should not be called with no categories")

    result = suggest_category(db, uuid.UUID(ticket["id"]))
    assert result is None


def test_create_ticket_succeeds_when_ai_provider_raises(
    client: TestClient, customer: dict, monkeypatch: pytest.MonkeyPatch
):
    def raising_provider():
        return _raising_provider()

    monkeypatch.setattr(ai_provider, "get_ai_provider", raising_provider)

    res = client.post(
        "/api/tickets",
        json={"customer_id": customer["id"], "subject": "Test", "description": ""},
    )
    assert res.status_code == 201
    assert res.json()["ai_suggested_category_id"] is None


def test_recompute_route_propagates_provider_failure(
    client: TestClient, ticket_category: dict, ticket: dict, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(ai_provider, "get_ai_provider", lambda: _raising_provider())
    res = client.post(f"/api/tickets/{ticket['id']}/ai/suggested-category")
    assert res.status_code == 502


def test_apply_suggestion_records_category_changed_and_clears_suggestion(
    client: TestClient, db: Session, ticket_category: dict, ticket: dict, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        ai_provider, "get_ai_provider", lambda: _fake_provider(ticket_category["id"])
    )
    suggest_category(db, uuid.UUID(ticket["id"]))
    db.commit()

    res = client.patch(f"/api/tickets/{ticket['id']}", json={"category_id": ticket_category["id"]})
    assert res.status_code == 200
    assert res.json()["ai_suggested_category_id"] is None

    events = client.get(f"/api/tickets/{ticket['id']}/events").json()["items"]
    assert any(e["event_type"] == "category_changed" for e in events)


def test_hallucinated_category_id_is_discarded(
    db: Session, ticket_category: dict, ticket: dict, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        ai_provider, "get_ai_provider", lambda: _fake_provider(str(uuid.uuid4()))
    )
    result = suggest_category(db, uuid.UUID(ticket["id"]))
    assert result is None


def test_manual_category_change_clears_stale_suggestion(
    client: TestClient, db: Session, ticket_category: dict, ticket: dict, monkeypatch: pytest.MonkeyPatch
):
    other = client.post(
        "/api/ticket-categories", json={"name": "Technical", "default_priority": "normal"}
    ).json()

    monkeypatch.setattr(
        ai_provider, "get_ai_provider", lambda: _fake_provider(ticket_category["id"])
    )
    suggest_category(db, uuid.UUID(ticket["id"]))
    db.commit()

    res = client.patch(f"/api/tickets/{ticket['id']}", json={"category_id": other["id"]})
    assert res.status_code == 200
    assert res.json()["ai_suggested_category_id"] is None


def _fake_provider(category_id: str):
    class FakeProvider:
        slug = "fake"

        def suggest_category(self, ticket, categories):
            return category_id

    return FakeProvider()


def _raising_provider():
    class FailingProvider:
        slug = "failing"

        def suggest_category(self, ticket, categories):
            raise AIProviderError("boom")

    return FailingProvider()
