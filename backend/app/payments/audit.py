import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PaymentAction


async def record_action(
    session: AsyncSession,
    *,
    merchant_id: uuid.UUID,
    order_id: uuid.UUID,
    action: str,
    trigger: str,
    amount: Decimal | None = None,
    result: str = "success",
    detail: dict | None = None,
) -> PaymentAction:
    """Add an audit row. The caller owns the commit."""
    entry = PaymentAction(
        merchant_id=merchant_id,
        order_id=order_id,
        action=action,
        trigger=trigger,
        amount=amount,
        result=result,
        detail=detail or {},
    )
    session.add(entry)
    return entry
