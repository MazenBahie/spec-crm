"""Live-chat channel driver — stub.

Story 23 replaces this with the websocket session transport that binds a
browser chat session to a ticket. Agent presence and typing indicators stay out
of scope there too.
"""

from __future__ import annotations

from typing import ClassVar

from app.services.channels.driver import StubDriver


class LiveChatDriver(StubDriver):
    slug: ClassVar[str] = "live_chat"
