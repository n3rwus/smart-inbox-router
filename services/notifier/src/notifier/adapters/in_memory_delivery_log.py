import asyncio
from contextlib import AbstractAsyncContextManager

# ponytail: unbounded per-message lock dict; see D-009 — swap for SQL-backed log if memory grows.


class InMemoryDeliveryLog:
    def __init__(self) -> None:
        self._hashes: dict[str, str] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._registry_lock = asyncio.Lock()

    async def stored_hash(self, message_id: str) -> str | None:
        return self._hashes.get(message_id)

    async def record(self, message_id: str, content_hash: str) -> None:
        self._hashes[message_id] = content_hash

    def lock(self, message_id: str) -> AbstractAsyncContextManager[None]:
        return _MessageLock(self, message_id)

    async def _acquire(self, message_id: str) -> asyncio.Lock:
        async with self._registry_lock:
            lock = self._locks.get(message_id)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[message_id] = lock
        return lock


class _MessageLock:
    def __init__(self, log: InMemoryDeliveryLog, message_id: str) -> None:
        self._log = log
        self._message_id = message_id
        self._lock: asyncio.Lock | None = None

    async def __aenter__(self) -> None:
        self._lock = await self._log._acquire(self._message_id)
        await self._lock.acquire()

    async def __aexit__(self, *_: object) -> None:
        if self._lock is None:
            raise RuntimeError("lock released without being acquired")
        self._lock.release()
