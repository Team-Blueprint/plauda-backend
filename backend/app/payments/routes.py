import uuid

from fastapi import APIRouter, HTTPException, Request, status

from app.db.models import Merchant
from app.deps import CurrentUserDep, SessionDep
from app.payments.crypto import encrypt_secret
from app.payments.errors import PaymentProviderError
from app.payments.paypal.client import PayPalClient
from app.payments.schemas import PayPalCredentialsIn, PayPalStatusOut
from app.payments.webhooks import handle_webhook

settings_router = APIRouter(prefix="/settings/paypal", tags=["payments"])
webhook_router = APIRouter(prefix="/webhooks/paypal", tags=["webhooks"])


@settings_router.get("", response_model=PayPalStatusOut)
async def get_paypal_status(user: CurrentUserDep) -> PayPalStatusOut:
    merchant = user.merchant
    connected = bool(
        merchant.paypal_client_id_enc
        and merchant.paypal_secret_enc
        and merchant.paypal_webhook_id_enc
    )
    return PayPalStatusOut(connected=connected, env=merchant.paypal_env)


@settings_router.post("", response_model=PayPalStatusOut)
async def connect_paypal(
    payload: PayPalCredentialsIn, user: CurrentUserDep, session: SessionDep
) -> PayPalStatusOut:
    client = PayPalClient(
        client_id=payload.client_id,
        client_secret=payload.client_secret,
        env=payload.env,
    )
    try:
        await client.check_credentials()
    except PaymentProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="PayPal rejected these credentials",
        ) from exc

    merchant = user.merchant
    merchant.paypal_client_id_enc = encrypt_secret(payload.client_id)
    merchant.paypal_secret_enc = encrypt_secret(payload.client_secret)
    merchant.paypal_webhook_id_enc = encrypt_secret(payload.webhook_id)
    merchant.paypal_env = payload.env
    await session.commit()
    return PayPalStatusOut(connected=True, env=payload.env)


@settings_router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_paypal(user: CurrentUserDep, session: SessionDep) -> None:
    merchant = user.merchant
    merchant.paypal_client_id_enc = None
    merchant.paypal_secret_enc = None
    merchant.paypal_webhook_id_enc = None
    merchant.paypal_env = None
    await session.commit()


@webhook_router.post("/{merchant_id}")
async def paypal_webhook(merchant_id: uuid.UUID, request: Request, session: SessionDep) -> dict:
    merchant = await session.get(Merchant, merchant_id)
    if merchant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Merchant not found")

    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body"
        ) from None

    headers = {key.lower(): value for key, value in request.headers.items()}
    return await handle_webhook(session, merchant, headers, payload)
