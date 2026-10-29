from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import get_settings

_engine: AsyncEngine | None = None


def normalize_database_url(raw_url: str) -> tuple[URL, dict]:
    """Split Supabase-specific URL params into asyncpg connect args.

    asyncpg does not understand ``sslmode``, which Supabase connection strings often carry.
    Supavisor transaction mode also requires client-side statement caching to be disabled.
    """
    url = make_url(raw_url)
    original_query = dict(url.query)
    query = dict(original_query)
    sslmode = query.pop("sslmode", None)
    query.pop("ssl", None)
    if query != original_query:
        url = url.set(query=query)

    connect_args: dict = {}
    host = url.host or ""
    if "pooler.supabase.com" in host:
        connect_args["statement_cache_size"] = 0
    if sslmode in {"require", "verify-ca", "verify-full"} or host.endswith(".supabase.co"):
        connect_args["ssl"] = True
    return url, connect_args


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL is not configured (see backend/.env.example)")
        url, connect_args = normalize_database_url(settings.database_url_async)
        engine_kwargs: dict = {}
        if connect_args.get("statement_cache_size") == 0:
            # Supavisor transaction pooling: no server-side prepared statements.
            engine_kwargs["prepared_statement_cache_size"] = 0
        _engine = create_async_engine(
            url,
            pool_pre_ping=True,
            connect_args=connect_args,
            **engine_kwargs,
        )
    return _engine


def reset_engine() -> None:
    """Drop the cached engine (used by tests when switching databases)."""
    global _engine
    _engine = None
