"""Strongly-typed request and response models for the Plauda APIMatic Python SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class OrderStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ConversationStatus(StrEnum):
    AI = "ai"
    HANDOFF_REQUESTED = "handoff_requested"
    HUMAN_ACTIVE = "human_active"
    CLOSED = "closed"


class BusinessInfoSource(StrEnum):
    ABOUT = "about"
    POLICIES = "policies"
    FAQ = "faq"


@dataclass(slots=True)
class HealthResponse:
    status: str
    db: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HealthResponse:
        return cls(status=str(data.get("status", "")), db=str(data.get("db", "")))


@dataclass(slots=True)
class RegisterRequest:
    email: str
    password: str
    business_name: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "email": self.email,
            "password": self.password,
            "business_name": self.business_name,
        }


@dataclass(slots=True)
class LoginRequest:
    email: str
    password: str

    def to_dict(self) -> dict[str, Any]:
        return {"email": self.email, "password": self.password}


@dataclass(slots=True)
class TokenResponse:
    access_token: str
    token_type: str
    merchant_id: str | None = None
    merchant_slug: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TokenResponse:
        merchant = data.get("merchant") or {}
        return cls(
            access_token=str(data["access_token"]),
            token_type=str(data.get("token_type", "bearer")),
            merchant_id=merchant.get("id") or data.get("merchant_id"),
            merchant_slug=merchant.get("slug") or data.get("slug"),
        )


@dataclass(slots=True)
class VariantCreateRequest:
    name: str
    price: str
    stock: int
    sku: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "price": self.price,
            "stock": self.stock,
        }
        if self.sku is not None:
            payload["sku"] = self.sku
        return payload


@dataclass(slots=True)
class ProductVariant:
    id: str
    name: str
    price: str
    stock: int
    sku: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProductVariant:
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            price=str(data["price"]),
            stock=int(data.get("stock", 0)),
            sku=data.get("sku"),
        )


@dataclass(slots=True)
class ProductCreateRequest:
    name: str
    description: str | None = None
    variants: list[VariantCreateRequest] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "variants": [v.to_dict() for v in self.variants],
        }


@dataclass(slots=True)
class Product:
    id: str
    name: str
    description: str | None
    variants: list[ProductVariant]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Product:
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            description=data.get("description"),
            variants=[ProductVariant.from_dict(v) for v in data.get("variants", [])],
        )


@dataclass(slots=True)
class DeliveryZoneCreateRequest:
    name: str
    fee: str
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "fee": self.fee, "description": self.description}


@dataclass(slots=True)
class DeliveryZone:
    id: str
    name: str
    fee: str
    description: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeliveryZone:
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            fee=str(data["fee"]),
            description=data.get("description"),
        )


@dataclass(slots=True)
class PublicStoreMeta:
    business_name: str
    slug: str
    currency: str
    chat_link: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PublicStoreMeta:
        return cls(
            business_name=str(data.get("business_name", "")),
            slug=str(data.get("slug", "")),
            currency=str(data.get("currency", "USD")),
            chat_link=data.get("chat_link"),
        )


@dataclass(slots=True)
class CreateConversationResponse:
    conversation_id: str
    visitor_token: str
    status: ConversationStatus

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CreateConversationResponse:
        conv = data.get("conversation") or {}
        conv_id = data.get("conversation_id") or conv.get("id") or data.get("id", "")
        raw_status = data.get("status") or conv.get("status") or "ai"
        return cls(
            conversation_id=str(conv_id),
            visitor_token=str(data.get("visitor_token", "")),
            status=ConversationStatus(raw_status),
        )


@dataclass(slots=True)
class ChatTurnRequest:
    conversation_id: str
    content: str

    def to_dict(self) -> dict[str, Any]:
        return {"conversation_id": self.conversation_id, "content": self.content}


@dataclass(slots=True)
class MessageRecord:
    id: str
    role: str
    content: str
    created_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MessageRecord:
        return cls(
            id=str(data.get("id", "")),
            role=str(data.get("role", "")),
            content=str(data.get("content", "")),
            created_at=data.get("created_at"),
        )


@dataclass(slots=True)
class ConversationDetail:
    id: str
    status: ConversationStatus
    handoff_reason: str | None = None
    visitor_name: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConversationDetail:
        return cls(
            id=str(data["id"]),
            status=ConversationStatus(data.get("status", "ai")),
            handoff_reason=data.get("handoff_reason"),
            visitor_name=data.get("visitor_name"),
        )


@dataclass(slots=True)
class OrderItemRecord:
    id: str
    variant_id: str
    product_name: str
    variant_name: str
    quantity: int
    unit_price: str
    line_total: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrderItemRecord:
        return cls(
            id=str(data.get("id", "")),
            variant_id=str(data.get("variant_id", "")),
            product_name=str(data.get("product_name", "")),
            variant_name=str(data.get("variant_name", "")),
            quantity=int(data.get("quantity", 1)),
            unit_price=str(data.get("unit_price", "0.00")),
            line_total=str(data.get("line_total", "0.00")),
        )


@dataclass(slots=True)
class OrderRecord:
    id: str
    status: OrderStatus
    currency: str
    subtotal: str
    delivery_fee: str
    total: str
    paypal_approval_url: str | None = None
    items: list[OrderItemRecord] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrderRecord:
        return cls(
            id=str(data["id"]),
            status=OrderStatus(data.get("status", "draft")),
            currency=str(data.get("currency", "USD")),
            subtotal=str(data.get("subtotal", "0.00")),
            delivery_fee=str(data.get("delivery_fee", "0.00")),
            total=str(data.get("total", "0.00")),
            paypal_approval_url=data.get("paypal_approval_url") or data.get("approval_url"),
            items=[OrderItemRecord.from_dict(i) for i in data.get("items", [])],
        )


@dataclass(slots=True)
class CreateOrderPaymentLinkResponse:
    order_id: str
    paypal_order_id: str
    approval_url: str
    status: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CreateOrderPaymentLinkResponse:
        return cls(
            order_id=str(data.get("order_id", "")),
            paypal_order_id=str(data.get("paypal_order_id", "")),
            approval_url=str(data.get("approval_url", "")),
            status=str(data.get("status", "")),
        )


@dataclass(slots=True)
class PayPalConnectRequest:
    client_id: str
    client_secret: str
    webhook_id: str | None = None
    sandbox: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "sandbox": self.sandbox,
        }
        if self.webhook_id:
            payload["webhook_id"] = self.webhook_id
        return payload


@dataclass(slots=True)
class PayPalStatusResponse:
    connected: bool
    sandbox: bool
    webhook_configured: bool

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PayPalStatusResponse:
        return cls(
            connected=bool(data.get("connected", False)),
            sandbox=bool(data.get("sandbox", True)),
            webhook_configured=bool(data.get("webhook_configured", False)),
        )


@dataclass(slots=True)
class DashboardSummary:
    today_revenue: str
    currency: str
    paid_orders_count: int
    pending_orders_count: int
    active_conversations_count: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DashboardSummary:
        return cls(
            today_revenue=str(data.get("today_revenue", "0.00")),
            currency=str(data.get("currency", "USD")),
            paid_orders_count=int(data.get("paid_orders_count", 0)),
            pending_orders_count=int(data.get("pending_orders_count", 0)),
            active_conversations_count=int(data.get("active_conversations_count", 0)),
        )


@dataclass(slots=True)
class AuditItem:
    id: str
    action: str
    trigger: str
    status: str
    amount: str | None = None
    currency: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditItem:
        return cls(
            id=str(data.get("id", "")),
            action=str(data.get("action", "")),
            trigger=str(data.get("trigger", "")),
            status=str(data.get("status", "")),
            amount=str(data["amount"]) if data.get("amount") is not None else None,
            currency=data.get("currency"),
        )
