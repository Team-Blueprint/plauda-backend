import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Product, ProductVariant
from app.deps import CurrentUserDep, SessionDep
from app.merchants.schemas import (
    ProductCreate,
    ProductOut,
    ProductUpdate,
    VariantIn,
    VariantOut,
    VariantUpdate,
)

router = APIRouter(prefix="/products", tags=["catalogue"])


async def _get_product_or_404(
    session: AsyncSession, merchant_id: uuid.UUID, product_id: uuid.UUID
) -> Product:
    product = await session.scalar(
        select(Product)
        .where(Product.id == product_id, Product.merchant_id == merchant_id)
        .options(selectinload(Product.variants))
    )
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


async def _get_variant_or_404(
    session: AsyncSession, product: Product, variant_id: uuid.UUID
) -> ProductVariant:
    variant = await session.scalar(
        select(ProductVariant).where(
            ProductVariant.id == variant_id, ProductVariant.product_id == product.id
        )
    )
    if variant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")
    return variant


def _resolve_currency(payload_currency: str | None, merchant_currency: str) -> str:
    currency = payload_currency or merchant_currency
    if currency != merchant_currency:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Product currency must match store currency ({merchant_currency})",
        )
    return currency


@router.get("", response_model=list[ProductOut])
async def list_products(
    user: CurrentUserDep,
    session: SessionDep,
    include_inactive: bool = False,
) -> list[Product]:
    stmt = (
        select(Product)
        .where(Product.merchant_id == user.merchant_id)
        .options(selectinload(Product.variants))
        .order_by(Product.created_at.desc())
    )
    if not include_inactive:
        stmt = stmt.where(Product.active.is_(True))
    return list(await session.scalars(stmt))


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    user: CurrentUserDep,
    session: SessionDep,
) -> Product:
    currency = _resolve_currency(payload.currency, user.merchant.currency)
    product = Product(
        merchant_id=user.merchant_id,
        name=payload.name,
        description=payload.description,
        price=payload.price,
        currency=currency,
        active=payload.active,
        image_urls=payload.image_urls,
        variants=[ProductVariant(**variant.model_dump()) for variant in payload.variants],
    )
    session.add(product)
    await session.commit()
    return await _get_product_or_404(session, user.merchant_id, product.id)


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(
    product_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> Product:
    return await _get_product_or_404(session, user.merchant_id, product_id)


@router.patch("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    user: CurrentUserDep,
    session: SessionDep,
) -> Product:
    product = await _get_product_or_404(session, user.merchant_id, product_id)
    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "currency" in data:
        data["currency"] = _resolve_currency(data["currency"], user.merchant.currency)
    for field, value in data.items():
        setattr(product, field, value)
    await session.commit()
    return await _get_product_or_404(session, user.merchant_id, product_id)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> None:
    """Hard delete. Phase 3 adds a guard: products referenced by order items must be deactivated."""
    product = await _get_product_or_404(session, user.merchant_id, product_id)
    await session.delete(product)
    await session.commit()


@router.post(
    "/{product_id}/variants",
    response_model=VariantOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_variant(
    product_id: uuid.UUID,
    payload: VariantIn,
    user: CurrentUserDep,
    session: SessionDep,
) -> ProductVariant:
    product = await _get_product_or_404(session, user.merchant_id, product_id)
    variant = ProductVariant(product=product, **payload.model_dump())
    session.add(variant)
    await session.commit()
    await session.refresh(variant)
    return variant


@router.patch("/{product_id}/variants/{variant_id}", response_model=VariantOut)
async def update_variant(
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
    payload: VariantUpdate,
    user: CurrentUserDep,
    session: SessionDep,
) -> ProductVariant:
    product = await _get_product_or_404(session, user.merchant_id, product_id)
    variant = await _get_variant_or_404(session, product, variant_id)
    data = payload.model_dump(exclude_unset=True)
    if "price_override" in data and data["price_override"] is None:
        variant.price_override = None
    for field, value in data.items():
        if field == "price_override" and value is None:
            continue
        if value is not None:
            setattr(variant, field, value)
    await session.commit()
    await session.refresh(variant)
    return variant


@router.delete("/{product_id}/variants/{variant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_variant(
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> None:
    product = await _get_product_or_404(session, user.merchant_id, product_id)
    variant = await _get_variant_or_404(session, product, variant_id)
    await session.delete(variant)
    await session.commit()
