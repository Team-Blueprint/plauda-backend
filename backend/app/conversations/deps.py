import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.tokens import token_matches
from app.db.models import Conversation
from app.db.session import get_session

_visitor_bearer = HTTPBearer(auto_error=False)


def bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token.strip()


async def get_visitor_conversation(
    conversation_id: uuid.UUID,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_visitor_bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Conversation:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Visitor token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    conversation = await session.scalar(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    if conversation is None or not token_matches(
        credentials.credentials, conversation.visitor_token_hash
    ):
        # Same response for missing and wrong tokens — no conversation enumeration.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conversation


VisitorConversationDep = Annotated[Conversation, Depends(get_visitor_conversation)]
