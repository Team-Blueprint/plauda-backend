import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DeliveryZone
from app.deps import CurrentUserDep, SessionDep
from app.merchants.schemas import ZoneCreate, ZoneOut, ZoneUpdate

router = APIRouter(prefix="/delivery-zones", tags=["delivery"])


async def _get_zone_or_404(
    session: AsyncSession, merchant_id: uuid.UUID, zone_id: uuid.UUID
) -> DeliveryZone:
    zone = await session.scalar(
        select(DeliveryZone).where(
            DeliveryZone.id == zone_id, DeliveryZone.merchant_id == merchant_id
        )
    )
    if zone is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery zone not found")
    return zone


@router.get("", response_model=list[ZoneOut])
async def list_zones(user: CurrentUserDep, session: SessionDep) -> list[DeliveryZone]:
    return list(
        await session.scalars(
            select(DeliveryZone)
            .where(DeliveryZone.merchant_id == user.merchant_id)
            .order_by(DeliveryZone.created_at)
        )
    )


@router.post("", response_model=ZoneOut, status_code=status.HTTP_201_CREATED)
async def create_zone(
    payload: ZoneCreate, user: CurrentUserDep, session: SessionDep
) -> DeliveryZone:
    zone = DeliveryZone(merchant_id=user.merchant_id, **payload.model_dump())
    session.add(zone)
    await session.commit()
    await session.refresh(zone)
    return zone


@router.get("/{zone_id}", response_model=ZoneOut)
async def get_zone(zone_id: uuid.UUID, user: CurrentUserDep, session: SessionDep) -> DeliveryZone:
    return await _get_zone_or_404(session, user.merchant_id, zone_id)


@router.patch("/{zone_id}", response_model=ZoneOut)
async def update_zone(
    zone_id: uuid.UUID,
    payload: ZoneUpdate,
    user: CurrentUserDep,
    session: SessionDep,
) -> DeliveryZone:
    zone = await _get_zone_or_404(session, user.merchant_id, zone_id)
    for field, value in payload.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(zone, field, value)
    await session.commit()
    await session.refresh(zone)
    return zone


@router.delete("/{zone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_zone(zone_id: uuid.UUID, user: CurrentUserDep, session: SessionDep) -> None:
    zone = await _get_zone_or_404(session, user.merchant_id, zone_id)
    await session.delete(zone)
    await session.commit()
