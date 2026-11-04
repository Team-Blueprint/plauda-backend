from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.agent.deps import AgentDeps
from app.db.models import Product, ProductVariant


def _money(value: Decimal) -> str:
    return f"{value:.2f}"


async def search_products(deps: AgentDeps, query: str = "", limit: int = 8) -> str:
    """Search the merchant's active catalogue using SQL, never vector similarity."""
    limit = min(max(limit, 1), 20)
    statement = (
        select(Product)
        .options(selectinload(Product.variants))
        .where(Product.merchant_id == deps.merchant.id, Product.active.is_(True))
    )

    query = query.strip()
    if query:
        pattern = f"%{query}%"
        statement = statement.where(
            or_(
                Product.name.ilike(pattern),
                Product.description.ilike(pattern),
                Product.variants.any(ProductVariant.name.ilike(pattern)),
            )
        )

    statement = statement.order_by(Product.name).limit(limit)
    products = list(await deps.session.scalars(statement))
    if not products:
        return "No active products matched that request."

    lines: list[str] = []
    for product in products:
        lines.append(
            f"Product: {product.name} (id={product.id}); "
            f"price={_money(product.price)} {product.currency}"
        )
        if product.description.strip():
            lines.append(f"  description: {product.description.strip()}")
        for variant in product.variants:
            unit_price = (
                variant.price_override if variant.price_override is not None else product.price
            )
            lines.append(
                f"  variant: {variant.name} (id={variant.id}); "
                f"price={_money(unit_price)} {product.currency}; stock={variant.stock}"
            )
    return "\n".join(lines)
