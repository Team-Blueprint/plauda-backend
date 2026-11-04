import uuid

from pydantic import BaseModel, Field


class ChatTurnIn(BaseModel):
    conversation_id: uuid.UUID
    content: str = Field(min_length=1, max_length=10_000)
