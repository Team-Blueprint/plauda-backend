"""Thin PayPal Orders v2 + Webhooks client (no SDK)."""

from decimal import Decimal
from typing import Any

import httpx

from app.db.models import Merchant
from app.payments.crypto import decrypt_secret
from app.payments.errors import (
    CredentialError,
    PaymentProviderError,
    PayPalNotConfiguredError,
)

SANDBOX_BASE_URL = "https://api-m.sandbox.paypal.com"
LIVE_BASE_URL = "https://api-m.paypal.com"


def _base_url(env: str) -> str:
    if env == "live":
        return LIVE_BASE_URL
    if env == "sandbox":
        return SANDBOX_BASE_URL
    raise PayPalNotConfiguredError(f"Unknown PayPal environment {env!r}")


class PayPalClient:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        env: str,
        webhook_id: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.env = env
        self.base_url = _base_url(env)
        self.webhook_id = webhook_id
        self.transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=30.0, transport=self.transport)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        request_headers = {"Accept": "application/json"}
        if headers:
            request_headers.update(headers)
        if token:
            request_headers["Authorization"] = f"Bearer {token}"
        try:
            async with self._client() as client:
                return await client.request(
                    method,
                    f"{self.base_url}{path}",
                    headers=request_headers,
                    **kwargs,
                )
        except httpx.HTTPError as exc:
            raise PaymentProviderError("Could not reach PayPal") from exc

    async def _token(self) -> str:
        try:
            async with self._client() as client:
                resp = await client.post(
                    f"{self.base_url}/v1/oauth2/token",
                    auth=(self.client_id, self.client_secret),
                    data={"grant_type": "client_credentials"},
                    headers={"Accept": "application/json"},
                )
        except httpx.HTTPError as exc:
            raise PaymentProviderError("Could not reach PayPal") from exc
        if resp.status_code != 200:
            raise PaymentProviderError("PayPal authentication failed")
        token = resp.json().get("access_token")
        if not token:
            raise PaymentProviderError("PayPal did not return an access token")
        return token

    async def check_credentials(self) -> None:
        await self._token()

    async def create_order(
        self,
        *,
        reference_id: str,
        amount: Decimal,
        currency: str,
        return_url: str,
        cancel_url: str,
    ) -> dict:
        token = await self._token()
        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": reference_id,
                    "amount": {"currency_code": currency, "value": f"{amount:.2f}"},
                }
            ],
            "application_context": {
                "return_url": return_url,
                "cancel_url": cancel_url,
                "user_action": "PAY_NOW",
                "shipping_preference": "NO_SHIPPING",
            },
        }
        resp = await self._request("POST", "/v2/checkout/orders", token=token, json=payload)
        if resp.status_code not in (200, 201):
            raise PaymentProviderError("PayPal could not create the order")
        return resp.json()

    async def get_order(self, order_id: str) -> dict:
        token = await self._token()
        resp = await self._request("GET", f"/v2/checkout/orders/{order_id}", token=token)
        if resp.status_code != 200:
            raise PaymentProviderError("PayPal could not load the order")
        return resp.json()

    async def capture_order(self, order_id: str) -> dict:
        token = await self._token()
        resp = await self._request(
            "POST", f"/v2/checkout/orders/{order_id}/capture", token=token, json={}
        )
        if resp.status_code == 422:
            try:
                details = resp.json().get("details", [])
            except ValueError:
                details = []
            issues = {detail.get("issue") for detail in details}
            if "ORDER_ALREADY_CAPTURED" in issues:
                return {"status": "COMPLETED", "already_captured": True}
        if resp.status_code not in (200, 201):
            raise PaymentProviderError("PayPal could not capture the order")
        return resp.json()

    async def refund(self, capture_id: str, *, amount: Decimal, currency: str) -> dict:
        token = await self._token()
        resp = await self._request(
            "POST",
            f"/v2/payments/captures/{capture_id}/refund",
            token=token,
            json={"amount": {"currency_code": currency, "value": f"{amount:.2f}"}},
        )
        if resp.status_code not in (200, 201):
            raise PaymentProviderError("PayPal could not issue the refund")
        return resp.json()

    async def verify_webhook_signature(self, headers: dict[str, str], event: dict) -> bool:
        if not self.webhook_id:
            return False
        transmission_id = headers.get("paypal-transmission-id")
        transmission_time = headers.get("paypal-transmission-time")
        cert_url = headers.get("paypal-cert-url")
        auth_algo = headers.get("paypal-auth-algo")
        transmission_sig = headers.get("paypal-transmission-sig")
        if not all([transmission_id, transmission_time, cert_url, auth_algo, transmission_sig]):
            return False

        token = await self._token()
        resp = await self._request(
            "POST",
            "/v1/notifications/verify-webhook-signature",
            token=token,
            json={
                "auth_algo": auth_algo,
                "cert_url": cert_url,
                "transmission_id": transmission_id,
                "transmission_sig": transmission_sig,
                "transmission_time": transmission_time,
                "webhook_id": self.webhook_id,
                "webhook_event": event,
            },
        )
        if resp.status_code != 200:
            return False
        return resp.json().get("verification_status") == "SUCCESS"


def extract_approval_link(paypal_order: dict) -> str | None:
    for link in paypal_order.get("links", []):
        if link.get("rel") in ("approve", "payer-action"):
            return link.get("href")
    return None


def client_for_merchant(merchant: Merchant) -> PayPalClient:
    if not (merchant.paypal_client_id_enc and merchant.paypal_secret_enc):
        raise PayPalNotConfiguredError("PayPal is not connected for this merchant")
    if not merchant.paypal_env:
        raise PayPalNotConfiguredError("PayPal environment is not configured")
    try:
        webhook_id = (
            decrypt_secret(merchant.paypal_webhook_id_enc)
            if merchant.paypal_webhook_id_enc
            else None
        )
        return PayPalClient(
            client_id=decrypt_secret(merchant.paypal_client_id_enc),
            client_secret=decrypt_secret(merchant.paypal_secret_enc),
            env=merchant.paypal_env,
            webhook_id=webhook_id,
        )
    except CredentialError as exc:
        raise PayPalNotConfiguredError(str(exc)) from exc
