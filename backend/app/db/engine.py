from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import get_settings

_engine: AsyncEngine | None = None


def normalize_database_url(raw_url: str, ssl_mode: str = "verify-full") -> tuple[URL, dict]:
    """Split Supabase-specific URL params into asyncpg connect args.

    asyncpg does not understand ``sslmode``, which Supabase connection strings often carry.
    Supavisor pooling also requires client-side statement caching to be disabled.
    """
    url = make_url(raw_url)
    query = dict(url.query)
    url_sslmode = query.pop("sslmode", None)
    query.pop("ssl", None)

    connect_args: dict = {}
    host = url.host or ""
    if "pooler.supabase.com" in host:
        # Supavisor pooling: disable both dialect-level and asyncpg statement caches.
        connect_args["statement_cache_size"] = 0
        query["prepared_statement_cache_size"] = "0"
    if url_sslmode is not None:
        connect_args["ssl"] = url_sslmode
    elif host.endswith((".supabase.co", ".supabase.com")):
        connect_args["ssl"] = ssl_mode

    if query != dict(url.query):
        url = url.set(query=query)
    return url, connect_args


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL is not configured (see backend/.env.example)")
        url, connect_args = normalize_database_url(
            settings.database_url_async, ssl_mode=settings.database_ssl_mode
        )
        _engine = create_async_engine(
            url,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
    return _engine


def reset_engine() -> None:
    """Drop the cached engine (used by tests when switching databases)."""
    global _engine
    _engine = None
