"""Service-layer exceptions, mapped to HTTP status codes by the route layer."""

from __future__ import annotations


class ServiceError(Exception):
    """Base class for expected, client-visible service failures."""


class NotFound(ServiceError):
    """Requested entity does not exist. Mapped to HTTP 404."""


class Conflict(ServiceError):
    """Request conflicts with current state. Mapped to HTTP 409."""


class PayloadTooLarge(ServiceError):
    """Upload exceeds the configured limit. Mapped to HTTP 413."""
