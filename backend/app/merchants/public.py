from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.db.models import Merchant
from app.deps import SessionDep
from app.merchants.schemas import PublicMetaOut
from app.merchants.settings import _chat_link

router = APIRouter(prefix="/public/chat", tags=["public"])


@router.get("/{slug}/meta", response_model=PublicMetaOut)
async def public_store_meta(slug: str, session: SessionDep) -> PublicMetaOut:
    merchant = await session.scalar(select(Merchant).where(Merchant.slug == slug))
    if merchant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")
    return PublicMetaOut(
        name=merchant.name,
        slug=merchant.slug,
        currency=merchant.currency,
        chat_link=_chat_link(merchant.slug),
    )
