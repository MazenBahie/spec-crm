"""Slug → driver lookup, built once at import time.

Every catalogue slug in ``app.models.channel.CHANNEL_CATALOGUE`` must appear
here; the check at the bottom fails the import rather than letting a channel
exist in the database with no transport behind it.
"""

from __future__ import annotations

from app.models.channel import CHANNEL_SLUGS
from app.services.channels.driver import ChannelDriver
from app.services.channels.email import EmailDriver
from app.services.channels.live_chat import LiveChatDriver
from app.services.channels.sms import SmsDriver
from app.services.channels.web_form import WebFormDriver
from app.services.channels.whatsapp import WhatsAppDriver
from app.services.errors import NotFound

DRIVERS: dict[str, ChannelDriver] = {
    driver.slug: driver
    for driver in (
        EmailDriver(),
        WhatsAppDriver(),
        LiveChatDriver(),
        SmsDriver(),
        WebFormDriver(),
    )
}


def get_driver(slug: str) -> ChannelDriver:
    driver = DRIVERS.get(slug)
    if driver is None:
        raise NotFound(f"no driver registered for channel {slug!r}")
    return driver


def _assert_every_channel_has_a_driver() -> None:
    """A raise, not an assert: this guard must survive ``python -O``."""
    missing = set(CHANNEL_SLUGS) - set(DRIVERS)
    if missing:
        raise RuntimeError(f"channels with no registered driver: {sorted(missing)}")


_assert_every_channel_has_a_driver()
