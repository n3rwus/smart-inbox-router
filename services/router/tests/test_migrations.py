import asyncio
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from common.db import create_engine
from router.adapters.db import Base
from router.migrate import build_config
from sqlalchemy import inspect
from sqlalchemy.engine import Connection


def _url(tmp_path: Path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'migrated.db'}"


def test_alembic_upgrade_creates_messages_table(tmp_path: Path) -> None:
    url = _url(tmp_path)
    command.upgrade(build_config(url), "head")

    engine = create_engine(url)

    async def _inspect() -> tuple[list[str], list[str]]:
        async with engine.connect() as conn:

            def _collect(sync_conn: Connection) -> tuple[list[str], list[str]]:
                insp = inspect(sync_conn)
                columns = [c["name"] for c in insp.get_columns("messages")]
                indexes = [i["name"] for i in insp.get_indexes("messages")]
                return columns, indexes

            return await conn.run_sync(_collect)

    try:
        columns, indexes = asyncio.run(_inspect())
    finally:
        asyncio.run(engine.dispose())

    assert "id" in columns
    assert "sender_email" in columns
    assert "status" in columns
    assert "available_at" in columns
    assert "ix_messages_status_available_at" in indexes


def test_migrations_match_model_metadata(tmp_path: Path) -> None:
    url = _url(tmp_path)
    command.upgrade(build_config(url), "head")

    engine = create_engine(url)

    async def _diff() -> list[object]:
        async with engine.connect() as conn:

            def _compare(sync_conn: Connection) -> list[object]:
                ctx = MigrationContext.configure(sync_conn)
                return list(compare_metadata(ctx, Base.metadata))

            return await conn.run_sync(_compare)

    try:
        diffs = asyncio.run(_diff())
    finally:
        asyncio.run(engine.dispose())

    assert diffs == [], f"model/migration drift: {diffs}"
