import asyncio
import logging
import time
from uuid import UUID

import httpx
from common.departments import Department
from common.errors import DeliveryFailedError, UpstreamTimeoutError
from common.http import CORRELATION_ID_HEADER
from common.log import correlation_id
from common.timeouts import with_timeout

from router.ports.notifier import DeliveryRejectedError, DeliveryResult

_log = logging.getLogger(__name__)

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
        message_id_str = str(message_id)
        for attempt in range(1, self._max_retries + 2):
            started = time.monotonic()
            status_code: int | None = None
            outcome: DeliveryResult | None = None
            retry_error_type: str | None = None
            try:
                response = await self._put(url=url, payload=payload, headers=headers)
            except (DeliveryFailedError, UpstreamTimeoutError) as exc:
                last_error = exc
                retry_error_type = type(exc).__name__
            else:
                status_code = response.status_code
                if response.status_code == 201:
                    outcome = DeliveryResult.SENT
                elif response.status_code == 200:
                    outcome = DeliveryResult.ALREADY_SENT
                elif response.status_code in REJECTED_STATUSES:
                    self._log_finished(
                        message_id_str, status_code, None, attempt, started, "rejected"
                    )
                    raise DeliveryRejectedError(
                        f"notifier rejected delivery with status {response.status_code}"
                    )
                elif response.status_code in RETRYABLE_STATUSES:
                    last_error = DeliveryFailedError(
                        f"notifier returned status {response.status_code}"
                    )
                else:
                    self._log_finished(
                        message_id_str, status_code, None, attempt, started, "failed"
                    )
                    raise DeliveryFailedError(
                        f"notifier returned unexpected status {response.status_code}"
                    )

            if outcome is not None:
                self._log_finished(
                    message_id_str, status_code, outcome, attempt, started, outcome.value
                )
                return outcome

            if attempt <= self._max_retries:
                _log.warning(
                    "notifier call retry",
                    extra={
                        "message_id": message_id_str,
                        "attempt": attempt,
                        **({"status_code": status_code} if status_code is not None else {}),
                        **({"error_type": retry_error_type} if retry_error_type else {}),
                    },
                )
                await asyncio.sleep(backoff)
                backoff *= BACKOFF_MULTIPLIER

        self._log_finished(message_id_str, None, None, self._max_retries + 1, started, "failed")
        if last_error is None:
            raise DeliveryFailedError("notifier call completed without a result")
        raise last_error

    @staticmethod
    def _log_finished(
        message_id_str: str,
        status_code: int | None,
        outcome: DeliveryResult | None,
        attempt: int,
        started: float,
        outcome_label: str,
    ) -> None:
        extra: dict[str, object] = {
            "message_id": message_id_str,
            "attempt": attempt,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "outcome": outcome_label,
        }
        if status_code is not None:
            extra["status_code"] = status_code
        _log.info("notifier call finished", extra=extra)

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
