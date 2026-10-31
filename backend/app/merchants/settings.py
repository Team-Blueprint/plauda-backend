from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.config import get_settings
from app.db.models import Product
from app.deps import CurrentUserDep, SessionDep
from app.merchants.schemas import SettingsOut, SettingsUpdate

router = APIRouter(prefix="/settings", tags=["settings"])


def _chat_link(slug: str) -> str:
    base = get_settings().frontend_base_url.rstrip("/")
    return f"{base}/chat/{slug}"


def _settings_out(user: CurrentUserDep) -> SettingsOut:
    merchant = user.merchant
    return SettingsOut(
        name=merchant.name,
        slug=merchant.slug,
        currency=merchant.currency,
        refund_cap=merchant.refund_cap,
        recovery_reminder_enabled=merchant.recovery_reminder_enabled,
        recovery_timeout_minutes=merchant.recovery_timeout_minutes,
        paypal_connected=bool(
            merchant.paypal_client_id_enc
            and merchant.paypal_secret_enc
            and merchant.paypal_webhook_id_enc
        ),
        chat_link=_chat_link(merchant.slug),
    )


@router.get("", response_model=SettingsOut)
async def get_settings_endpoint(user: CurrentUserDep) -> SettingsOut:
    return _settings_out(user)


@router.patch("", response_model=SettingsOut)
async def update_settings(
    payload: SettingsUpdate,
    user: CurrentUserDep,
    session: SessionDep,
) -> SettingsOut:
    merchant = user.merchant
    data = payload.model_dump(exclude_unset=True, exclude_none=True)

    if "currency" in data and data["currency"] != merchant.currency:
        has_products = await session.scalar(
            select(Product.id).where(Product.merchant_id == merchant.id).limit(1)
        )
        if has_products is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot change store currency while products exist",
            )
        merchant.currency = data.pop("currency")

    for field, value in data.items():
        setattr(merchant, field, value)

    await session.commit()
    await session.refresh(merchant)
    return _settings_out(user)
