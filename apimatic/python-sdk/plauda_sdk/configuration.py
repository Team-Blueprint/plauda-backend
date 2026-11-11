"""APIMatic SDK Environment & Client Configuration for Plauda."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Environment(StrEnum):
    """Target API server environments defined in apimatic/plauda-openapi.json."""

    PRODUCTION = "https://plauda.fastapicloud.dev"
    LOCAL = "http://localhost:8000"


@dataclass(slots=True)
class RetryConfig:
    """Retry policy matching APIMATIC-META.json."""

    number_of_retries: int = 3
    backoff_factor: float = 2.0
    status_codes_to_retry: tuple[int, ...] = (408, 429, 500, 502, 503, 504)


@dataclass(slots=True)
class Configuration:
    """Strongly-typed configuration for PlaudaClient."""

    environment: Environment = Environment.PRODUCTION
    custom_base_url: str | None = None
    merchant_bearer_token: str | None = None
    visitor_bearer_token: str | None = None
    timeout: float = 30.0
    retry_config: RetryConfig = field(default_factory=RetryConfig)

    @property
    def base_url(self) -> str:
        if self.custom_base_url:
            return self.custom_base_url.rstrip("/")
        return self.environment.value.rstrip("/")
