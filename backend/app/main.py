import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.agent.routes import router as agent_chat_router
from app.auth.routes import router as auth_router
from app.config import get_settings
from app.conversations.routes_inbox import router as inbox_router
from app.conversations.routes_public import router as public_chat_router
from app.dashboard.routes import audit_router, summary_router
from app.db.engine import get_engine
from app.errors import register_error_handlers
from app.logging import configure_logging
from app.merchants.business_info import router as business_info_router
from app.merchants.catalogue import router as catalogue_router
from app.merchants.public import router as public_router
from app.merchants.settings import router as settings_router
from app.merchants.zones import router as zones_router
from app.orders.routes import router as orders_router
from app.payments.routes import settings_router as paypal_settings_router
from app.payments.routes import webhook_router as paypal_webhook_router

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=f"{settings.app_name} API",
        version="0.1.0",
        description="AI employee for chat-driven businesses.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(auth_router)
    app.include_router(catalogue_router)
    app.include_router(zones_router)
    app.include_router(business_info_router)
    app.include_router(settings_router)
    app.include_router(public_router)
    app.include_router(orders_router)
    app.include_router(public_chat_router)
    app.include_router(agent_chat_router)
    app.include_router(inbox_router)
    app.include_router(summary_router)
    app.include_router(audit_router)
    app.include_router(paypal_settings_router)
    app.include_router(paypal_webhook_router)

    @app.get("/healthz", tags=["system"])
    async def healthz() -> dict:
        db_status = "not_configured"
        if settings.database_url:
            try:
                async with get_engine().connect() as conn:
                    await conn.execute(text("SELECT 1"))
                db_status = "ok"
            except Exception:
                logger.exception("healthz database check failed")
                db_status = "error"
        return {
            "status": "ok" if db_status != "error" else "degraded",
            "app": settings.app_name,
            "env": settings.env,
            "db": db_status,
        }

    return app


app = create_app()
