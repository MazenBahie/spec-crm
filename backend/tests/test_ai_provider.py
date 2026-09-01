"""Story 08 -- AI foundation: the Protocol, the stub, the factory, error wrapping."""

from __future__ import annotations

import uuid

import pytest

from app.core.config import settings
from app.models.channel import ChannelMessage
from app.models.ticket import Ticket, TicketCategory
from app.services.ai import provider as ai_provider
from app.services.ai.provider import AIProviderError, AnthropicProvider, StubAIProvider, get_ai_provider


def _ticket(**overrides) -> Ticket:
    defaults = dict(
        id=uuid.uuid4(),
        reference="TCK-DEADBEEF",
        customer_id=uuid.uuid4(),
        subject="Cannot log in",
        description="Password reset email never arrives.",
        status="open",
        priority="normal",
    )
    defaults.update(overrides)
    return Ticket(**defaults)


def _message(**overrides) -> ChannelMessage:
    defaults = dict(
        id=uuid.uuid4(),
        ticket_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        direction="inbound",
        status="received",
        body="Still broken.",
    )
    defaults.update(overrides)
    return ChannelMessage(**defaults)


def _category(**overrides) -> TicketCategory:
    defaults = dict(id=uuid.uuid4(), name="Billing", default_priority="normal")
    defaults.update(overrides)
    return TicketCategory(**defaults)


def test_stub_provider_deterministic():
    stub = StubAIProvider()
    ticket = _ticket()
    messages = [_message()]
    categories = [_category()]

    assert stub.summarize_ticket(ticket, messages) == stub.summarize_ticket(ticket, messages)
    assert stub.suggest_reply(ticket, messages) == stub.suggest_reply(ticket, messages)
    assert stub.suggest_category(ticket, categories) == stub.suggest_category(ticket, categories)
    assert stub.chat("hi", []) == stub.chat("hi", [])


def test_stub_provider_output_shapes():
    stub = StubAIProvider()
    ticket = _ticket()
    messages = [_message()]
    categories = [_category()]

    assert isinstance(stub.summarize_ticket(ticket, messages), str) and stub.summarize_ticket(ticket, messages)
    assert isinstance(stub.suggest_reply(ticket, messages), str) and stub.suggest_reply(ticket, messages)
    assert isinstance(stub.chat("hi", []), str) and stub.chat("hi", [])

    assert stub.suggest_category(ticket, categories) == str(categories[0].id)
    assert stub.suggest_category(ticket, []) is None

    candidates = [{"id": "a", "title": "t", "summary": "s"}, {"id": "b", "title": "t2", "summary": "s2"}]
    assert stub.suggest_solutions(
        ticket_subject="x", ticket_description="y", candidates=candidates, limit=1
    ) == ["a"]


def test_get_ai_provider_returns_stub_when_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "ai_enabled", False)
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test-would-be-real")
    assert isinstance(get_ai_provider(), StubAIProvider)


def test_get_ai_provider_returns_stub_when_no_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    assert isinstance(get_ai_provider(), StubAIProvider)


def test_get_ai_provider_returns_anthropic_when_configured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test-fake")
    provider = get_ai_provider()
    assert isinstance(provider, AnthropicProvider)


def test_module_import_survives_monkeypatch(monkeypatch: pytest.MonkeyPatch):
    """Proves the module-import test-override mechanism `provider.py` documents."""
    monkeypatch.setattr(ai_provider, "get_ai_provider", lambda: StubAIProvider())
    assert isinstance(ai_provider.get_ai_provider(), StubAIProvider)


def test_anthropic_provider_wraps_sdk_errors(monkeypatch: pytest.MonkeyPatch):
    provider = AnthropicProvider(api_key="fake", model="fake-model")

    def boom(**_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(provider._client.messages, "create", boom)

    with pytest.raises(AIProviderError):
        provider.summarize_ticket(_ticket(), [])

    with pytest.raises(AIProviderError):
        provider.suggest_reply(_ticket(), [])


def test_anthropic_provider_truncates_long_input(monkeypatch: pytest.MonkeyPatch):
    from app.services.ai.anthropic_provider import MAX_INPUT_CHARS

    provider = AnthropicProvider(api_key="fake", model="fake-model")
    captured = {}

    class FakeBlock:
        type = "text"
        text = "a summary"

    class FakeResponse:
        stop_reason = "end_turn"
        content = [FakeBlock()]

    def fake_create(**kwargs):
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(provider._client.messages, "create", fake_create)

    long_description = "x" * (MAX_INPUT_CHARS + 500) + "TAIL_MARKER"
    ticket = _ticket(description=long_description)
    provider.summarize_ticket(ticket, [])

    prompt = captured["messages"][0]["content"]
    assert "TAIL_MARKER" in prompt
    # The truncated description segment itself is capped, even though the
    # full assembled prompt (with labels/other sections) is longer.
    assert long_description not in prompt


def test_anthropic_provider_refusal_raises(monkeypatch: pytest.MonkeyPatch):
    provider = AnthropicProvider(api_key="fake", model="fake-model")

    class FakeResponse:
        stop_reason = "refusal"
        content = []

    monkeypatch.setattr(provider._client.messages, "create", lambda **_: FakeResponse())

    with pytest.raises(AIProviderError):
        provider.suggest_reply(_ticket(), [])
