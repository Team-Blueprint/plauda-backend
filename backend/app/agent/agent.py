import uuid
from typing import Annotated

from pydantic import Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model
from pydantic_ai.models.groq import GroqModel
from pydantic_ai.providers.groq import GroqProvider

from app.agent.deps import AgentDeps
from app.agent.prompts import build_system_prompt
from app.agent.tools.business_info import search_store_info
from app.agent.tools.catalogue import search_products
from app.agent.tools.handoff import request_human_handoff
from app.agent.tools.orders import add_order_item as add_order_item_tool
from app.agent.tools.orders import confirm_order as confirm_order_tool
from app.agent.tools.orders import create_payment_link as create_payment_link_tool
from app.agent.tools.orders import get_delivery_options as get_delivery_options_tool
from app.agent.tools.orders import remove_order_item as remove_order_item_tool
from app.agent.tools.orders import set_delivery_details as set_delivery_details_tool
from app.agent.tools.orders import start_order as start_order_tool
from app.config import Settings, get_settings
from app.db.models import Merchant, Order


class AgentConfigError(RuntimeError):
    """Raised when the LLM provider is not configured."""


def get_agent_model(settings: Settings | None = None) -> Model:
    settings = settings or get_settings()
    if not settings.groq_api_key.strip():
        raise AgentConfigError("GROQ_API_KEY is not configured")
    return GroqModel(
        settings.groq_agent_model,
        provider=GroqProvider(api_key=settings.groq_api_key),
    )


def get_cheap_model(settings: Settings | None = None) -> Model:
    """Cheap model used for routing and classification turns."""
    settings = settings or get_settings()
    if not settings.groq_api_key.strip():
        raise AgentConfigError("GROQ_API_KEY is not configured")
    return GroqModel(
        settings.groq_cheap_model,
        provider=GroqProvider(api_key=settings.groq_api_key),
    )


def build_agent(
    model: Model,
    merchant: Merchant,
    order: Order | None = None,
) -> Agent[AgentDeps, str]:
    """Build one agent with the merchant's grounding prompt and typed tools."""
    agent: Agent[AgentDeps, str] = Agent(
        model,
        deps_type=AgentDeps,
        system_prompt=build_system_prompt(merchant, order),
    )

    @agent.tool
    async def search_business_info(
        ctx: RunContext[AgentDeps],
        query: Annotated[
            str,
            Field(description="The buyer's question about store policies, delivery, or FAQ."),
        ],
    ) -> str:
        """Search the store's approved about, policy, and FAQ documents."""
        return await search_store_info(ctx.deps, query)

    @agent.tool
    async def search_catalogue(
        ctx: RunContext[AgentDeps],
        query: Annotated[
            str,
            Field(description="Product name, description, or variant to search for."),
        ] = "",
        limit: Annotated[int, Field(description="Maximum products to return.", ge=1, le=20)] = 8,
    ) -> str:
        """Search the merchant's active catalogue for exact products, prices, and stock."""
        return await search_products(ctx.deps, query, limit)

    @agent.tool
    async def start_order(ctx: RunContext[AgentDeps]) -> str:
        """Start a new draft order for this chat, unless an active order already exists."""
        return await start_order_tool(ctx.deps)

    @agent.tool
    async def add_order_item(
        ctx: RunContext[AgentDeps],
        product_id: Annotated[
            str,
            Field(description="Product id returned by search_catalogue."),
        ],
        variant_id: Annotated[
            str | None,
            Field(
                description="Variant id from search_catalogue, or null when there is no variant."
            ),
        ] = None,
        qty: Annotated[int, Field(description="Quantity to add (1-99).", ge=1, le=99)] = 1,
    ) -> str:
        """Add one catalogue product+variant to the draft order."""
        try:
            product_uuid = uuid.UUID(product_id)
            variant_uuid = uuid.UUID(variant_id) if variant_id else None
        except (TypeError, ValueError):
            return (
                "That product or variant id is invalid. Call search_catalogue again and use an "
                "exact id from its result."
            )
        return await add_order_item_tool(ctx.deps, product_uuid, variant_uuid, qty)

    @agent.tool
    async def remove_order_item(
        ctx: RunContext[AgentDeps],
        item_id: Annotated[str, Field(description="Order item id from the order summary.")],
    ) -> str:
        """Remove one item from the current draft order."""
        try:
            item_uuid = uuid.UUID(item_id)
        except (TypeError, ValueError):
            return "That order item id is invalid. Use an id from the current order summary."
        return await remove_order_item_tool(ctx.deps, item_uuid)

    @agent.tool
    async def get_delivery_options(ctx: RunContext[AgentDeps]) -> str:
        """List delivery zones, areas, fees, and ETAs for this store."""
        return await get_delivery_options_tool(ctx.deps)

    @agent.tool
    async def set_delivery_details(
        ctx: RunContext[AgentDeps],
        zone_id: Annotated[str, Field(description="Delivery zone id from get_delivery_options.")],
        address: Annotated[
            str,
            Field(description="Full delivery address supplied by the buyer.", max_length=500),
        ],
    ) -> str:
        """Save the buyer's delivery zone and address on the draft order."""
        try:
            zone_uuid = uuid.UUID(zone_id)
        except (TypeError, ValueError):
            return "That delivery zone id is invalid. Call get_delivery_options again."
        return await set_delivery_details_tool(ctx.deps, zone_uuid, address)

    @agent.tool
    async def confirm_order(ctx: RunContext[AgentDeps]) -> str:
        """Confirm the draft, but only after the buyer explicitly says yes in a later message."""
        return await confirm_order_tool(ctx.deps)

    @agent.tool
    async def create_payment_link(ctx: RunContext[AgentDeps]) -> str:
        """Create (or reuse) the PayPal approval link for the confirmed order."""
        return await create_payment_link_tool(ctx.deps)

    @agent.tool
    async def request_handoff(
        ctx: RunContext[AgentDeps],
        reason: Annotated[
            str,
            Field(description="Why the buyer needs a human, in one short sentence."),
        ],
    ) -> str:
        """Ask the store owner to take over this conversation."""
        return await request_human_handoff(ctx.deps, reason)

    return agent
