"""Deadline handling shared by outbound adapters."""

import asyncio
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any, Concatenate, Protocol

from common.errors import UpstreamTimeoutError


class HasTimeout(Protocol):
    @property
    def timeout_seconds(self) -> float: ...


def with_timeout[S: HasTimeout, **P, R](
    method: Callable[Concatenate[S, P], Coroutine[Any, Any, R]],
) -> Callable[Concatenate[S, P], Coroutine[Any, Any, R]]:
    """Bound an async method by ``self.timeout_seconds``; raise UpstreamTimeoutError on expiry."""

    async def wrapper(self: S, /, *args: P.args, **kwargs: P.kwargs) -> R:
        try:
            async with asyncio.timeout(self.timeout_seconds):
                return await method(self, *args, **kwargs)
        except TimeoutError as exc:
            raise UpstreamTimeoutError(
                f"{method.__qualname__} exceeded {self.timeout_seconds}s"
            ) from exc

    wraps(method)(wrapper)
    return wrapper
