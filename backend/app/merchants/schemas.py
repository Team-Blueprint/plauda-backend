import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.merchants.constants import MAX_PRODUCT_IMAGES, PAYPAL_SUPPORTED_CURRENCIES


def _validate_currency(value: str) -> str:
    code = value.upper()
    if code not in PAYPAL_SUPPORTED_CURRENCIES:
        raise ValueError(
            f"Currency {code!r} is not supported by PayPal. "
            f"Allowed: {', '.join(sorted(PAYPAL_SUPPORTED_CURRENCIES))}"
        )
    return code


class VariantIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    options: dict = Field(default_factory=dict)
    price_override: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    stock: int = Field(default=0, ge=0)


class VariantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    options: dict | None = None
    price_override: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    stock: int | None = Field(default=None, ge=0)


class VariantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    options: dict
    price_override: Decimal | None
    stock: int


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str | None = None
    active: bool = True
    image_urls: list[str] = Field(default_factory=list, max_length=MAX_PRODUCT_IMAGES)
    variants: list[VariantIn] = Field(default_factory=list)

    @field_validator("currency")
    @classmethod
    def _currency(cls, value: str | None) -> str | None:
        return None if value is None else _validate_currency(value)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    price: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    currency: str | None = None
    active: bool | None = None
    image_urls: list[str] | None = Field(default=None, max_length=MAX_PRODUCT_IMAGES)

    @field_validator("currency")
    @classmethod
    def _currency(cls, value: str | None) -> str | None:
        return None if value is None else _validate_currency(value)


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    price: Decimal
    currency: str
    active: bool
    image_urls: list[str]
    created_at: datetime
    updated_at: datetime
    variants: list[VariantOut]


class ZoneCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    areas: list[str] = Field(default_factory=list)
    fee: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2)
    eta_days: int = Field(default=0, ge=0, le=365)


class ZoneUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    areas: list[str] | None = None
    fee: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    eta_days: int | None = Field(default=None, ge=0, le=365)


class ZoneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    areas: list[str]
    fee: Decimal
    eta_days: int
    created_at: datetime
    updated_at: datetime


class BusinessInfoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    content: str
    updated_at: datetime | None = None


class BusinessInfoUpdate(BaseModel):
    content: str = Field(max_length=200_000)


class SettingsOut(BaseModel):
    name: str
    slug: str
    currency: str
    refund_cap: Decimal
    recovery_reminder_enabled: bool
    recovery_timeout_minutes: int
    paypal_connected: bool
    chat_link: str


class SettingsUpdate(BaseModel):
    currency: str | None = None
    refund_cap: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    recovery_reminder_enabled: bool | None = None
    recovery_timeout_minutes: int | None = Field(default=None, ge=15, le=10_080)

    @field_validator("currency")
    @classmethod
    def _currency(cls, value: str | None) -> str | None:
        return None if value is None else _validate_currency(value)


class PublicMetaOut(BaseModel):
    name: str
    slug: str
    currency: str
    chat_link: str
