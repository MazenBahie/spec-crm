"""AI-provider infrastructure errors.

Distinct from `app.services.errors.ServiceError` on purpose. Those are
request-validation failures the route layer maps straight to an HTTP status
(`NotFound` -> 404, `Conflict` -> 409, ...) via
`app.main.register_exception_handlers`. `AIProviderError` is an
integration/infrastructure failure -- a timeout, a rate limit, a bad or
revoked credential, a malformed or refused provider response -- and it is
NOT registered in `register_exception_handlers`. It must never reach a route
handler unhandled.

Contract for callers (Stories 09-13, since this story ships no caller of its
own): every `AIProvider` method raises this on failure instead of returning
a sentinel value, mirroring `ChannelDriver.send`'s own documented raise
semantics. No AI call may ever block or fail a synchronous request path that
does not need it -- see `app.services.channels.service.enqueue_outbound`
(`backend/app/services/channels/service.py:132-144`) for this codebase's
existing best-effort precedent: wrap the `AIProvider` call in
`try/except AIProviderError` (or a broader `except Exception`, since a
provider must never leak an un-wrapped SDK exception past this class, but a
defensive caller should not assume that guarantee is airtight) and degrade
to `StubAIProvider` output, a non-AI fallback, or a clean error response --
whichever the specific capability requires. A capability that is itself the
explicit, user-triggered action (e.g. an agent clicking "Regenerate summary")
may instead let `AIProviderError` propagate to a clean 5xx, since failure is
exactly what that caller needs to be told; that is a per-story judgment call,
not a rule enforced here.
"""

from __future__ import annotations


class AIProviderError(Exception):
    """Raised by an `AIProvider` implementation when it cannot produce an answer.

    Covers timeouts, rate limits, invalid/revoked credentials, and malformed
    or refused provider responses alike -- callers should not need to
    distinguish the cause to implement the required best-effort fallback.
    """
