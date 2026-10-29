import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import app.db.models  # noqa: F401 — register models on Base.metadata
from alembic import context
from app.config import get_settings
from app.db.base import Base
from app.db.engine import normalize_database_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
if not settings.database_url:
    raise RuntimeError("DATABASE_URL is not configured — copy backend/.env.example to backend/.env")
# configparser treats '%' specially; escape it for passwords containing percent signs.
config.set_main_option("sqlalchemy.url", settings.database_url_async.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a DBAPI connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    url, connect_args = normalize_database_url(settings.database_url_async)
    engine_kwargs: dict = {}
    if connect_args.get("statement_cache_size") == 0:
        engine_kwargs["prepared_statement_cache_size"] = 0
    connectable = create_async_engine(
        url,
        poolclass=pool.NullPool,
        connect_args=connect_args,
        **engine_kwargs,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
