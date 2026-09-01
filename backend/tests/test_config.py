"""Settings tests -- first config test file in the suite (Story 08)."""

from __future__ import annotations

import pytest

from app.core.config import Settings


def test_settings_read_ai_env_vars(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CRM_ANTHROPIC_API_KEY", "sk-test-123")
    monkeypatch.setenv("CRM_AI_MODEL", "claude-haiku-4-5")
    monkeypatch.setenv("CRM_AI_ENABLED", "true")

    fresh = Settings()

    assert fresh.anthropic_api_key == "sk-test-123"
    assert fresh.ai_model == "claude-haiku-4-5"
    assert fresh.ai_enabled is True


def test_settings_ai_defaults(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CRM_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CRM_AI_MODEL", raising=False)
    monkeypatch.delenv("CRM_AI_ENABLED", raising=False)

    fresh = Settings()

    assert fresh.anthropic_api_key is None
    assert fresh.ai_enabled is False
    assert isinstance(fresh.ai_model, str) and fresh.ai_model
