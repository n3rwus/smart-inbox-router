import asyncio
from uuid import UUID

import httpx
from common.departments import Department
from common.errors import DeliveryFailedError, UpstreamTimeoutError
from common.http import CORRELATION_ID_HEADER
from common.log import correlation_id
from common.timeouts import with_timeout

from router.ports.notifier import DeliveryRejectedError, DeliveryResult

RETRYABLE_STATUSES = frozenset({502, 503, 504})
REJECTED_STATUSES = frozenset({409, 422})
INITIAL_BACKOFF_SECONDS = 0.1
BACKOFF_MULTIPLIER = 2.0


class HttpNotifier:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        max_retries: int,
        client: httpx.AsyncClient | None = None,
        initial_backoff_seconds: float = INITIAL_BACKOFF_SECONDS,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._initial_backoff_seconds = initial_backoff_seconds
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def notify(
        self,
        *,
        message_id: UUID,
        department: Department,
        sender_email: str,
        body: str,
    ) -> DeliveryResult:
        url = f"{self._base_url}/api/v1/notifications/{message_id}"
        payload = {
            "department": department.value,
            "sender": sender_email,
            "body": body,
        }
        headers = self._headers()

        last_error: Exception | None = None
        backoff = self._initial_backoff_seconds
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._put(url=url, payload=payload, headers=headers)
            except (DeliveryFailedError, UpstreamTimeoutError) as exc:
                last_error = exc
            else:
                if response.status_code == 201:
                    return DeliveryResult.SENT
                if response.status_code == 200:
                    return DeliveryResult.ALREADY_SENT
                if response.status_code in REJECTED_STATUSES:
                    raise DeliveryRejectedError(
                        f"notifier rejected delivery with status {response.status_code}"
                    )
                if response.status_code in RETRYABLE_STATUSES:
                    last_error = DeliveryFailedError(
                        f"notifier returned status {response.status_code}"
                    )
                else:
                    raise DeliveryFailedError(
                        f"notifier returned unexpected status {response.status_code}"
                    )

            if attempt < self._max_retries:
                await asyncio.sleep(backoff)
                backoff *= BACKOFF_MULTIPLIER

        if last_error is None:
            raise DeliveryFailedError("notifier call completed without a result")
        raise last_error

    @with_timeout
    async def _put(
        self,
        *,
        url: str,
        payload: dict[str, str],
        headers: dict[str, str],
    ) -> httpx.Response:
        try:
            return await self._client.put(url, json=payload, headers=headers)
        except httpx.RequestError as exc:
            raise DeliveryFailedError(f"notifier request failed: {exc}") from exc

    @staticmethod
    def _headers() -> dict[str, str]:
        headers: dict[str, str] = {}
        cid = correlation_id.get()
        if cid:
            headers[CORRELATION_ID_HEADER] = cid
        return headers
