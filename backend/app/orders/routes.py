import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.db.models import Order
from app.deps import CurrentUserDep, SessionDep
from app.orders import service
from app.orders.schemas import OrderListOut, OrderOut, OrderStatus

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_model=OrderListOut)
async def list_orders(
    user: CurrentUserDep,
    session: SessionDep,
    status_filter: Annotated[OrderStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OrderListOut:
    conditions = [Order.merchant_id == user.merchant_id]
    if status_filter is not None:
        conditions.append(Order.status == status_filter)

    total = await session.scalar(select(func.count(Order.id)).where(*conditions))
    rows = await session.scalars(
        select(Order)
        .where(*conditions)
        .order_by(Order.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return OrderListOut(items=list(rows), total=total or 0, limit=limit, offset=offset)


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(order_id: uuid.UUID, user: CurrentUserDep, session: SessionDep) -> Order:
    return await service.get_order(session, user.merchant_id, order_id)


@router.post("/{order_id}/cancel", response_model=OrderOut)
async def cancel_order(order_id: uuid.UUID, user: CurrentUserDep, session: SessionDep) -> Order:
    order = await service.get_order(session, user.merchant_id, order_id)
    return await service.cancel_order(session, order)


@router.post("/{order_id}/fulfill", response_model=OrderOut)
async def fulfill_order(order_id: uuid.UUID, user: CurrentUserDep, session: SessionDep) -> Order:
    order = await service.get_order(session, user.merchant_id, order_id)
    return await service.fulfill_order(session, order)
