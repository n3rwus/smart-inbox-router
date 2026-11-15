from typing import Protocol, cast

from common.errors import NotReadyError, UpstreamTimeoutError
from common.timeouts import with_timeout
from fastapi import APIRouter, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

HEALTH_PATH = "/health"
READY_PATH = "/ready"
READY_TIMEOUT_SECONDS = 2.0


class DbReadyProbe(Protocol):
    async def probe(self) -> None: ...


class SessionDbReadyProbe:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        timeout_seconds: float = READY_TIMEOUT_SECONDS,
    ) -> None:
        self._session_factory = session_factory
        self.timeout_seconds = timeout_seconds

    @with_timeout
    async def _select_one(self) -> None:
        async with self._session_factory() as session:
            await session.execute(text("SELECT 1"))

    async def probe(self) -> None:
        try:
            await self._select_one()
        except UpstreamTimeoutError as exc:
            raise NotReadyError(f"database probe timed out: {exc.detail}") from exc
        except NotReadyError:
            raise
        except Exception as exc:
            raise NotReadyError(f"database probe failed: {exc}") from exc


router = APIRouter(include_in_schema=False)


@router.get(HEALTH_PATH, status_code=status.HTTP_200_OK)
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get(READY_PATH, status_code=status.HTTP_200_OK)
async def ready(request: Request) -> dict[str, str]:
    probe = cast(DbReadyProbe, request.app.state.db_probe)
    await probe.probe()
    return {"status": "ready"}
