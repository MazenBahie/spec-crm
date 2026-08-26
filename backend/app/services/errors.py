"""Service-layer exceptions, mapped to HTTP status codes by the route layer."""

from __future__ import annotations


class ServiceError(Exception):
    """Base class for expected, client-visible service failures."""


class NotFound(ServiceError):
    """Requested entity does not exist. Mapped to HTTP 404."""


class Conflict(ServiceError):
    """Request conflicts with current state. Mapped to HTTP 409."""


class Forbidden(ServiceError):
    """Caller is known but may not touch this row. Mapped to HTTP 403.

    Distinct from :class:`NotFound` on purpose: agent-scoped entities such as
    ``agent_tasks`` answer "that is not yours" rather than pretending the row
    does not exist, because both agents are trusted staff and hiding it would
    only make a mis-set ``X-Agent-Id`` harder to diagnose.
    """


class PayloadTooLarge(ServiceError):
    """Upload exceeds the configured limit. Mapped to HTTP 413."""
