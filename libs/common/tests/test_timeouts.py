import asyncio

import pytest
from common.errors import UpstreamTimeoutError
from common.timeouts import with_timeout

FAST_TIMEOUT_SECONDS = 0.01
RESULT = "done"


class _Upstream:
    def __init__(self, timeout_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds
        self._never_set = asyncio.Event()

    @with_timeout
    async def hang(self) -> None:
        await self._never_set.wait()

    @with_timeout
    async def answer(self) -> str:
        return RESULT


async def test_raises_upstream_timeout_after_deadline():
    with pytest.raises(UpstreamTimeoutError):
        await _Upstream(FAST_TIMEOUT_SECONDS).hang()


async def test_returns_result_within_deadline():
    assert await _Upstream(FAST_TIMEOUT_SECONDS).answer() == RESULT


def test_keeps_wrapped_method_name():
    assert _Upstream.answer.__name__ == "answer"
