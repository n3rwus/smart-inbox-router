import asyncio
from logging.config import fileConfig

import router.adapters.db  # noqa: F401 -- registers MessageRow with Base.metadata
from alembic import context
from common.db import create_engine
from router.adapters.db import Base
from router.config import RouterSettings
from sqlalchemy.engine import Connection

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    x_args = context.get_x_argument(as_dictionary=True)
    url = x_args.get("url") or config.get_main_option("sqlalchemy.url")
    if url:
        return url
    return RouterSettings().database_url


def _configure(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    engine = create_engine(_database_url())
    try:
        async with engine.connect() as conn:
            await conn.run_sync(_configure)
    finally:
        await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_async())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
