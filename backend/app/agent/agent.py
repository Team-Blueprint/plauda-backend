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
from app.config import Settings, get_settings
from app.db.models import Merchant


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


def build_agent(model: Model, merchant: Merchant) -> Agent[AgentDeps, str]:
    """Build one agent with the merchant's grounding prompt and typed tools."""
    agent: Agent[AgentDeps, str] = Agent(
        model,
        deps_type=AgentDeps,
        system_prompt=build_system_prompt(merchant),
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
