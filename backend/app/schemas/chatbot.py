"""Pydantic v2 schemas for the AI-chatbot endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatbotSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    portal_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ChatbotMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class ChatbotMessageCreate(BaseModel):
    # 4000 chars is a generous chat-turn ceiling with no basis in a real
    # provider limit -- it exists only so one pathological paste can't blow
    # up the context this story builds on every turn.
    content: str = Field(min_length=1, max_length=4000)


class ChatTurnRead(BaseModel):
    """The response to sending one message: both halves of the turn.

    Returning both (not just the assistant reply) means the frontend never
    has to guess the server-assigned id/timestamp of the message it just
    sent -- it renders exactly what was persisted.
    """

    user_message: ChatbotMessageRead
    assistant_message: ChatbotMessageRead
