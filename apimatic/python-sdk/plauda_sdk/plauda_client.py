"""Main strongly-typed APIMatic client entrypoint for Plauda."""

from __future__ import annotations

from types import TracebackType

import httpx

from plauda_sdk.configuration import Configuration, Environment
from plauda_sdk.controllers import (
    AuthController,
    CatalogueController,
    DashboardController,
    InboxController,
    OrdersController,
    PaymentsController,
    PublicChatController,
    SystemController,
)


class PlaudaClient:
    """Strongly-typed Python SDK client for the Plauda API."""

    def __init__(
        self,
        environment: Environment = Environment.PRODUCTION,
        merchant_bearer_token: str | None = None,
        visitor_bearer_token: str | None = None,
        custom_base_url: str | None = None,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.config = Configuration(
            environment=environment,
            custom_base_url=custom_base_url,
            merchant_bearer_token=merchant_bearer_token,
            visitor_bearer_token=visitor_bearer_token,
            timeout=timeout,
        )
        self._owns_client = http_client is None
        self._http = http_client or httpx.Client(timeout=timeout)

        self.system = SystemController(self.config, self._http)
        self.auth = AuthController(self.config, self._http)
        self.catalogue = CatalogueController(self.config, self._http)
        self.public_chat = PublicChatController(self.config, self._http)
        self.inbox = InboxController(self.config, self._http)
        self.orders = OrdersController(self.config, self._http)
        self.payments = PaymentsController(self.config, self._http)
        self.dashboard = DashboardController(self.config, self._http)

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> PlaudaClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()
