from typing import Literal

from pydantic import BaseModel, Field


class PayPalCredentialsIn(BaseModel):
    client_id: str = Field(min_length=1, max_length=200)
    client_secret: str = Field(min_length=1, max_length=500)
    webhook_id: str = Field(min_length=1, max_length=200)
    env: Literal["sandbox", "live"] = "sandbox"


class PayPalStatusOut(BaseModel):
    connected: bool
    env: str | None
