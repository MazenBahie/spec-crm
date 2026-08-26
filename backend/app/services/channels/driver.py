"""The contract every channel adapter implements.

Transport lives behind this interface so the service layer never imports a
provider SDK, and so stories 21-25 can each replace one stub without touching
anything outside this package.

A driver is stateless and holds no session: it is handed a ``ChannelMessage``
to send, or a payload to parse, and answers with a plain value object. Writing
the outcome back to the row is the service's job, not the driver's.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar, Protocol, runtime_checkable

from app.models.channel import ChannelMessage


@dataclass(frozen=True)
class SendResult:
    """What a driver reports after handing a message to its provider.

    ``status`` is ``sent`` when the provider has accepted the message but not
    yet confirmed delivery, and ``delivered`` when it has. A driver that fails
    raises instead of returning a failed result — see ``ChannelDriver.send``.
    """

    status: str = "sent"
    provider_message_id: str | None = None


@dataclass(frozen=True)
class ParsedInbound:
    """The channel-agnostic core of an inbound provider payload."""

    body: str
    provider_message_id: str | None = None


@runtime_checkable
class ChannelDriver(Protocol):
    slug: ClassVar[str]

    def send(self, message: ChannelMessage) -> SendResult:
        """Hand ``message`` to the provider.

        Raises on failure — anything short of "the provider took it" is an
        exception, which the service records as ``status='failed'`` plus an
        ``error_reason``. Must not mutate ``message``.
        """
        ...

    def parse_inbound(self, payload: Mapping[str, Any]) -> ParsedInbound:
        """Pull the message text out of a provider webhook body.

        Raises ``ValueError`` when the payload carries no usable message; the
        service turns that into a client-visible 409.
        """
        ...


class StubDriver:
    """Base for a channel whose transport has not been built yet.

    ``send`` raises, so an outbound message on a stubbed channel is persisted
    as ``failed`` with a readable reason rather than silently vanishing —
    that is the expected state until the channel's own story lands.

    ``parse_inbound`` *is* implemented: inbound ingestion is testable without a
    provider, and reading ``body`` off the payload is what a caller posting
    directly to the webhook endpoint would send anyway.
    """

    slug: ClassVar[str] = ""

    def send(self, message: ChannelMessage) -> SendResult:
        raise NotImplementedError(f"channel driver {self.slug!r} is not implemented yet")

    def parse_inbound(self, payload: Mapping[str, Any]) -> ParsedInbound:
        body = payload.get("body")
        if not isinstance(body, str) or not body.strip():
            raise ValueError(
                f"inbound {self.slug!r} payload carries no message body"
            )
        provider_message_id = payload.get("provider_message_id")
        return ParsedInbound(
            body=body,
            provider_message_id=(
                None if provider_message_id is None else str(provider_message_id)
            ),
        )
