import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.auth.routes import router as auth_router
from app.config import get_settings
from app.db.engine import get_engine
from app.errors import register_error_handlers
from app.logging import configure_logging

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
