import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dashboard.schemas import AuditListOut, DashboardSummaryOut, PaymentActionOut
from app.db.models import Conversation, Merchant, Order, PaymentAction

CENT = Decimal("0.01")
PAID_STATUSES = ("paid", "fulfilled")
LIVE_CHAT_STATUSES = ("ai", "handoff_requested", "human_active")


def _money(value: Decimal | int | None) -> Decimal:
    return Decimal(value or 0).quantize(CENT)


async def summary(session: AsyncSession, merchant: Merchant) -> DashboardSummaryOut:
    now = datetime.now(UTC)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    order_row = (
        await session.execute(
            select(
                func.coalesce(
                    func.sum(Order.total).filter(
                        Order.status.in_(PAID_STATUSES),
                        Order.paid_at >= day_start,
                        Order.paid_at < day_end,
                    ),
                    0,
                ).label("revenue_today"),
                func.count(Order.id)
                .filter(Order.created_at >= day_start, Order.created_at < day_end)
                .label("orders_today"),
                func.count(Order.id)
                .filter(
                    Order.status.in_(PAID_STATUSES),
                    Order.paid_at >= day_start,
                    Order.paid_at < day_end,
                )
                .label("paid_orders_today"),
                func.count(Order.id)
                .filter(Order.status == "pending_payment")
                .label("pending_payment_orders"),
                func.coalesce(
                    func.sum(Order.total).filter(Order.status.in_(PAID_STATUSES)),
                    0,
                ).label("total_revenue"),
                func.count(Order.id).label("total_orders"),
            ).where(Order.merchant_id == merchant.id)
        )
    ).one()

    chat_row = (
        await session.execute(
            select(
                func.count(Conversation.id)
                .filter(Conversation.status.in_(LIVE_CHAT_STATUSES))
                .label("live_chats"),
                func.count(Conversation.id)
                .filter(Conversation.status == "handoff_requested")
                .label("handoff_requests"),
            ).where(Conversation.merchant_id == merchant.id)
        )
    ).one()

    return DashboardSummaryOut(
        as_of=now,
        day_start=day_start,
        currency=merchant.currency,
        revenue_today=_money(order_row.revenue_today),
        orders_today=order_row.orders_today,
        paid_orders_today=order_row.paid_orders_today,
        pending_payment_orders=order_row.pending_payment_orders,
        live_chats=chat_row.live_chats,
        handoff_requests=chat_row.handoff_requests,
        total_revenue=_money(order_row.total_revenue),
        total_orders=order_row.total_orders,
    )


async def list_audit(
    session: AsyncSession,
    merchant_id: uuid.UUID,
    *,
    order_id: uuid.UUID | None = None,
    action: str | None = None,
    trigger: str | None = None,
    result: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> AuditListOut:
    conditions = [PaymentAction.merchant_id == merchant_id]
    if order_id is not None:
        conditions.append(PaymentAction.order_id == order_id)
    if action is not None:
        conditions.append(PaymentAction.action == action)
    if trigger is not None:
        conditions.append(PaymentAction.trigger == trigger)
    if result is not None:
        conditions.append(PaymentAction.result == result)
    if since is not None:
        conditions.append(PaymentAction.created_at >= since)
    if until is not None:
        conditions.append(PaymentAction.created_at <= until)

    total = await session.scalar(select(func.count(PaymentAction.id)).where(*conditions))
    rows = (
        await session.execute(
            select(PaymentAction, Order.currency, Order.status)
            .join(
                Order,
                (Order.id == PaymentAction.order_id) & (Order.merchant_id == merchant_id),
            )
            .where(*conditions)
            .order_by(PaymentAction.created_at.desc(), PaymentAction.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()

    return AuditListOut(
        items=[
            PaymentActionOut(
                id=entry.id,
                order_id=entry.order_id,
                order_status=order_status,
                currency=currency,
                action=entry.action,
                trigger=entry.trigger,
                amount=entry.amount,
                result=entry.result,
                detail=entry.detail,
                created_at=entry.created_at,
            )
            for entry, currency, order_status in rows
        ],
        total=total or 0,
        limit=limit,
        offset=offset,
    )
