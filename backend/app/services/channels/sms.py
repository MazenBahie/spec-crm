"""SMS channel driver — stub.

Story 24 replaces this with the SMS gateway integration, including multipart
concatenation for bodies past the single-segment limit.
"""

from __future__ import annotations

from typing import ClassVar

from app.services.channels.driver import StubDriver


class SmsDriver(StubDriver):
    slug: ClassVar[str] = "sms"
