import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

# ponytail: unbounded per-message lock dict; PoC accepts the growth.
# Upgrade path: SQL-backed DeliveryLog behind the same port.


class InMemoryDeliveryLog:
    def __init__(self) -> None:
        self._hashes: dict[str, str] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def stored_hash(self, message_id: str) -> str | None:
        return self._hashes.get(message_id)

    async def record(self, message_id: str, content_hash: str) -> None:
        self._hashes[message_id] = content_hash

    @asynccontextmanager
    async def lock(self, message_id: str) -> AsyncIterator[None]:
        async with self._locks.setdefault(message_id, asyncio.Lock()):
            yield
