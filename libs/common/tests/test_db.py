from pathlib import Path

from common.db import SQLITE_BUSY_TIMEOUT_MS, create_engine, create_session_factory
from sqlalchemy import text


def _sqlite_url(tmp_path: Path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'router.db'}"


async def test_sqlite_pragmas_applied_on_new_connection(tmp_path: Path) -> None:
    engine = create_engine(_sqlite_url(tmp_path))
    try:
        async with engine.connect() as conn:
            journal = (await conn.execute(text("PRAGMA journal_mode"))).scalar_one()
            foreign_keys = (await conn.execute(text("PRAGMA foreign_keys"))).scalar_one()
            busy_timeout = (await conn.execute(text("PRAGMA busy_timeout"))).scalar_one()
    finally:
        await engine.dispose()

    assert str(journal).lower() == "wal"
    assert foreign_keys == 1
    assert busy_timeout == SQLITE_BUSY_TIMEOUT_MS


async def test_session_factory_executes_statements(tmp_path: Path) -> None:
    engine = create_engine(_sqlite_url(tmp_path))
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session:
            value = (await session.execute(text("SELECT 1"))).scalar_one()
    finally:
        await engine.dispose()

    assert value == 1


async def test_session_factory_keeps_instance_usable_after_commit(tmp_path: Path) -> None:
    engine = create_engine(_sqlite_url(tmp_path))
    session_factory = create_session_factory(engine)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY, v INTEGER)"))
        async with session_factory() as session:
            await session.execute(text("INSERT INTO t (v) VALUES (42)"))
            await session.commit()
            value = (await session.execute(text("SELECT v FROM t"))).scalar_one()
    finally:
        await engine.dispose()

    assert value == 42
