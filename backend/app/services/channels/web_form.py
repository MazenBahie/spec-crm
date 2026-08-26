"""Web-form channel driver — stub.

Story 25 replaces ``parse_inbound`` with the public submission endpoint's field
mapping. ``send`` will keep raising even then: a web form is inbound-only, so
there is nowhere to send a reply — an agent answers on another channel.
"""

from __future__ import annotations

from typing import ClassVar

from app.services.channels.driver import StubDriver


class WebFormDriver(StubDriver):
    slug: ClassVar[str] = "web_form"
