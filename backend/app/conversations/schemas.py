import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ConversationStatus = Literal["ai", "handoff_requested", "human_active", "closed"]


class ConversationCreate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    contact: str | None = Field(default=None, max_length=320)


class ConversationCreatedOut(BaseModel):
    conversation_id: uuid.UUID
    visitor_token: str
    status: str
    started_at: datetime


class HandoffIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    meta: dict
    created_at: datetime


class MessageListOut(BaseModel):
    items: list[MessageOut]
    total: int
    limit: int
    offset: int


class ConversationSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    channel: str
    customer_name: str | None
    customer_contact: str | None
    handoff_reason: str | None
    last_message_at: datetime | None
    started_at: datetime


class ConversationListOut(BaseModel):
    items: list[ConversationSummaryOut]
    total: int
    limit: int
    offset: int


class ConversationOut(ConversationSummaryOut):
    customer_id: uuid.UUID | None
    summary: str | None
    latest_order_id: uuid.UUID | None = None


class VisitorMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=10_000)


class StaffMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=10_000)
