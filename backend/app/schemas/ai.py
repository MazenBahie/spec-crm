"""Pydantic v2 schemas for AI-feature endpoints (stories 09-13)."""

from __future__ import annotations

from pydantic import BaseModel


class SuggestedReplyRead(BaseModel):
    draft: str
