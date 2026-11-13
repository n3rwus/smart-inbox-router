import asyncio
from contextlib import AbstractAsyncContextManager


class InMemoryDeliveryLog:
    def __init__(self) -> None:
        self._delivered: set[str] = set()
        self._locks: dict[str, asyncio.Lock] = {}
        self._registry_lock = asyncio.Lock()

    async def is_delivered(self, message_id: str) -> bool:
        return message_id in self._delivered

    async def mark_delivered(self, message_id: str) -> None:
        self._delivered.add(message_id)

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
