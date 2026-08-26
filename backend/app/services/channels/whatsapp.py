"""WhatsApp channel driver — stub.

Story 22 replaces this with the WhatsApp Business Cloud API: template messages
for outbound outside the 24-hour session window, and webhook signature
verification for inbound.
"""

from __future__ import annotations

from typing import ClassVar

from app.services.channels.driver import StubDriver


class WhatsAppDriver(StubDriver):
    slug: ClassVar[str] = "whatsapp"
