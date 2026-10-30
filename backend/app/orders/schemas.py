import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

OrderStatus = Literal[
    "draft",
    "confirmed",
    "pending_payment",
    "paid",
    "fulfilled",
    "cancelled",
    "expired",
]


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID | None
    variant_id: uuid.UUID | None
    name_snapshot: str
    variant_snapshot: dict | None
    qty: int
    unit_price: Decimal
    line_total: Decimal


class OrderSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    currency: str
    total: Decimal | None
    item_count: int
    created_at: datetime
    updated_at: datetime


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID | None
    customer_id: uuid.UUID | None
    status: str
    currency: str
    subtotal: Decimal | None
    delivery_fee: Decimal | None
    total: Decimal | None
    delivery_details: dict | None
    paypal_order_id: str | None
    approval_link: str | None
    reminder_count: int
    paid_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemOut]


class OrderListOut(BaseModel):
    items: list[OrderSummaryOut]
    total: int
    limit: int
    offset: int
