from typing import Literal

from fastapi import APIRouter, status
from sqlalchemy import select

from app.db.models import BusinessInfoDocument
from app.deps import CurrentUserDep, SessionDep
from app.merchants.constants import BUSINESS_INFO_SOURCES
from app.merchants.schemas import BusinessInfoOut, BusinessInfoUpdate

router = APIRouter(prefix="/business-info", tags=["business-info"])

InfoSource = Literal["about", "policies", "faq"]


@router.get("", response_model=list[BusinessInfoOut])
async def get_business_info(user: CurrentUserDep, session: SessionDep) -> list[BusinessInfoOut]:
    """Always returns all three sources; missing documents come back with empty content."""
    rows = {
        row.source: row
        for row in await session.scalars(
            select(BusinessInfoDocument).where(BusinessInfoDocument.merchant_id == user.merchant_id)
        )
    }
    return [
        BusinessInfoOut(
            source=source,
            content=rows[source].content if source in rows else "",
            updated_at=rows[source].updated_at if source in rows else None,
        )
        for source in BUSINESS_INFO_SOURCES
    ]


@router.put("/{source}", response_model=BusinessInfoOut, status_code=status.HTTP_200_OK)
async def put_business_info(
    source: InfoSource,
    payload: BusinessInfoUpdate,
    user: CurrentUserDep,
    session: SessionDep,
) -> BusinessInfoDocument:
    """Upsert one markdown document. Reindexing (chunk + embed) is wired in Phase 1 AI."""
    document = await session.scalar(
        select(BusinessInfoDocument).where(
            BusinessInfoDocument.merchant_id == user.merchant_id,
            BusinessInfoDocument.source == source,
        )
    )
    if document is None:
        document = BusinessInfoDocument(
            merchant_id=user.merchant_id, source=source, content=payload.content
        )
        session.add(document)
    else:
        document.content = payload.content
    await session.commit()
    await session.refresh(document)
    return document
