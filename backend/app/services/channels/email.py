"""Email channel driver — stub.

Story 21 replaces this with SMTP send plus IMAP/webhook inbound parsing
(MIME decoding, quoted-reply stripping, threading by ``Message-ID``).
"""

from __future__ import annotations

from typing import ClassVar

from app.services.channels.driver import StubDriver


class EmailDriver(StubDriver):
    slug: ClassVar[str] = "email"
