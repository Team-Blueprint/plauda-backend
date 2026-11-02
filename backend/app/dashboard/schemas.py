import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

AuditAction = Literal["create_link", "refund", "mark_paid", "receipt", "expire"]
AuditTrigger = Literal["agent", "webhook", "staff", "system"]
AuditResult = Literal["success", "declined", "ignored", "failed"]


class DashboardSummaryOut(BaseModel):
    as_of: datetime
    day_start: datetime
    currency: str
    revenue_today: Decimal
    orders_today: int
    paid_orders_today: int
    pending_payment_orders: int
    live_chats: int
    handoff_requests: int
    total_revenue: Decimal
    total_orders: int


class PaymentActionOut(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    order_status: str
    currency: str
    action: AuditAction
    trigger: AuditTrigger
    amount: Decimal | None
    result: AuditResult
    detail: dict
    created_at: datetime


class AuditListOut(BaseModel):
    items: list[PaymentActionOut]
    total: int
    limit: int
    offset: int
