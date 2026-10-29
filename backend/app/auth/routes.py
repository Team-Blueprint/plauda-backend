import logging
import re
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.auth.security import create_access_token, hash_password, verify_password
from app.db.models import Merchant, User
from app.db.session import get_session
from app.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80] or "store"


async def _unique_slug(session: AsyncSession, base: str) -> str:
    slug = base
    for _ in range(5):
        exists = await session.scalar(select(Merchant.id).where(Merchant.slug == slug))
        if exists is None:
            return slug
        slug = f"{base}-{secrets.token_hex(2)}"
    return f"{base}-{secrets.token_hex(4)}"


def _token_response(user: User) -> TokenResponse:
    token = create_access_token(
        user_id=str(user.id), merchant_id=str(user.merchant_id), role=user.role
    )
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    session: SessionDep,
) -> TokenResponse:
    """Create a merchant (store) and its single owner account in one transaction."""
    email = payload.email.lower()
    existing = await session.scalar(select(User.id).where(User.email == email))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    merchant = Merchant(
        name=payload.store_name.strip(),
        slug=await _unique_slug(session, _slugify(payload.store_name)),
    )
    user = User(
        merchant=merchant,
        email=email,
        hashed_password=hash_password(payload.password),
        role="owner",
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        ) from None

    logger.info("merchant registered", extra={"merchant_id": str(merchant.id)})
    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    session: SessionDep,
) -> TokenResponse:
    user = await session.scalar(
        select(User).where(User.email == payload.email.lower()).options(selectinload(User.merchant))
    )
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    return _token_response(user)


@router.get("/me", response_model=UserOut)
async def me(current_user: CurrentUserDep) -> UserOut:
    return UserOut.model_validate(current_user)
