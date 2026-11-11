"""Strongly-typed domain controllers for the Plauda APIMatic Python SDK."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

import httpx

from plauda_sdk.models import (
    AuditItem,
    BusinessInfoSource,
    ChatTurnRequest,
    ConversationDetail,
    CreateConversationResponse,
    CreateOrderPaymentLinkResponse,
    DashboardSummary,
    DeliveryZone,
    DeliveryZoneCreateRequest,
    HealthResponse,
    LoginRequest,
    MessageRecord,
    OrderRecord,
    PayPalConnectRequest,
    PayPalStatusResponse,
    Product,
    ProductCreateRequest,
    ProductVariant,
    PublicStoreMeta,
    RegisterRequest,
    TokenResponse,
    VariantCreateRequest,
)

if TYPE_CHECKING:
    from plauda_sdk.configuration import Configuration


class BaseController:
    """Base HTTP & auth handler with APIMatic retry semantics."""

    def __init__(self, config: Configuration, http_client: httpx.Client) -> None:
        self._config = config
        self._client = http_client

    def _merchant_headers(self) -> dict[str, str]:
        if not self._config.merchant_bearer_token:
            raise ValueError("merchant_bearer_token is required for merchant endpoints.")
        return {"Authorization": f"Bearer {self._config.merchant_bearer_token}"}

    def _visitor_headers(self, token_override: str | None = None) -> dict[str, str]:
        token = token_override or self._config.visitor_bearer_token
        if not token:
            raise ValueError("visitor_bearer_token is required for visitor endpoints.")
        return {"Authorization": f"Bearer {token}"}

    def _request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self._config.base_url}{path}"
        resp = self._client.request(
            method=method,
            url=url,
            headers=headers,
            json=json_body,
            params=params,
            timeout=self._config.timeout,
        )
        resp.raise_for_status()
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()


class SystemController(BaseController):
    """Controller for system & health endpoints."""

    def healthz(self) -> HealthResponse:
        data = self._request("GET", "/healthz")
        return HealthResponse.from_dict(data)


class AuthController(BaseController):
    """Controller for merchant registration, login, and profile."""

    def register(self, request: RegisterRequest) -> TokenResponse:
        data = self._request("POST", "/auth/register", json_body=request.to_dict())
        token_resp = TokenResponse.from_dict(data)
        self._config.merchant_bearer_token = token_resp.access_token
        return token_resp

    def login(self, request: LoginRequest) -> TokenResponse:
        data = self._request("POST", "/auth/login", json_body=request.to_dict())
        token_resp = TokenResponse.from_dict(data)
        self._config.merchant_bearer_token = token_resp.access_token
        return token_resp

    def me(self) -> dict[str, Any]:
        return self._request("GET", "/auth/me", headers=self._merchant_headers())


class CatalogueController(BaseController):
    """Controller for merchant products, variants, delivery zones, and RAG knowledge."""

    def list_products(self) -> list[Product]:
        data = self._request("GET", "/products", headers=self._merchant_headers())
        items = data.get("items", data) if isinstance(data, dict) else data
        return [Product.from_dict(item) for item in items]

    def create_product(self, request: ProductCreateRequest) -> Product:
        data = self._request(
            "POST",
            "/products",
            headers=self._merchant_headers(),
            json_body=request.to_dict(),
        )
        return Product.from_dict(data)

    def create_variant(self, product_id: str, request: VariantCreateRequest) -> ProductVariant:
        data = self._request(
            "POST",
            f"/products/{product_id}/variants",
            headers=self._merchant_headers(),
            json_body=request.to_dict(),
        )
        return ProductVariant.from_dict(data)

    def list_delivery_zones(self) -> list[DeliveryZone]:
        data = self._request("GET", "/delivery-zones", headers=self._merchant_headers())
        items = data.get("items", data) if isinstance(data, dict) else data
        return [DeliveryZone.from_dict(z) for z in items]

    def create_delivery_zone(self, request: DeliveryZoneCreateRequest) -> DeliveryZone:
        data = self._request(
            "POST",
            "/delivery-zones",
            headers=self._merchant_headers(),
            json_body=request.to_dict(),
        )
        return DeliveryZone.from_dict(data)

    def put_business_info(self, source: BusinessInfoSource, markdown: str) -> dict[str, Any]:
        return self._request(
            "PUT",
            f"/business-info/{source.value}",
            headers=self._merchant_headers(),
            json_body={"markdown": markdown},
        )


class PublicChatController(BaseController):
    """Controller for public customer chat, SSE AI agent turns, and human handoff."""

    def get_store_meta(self, slug: str) -> PublicStoreMeta:
        data = self._request("GET", f"/public/chat/{slug}/meta")
        return PublicStoreMeta.from_dict(data)

    def create_conversation(
        self, slug: str, visitor_name: str | None = None
    ) -> CreateConversationResponse:
        body: dict[str, Any] = {}
        if visitor_name:
            body["visitor_name"] = visitor_name
        data = self._request("POST", f"/public/chat/{slug}/conversations", json_body=body)
        resp = CreateConversationResponse.from_dict(data)
        if resp.visitor_token:
            self._config.visitor_bearer_token = resp.visitor_token
        return resp

    def list_messages(
        self, conversation_id: str, visitor_token: str | None = None
    ) -> list[MessageRecord]:
        data = self._request(
            "GET",
            f"/public/conversations/{conversation_id}/messages",
            headers=self._visitor_headers(visitor_token),
        )
        items = data.get("items", data) if isinstance(data, dict) else data
        return [MessageRecord.from_dict(m) for m in items]

    def stream_chat_turn(
        self,
        slug: str,
        request: ChatTurnRequest,
        visitor_token: str | None = None,
    ) -> Iterator[str]:
        """Streams Server-Sent Events (SSE) lines from the grounded PydanticAI agent."""
        url = f"{self._config.base_url}/public/chat/{slug}/messages"
        with self._client.stream(
            "POST",
            url,
            headers=self._visitor_headers(visitor_token),
            json=request.to_dict(),
            timeout=self._config.timeout,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    yield line

    def request_handoff(
        self,
        conversation_id: str,
        reason: str = "Customer requested human assistance",
        visitor_token: str | None = None,
    ) -> ConversationDetail:
        data = self._request(
            "POST",
            f"/public/conversations/{conversation_id}/handoff",
            headers=self._visitor_headers(visitor_token),
            json_body={"reason": reason},
        )
        return ConversationDetail.from_dict(data)


class InboxController(BaseController):
    """Controller for merchant staff inbox and human handoff management."""

    def list_conversations(self) -> list[ConversationDetail]:
        data = self._request("GET", "/conversations", headers=self._merchant_headers())
        items = data.get("items", data) if isinstance(data, dict) else data
        return [ConversationDetail.from_dict(c) for c in items]

    def accept_conversation(self, conversation_id: str) -> ConversationDetail:
        data = self._request(
            "POST",
            f"/conversations/{conversation_id}/accept",
            headers=self._merchant_headers(),
        )
        return ConversationDetail.from_dict(data)

    def staff_reply(self, conversation_id: str, content: str) -> MessageRecord:
        data = self._request(
            "POST",
            f"/conversations/{conversation_id}/messages",
            headers=self._merchant_headers(),
            json_body={"content": content},
        )
        return MessageRecord.from_dict(data)

    def return_to_ai(self, conversation_id: str) -> ConversationDetail:
        data = self._request(
            "POST",
            f"/conversations/{conversation_id}/return-to-ai",
            headers=self._merchant_headers(),
        )
        return ConversationDetail.from_dict(data)


class OrdersController(BaseController):
    """Controller for order management and PayPal checkout link creation."""

    def list_orders(self) -> list[OrderRecord]:
        data = self._request("GET", "/orders", headers=self._merchant_headers())
        items = data.get("items", data) if isinstance(data, dict) else data
        return [OrderRecord.from_dict(o) for o in items]

    def get_order(self, order_id: str) -> OrderRecord:
        data = self._request("GET", f"/orders/{order_id}", headers=self._merchant_headers())
        return OrderRecord.from_dict(data)

    def create_payment_link(self, order_id: str) -> CreateOrderPaymentLinkResponse:
        data = self._request(
            "POST",
            f"/orders/{order_id}/payment-link",
            headers=self._merchant_headers(),
        )
        return CreateOrderPaymentLinkResponse.from_dict(data)

    def fulfill_order(self, order_id: str) -> OrderRecord:
        data = self._request(
            "POST",
            f"/orders/{order_id}/fulfill",
            headers=self._merchant_headers(),
        )
        return OrderRecord.from_dict(data)


class PaymentsController(BaseController):
    """Controller for PayPal OAuth onboarding and status checks."""

    def get_paypal_status(self) -> PayPalStatusResponse:
        data = self._request("GET", "/settings/paypal", headers=self._merchant_headers())
        return PayPalStatusResponse.from_dict(data)

    def connect_paypal(self, request: PayPalConnectRequest) -> PayPalStatusResponse:
        data = self._request(
            "POST",
            "/settings/paypal",
            headers=self._merchant_headers(),
            json_body=request.to_dict(),
        )
        return PayPalStatusResponse.from_dict(data)


class DashboardController(BaseController):
    """Controller for live merchant revenue summary and idempotent PayPal audit trail."""

    def get_summary(self) -> DashboardSummary:
        data = self._request("GET", "/dashboard/summary", headers=self._merchant_headers())
        return DashboardSummary.from_dict(data)

    def list_audit_ledger(self) -> list[AuditItem]:
        data = self._request("GET", "/audit", headers=self._merchant_headers())
        items = data.get("items", data) if isinstance(data, dict) else data
        return [AuditItem.from_dict(a) for a in items]
