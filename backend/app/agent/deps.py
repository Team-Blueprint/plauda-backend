from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation, Merchant
from app.rag.embedders.base import EmbeddingProvider


@dataclass
class AgentDeps:
    """Everything a tool needs for one merchant turn."""

    session: AsyncSession
    merchant: Merchant
    conversation: Conversation
    embedding_provider: EmbeddingProvider | None = None
