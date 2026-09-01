"""AI integration layer: the `AIProvider` Protocol, its Anthropic-backed and
stub implementations, and the `get_ai_provider()` factory that selects
between them based on `Settings.ai_enabled` / `Settings.anthropic_api_key`.

Deliberately empty of re-exports at the package root. Unlike
`app.services.channels` (whose own `__init__.py` explains a real circular-
import hazard: `service` -> `registry` -> every driver module), there is no
such hazard here -- `stub_provider.py` and `anthropic_provider.py` do not
import `provider.py` -- but the convention in this codebase is still to
import what you need directly:

    from app.services.ai import provider as ai_provider
    from app.services.ai.provider import AIProvider, get_ai_provider
    from app.services.ai.errors import AIProviderError

Importing the *module* rather than a bare name matters for tests that
monkeypatch `get_ai_provider` -- see `provider.py`'s docstring.
"""
