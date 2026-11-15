from uuid import uuid4

import httpx
import pytest
import respx
from common.departments import Department
from common.errors import DeliveryFailedError, UpstreamTimeoutError
from common.http import CORRELATION_ID_HEADER
from common.log import correlation_id
from router.adapters.http_notifier import HttpNotifier
from router.ports.notifier import DeliveryRejectedError, DeliveryResult

BASE_URL = "http://notifier:8000"
MESSAGE_ID = uuid4()
NOTIFY_URL = f"{BASE_URL}/api/v1/notifications/{MESSAGE_ID}"
DEFAULT_PAYLOAD = {
    "department": Department.IT.value,
    "sender": "alice@example.com",
    "body": "please help",
}


async def _notify(notifier: HttpNotifier) -> DeliveryResult:
    return await notifier.notify(
        message_id=MESSAGE_ID,
        department=Department.IT,
        sender_email="alice@example.com",
        body="please help",
    )


@pytest.fixture
async def notifier():
    instance = HttpNotifier(
        base_url=BASE_URL,
        timeout_seconds=1.0,
        max_retries=2,
        initial_backoff_seconds=0,
    )
    try:
        yield instance
    finally:
        await instance.aclose()


async def test_201_returns_sent(notifier: HttpNotifier) -> None:
    with respx.mock() as mock:
        mock.put(NOTIFY_URL).mock(return_value=httpx.Response(201))
        assert await _notify(notifier) == DeliveryResult.SENT


async def test_200_returns_already_sent(notifier: HttpNotifier) -> None:
    with respx.mock() as mock:
        mock.put(NOTIFY_URL).mock(return_value=httpx.Response(200))
        assert await _notify(notifier) == DeliveryResult.ALREADY_SENT


async def test_409_raises_rejected_without_retries(notifier: HttpNotifier) -> None:
    with respx.mock() as mock:
        route = mock.put(NOTIFY_URL).mock(return_value=httpx.Response(409))
        with pytest.raises(DeliveryRejectedError):
            await _notify(notifier)
        assert route.call_count == 1


async def test_422_raises_rejected_without_retries(notifier: HttpNotifier) -> None:
    with respx.mock() as mock:
        route = mock.put(NOTIFY_URL).mock(return_value=httpx.Response(422))
        with pytest.raises(DeliveryRejectedError):
            await _notify(notifier)
        assert route.call_count == 1


async def test_502_then_success(notifier: HttpNotifier) -> None:
    with respx.mock() as mock:
        route = mock.put(NOTIFY_URL).mock(side_effect=[httpx.Response(502), httpx.Response(201)])
        assert await _notify(notifier) == DeliveryResult.SENT
        assert route.call_count == 2


async def test_502_all_attempts_raises_delivery_failed(notifier: HttpNotifier) -> None:
    with respx.mock() as mock:
        route = mock.put(NOTIFY_URL).mock(return_value=httpx.Response(502))
        with pytest.raises(DeliveryFailedError):
            await _notify(notifier)
        assert route.call_count == 3


async def test_timeout_all_attempts_raises_upstream_timeout(notifier: HttpNotifier) -> None:
    with respx.mock() as mock:
        route = mock.put(NOTIFY_URL).mock(side_effect=httpx.ConnectTimeout("boom"))
        with pytest.raises((UpstreamTimeoutError, DeliveryFailedError)):
            await _notify(notifier)
        assert route.call_count == 3


async def test_connection_error_retries_then_succeeds(notifier: HttpNotifier) -> None:
    with respx.mock() as mock:
        route = mock.put(NOTIFY_URL).mock(
            side_effect=[httpx.ConnectError("boom"), httpx.Response(201)]
        )
        assert await _notify(notifier) == DeliveryResult.SENT
        assert route.call_count == 2


async def test_201_logs_notifier_call_finished_with_sent(notifier: HttpNotifier, caplog) -> None:
    import logging

    caplog.set_level(logging.INFO, logger="router.adapters.http_notifier")
    with respx.mock() as mock:
        mock.put(NOTIFY_URL).mock(return_value=httpx.Response(201))
        await _notify(notifier)

    rec = next(r for r in caplog.records if r.message == "notifier call finished")
    assert rec.levelno == logging.INFO
    assert rec.status_code == 201  # type: ignore[attr-defined]
    assert rec.outcome == "sent"  # type: ignore[attr-defined]
    assert rec.attempt == 1  # type: ignore[attr-defined]
    assert isinstance(rec.duration_ms, int)  # type: ignore[attr-defined]
    assert rec.message_id == str(MESSAGE_ID)  # type: ignore[attr-defined]


async def test_200_logs_already_sent_outcome(notifier: HttpNotifier, caplog) -> None:
    import logging

    caplog.set_level(logging.INFO, logger="router.adapters.http_notifier")
    with respx.mock() as mock:
        mock.put(NOTIFY_URL).mock(return_value=httpx.Response(200))
        await _notify(notifier)

    rec = next(r for r in caplog.records if r.message == "notifier call finished")
    assert rec.outcome == "already_sent"  # type: ignore[attr-defined]
    assert rec.status_code == 200  # type: ignore[attr-defined]


async def test_retry_on_502_logs_retry_warning(notifier: HttpNotifier, caplog) -> None:
    import logging

    caplog.set_level(logging.WARNING, logger="router.adapters.http_notifier")
    with respx.mock() as mock:
        mock.put(NOTIFY_URL).mock(side_effect=[httpx.Response(502), httpx.Response(201)])
        await _notify(notifier)

    retries = [r for r in caplog.records if r.message == "notifier call retry"]
    assert len(retries) == 1
    rec = retries[0]
    assert rec.levelno == logging.WARNING
    assert rec.status_code == 502  # type: ignore[attr-defined]
    assert rec.attempt == 1  # type: ignore[attr-defined]


async def test_retry_on_connection_error_logs_error_type(notifier: HttpNotifier, caplog) -> None:
    import logging

    caplog.set_level(logging.WARNING, logger="router.adapters.http_notifier")
    with respx.mock() as mock:
        mock.put(NOTIFY_URL).mock(side_effect=[httpx.ConnectError("boom"), httpx.Response(201)])
        await _notify(notifier)

    retries = [r for r in caplog.records if r.message == "notifier call retry"]
    assert len(retries) == 1
    assert retries[0].error_type == "DeliveryFailedError"  # type: ignore[attr-defined]


async def test_sends_correlation_header(notifier: HttpNotifier) -> None:
    token = correlation_id.set("test-correlation-id")
    try:
        with respx.mock() as mock:
            route = mock.put(NOTIFY_URL).mock(return_value=httpx.Response(201))
            await _notify(notifier)
    finally:
        correlation_id.reset(token)

    request = route.calls.last.request
    assert request.headers[CORRELATION_ID_HEADER] == "test-correlation-id"


async def test_body_contains_only_expected_fields(notifier: HttpNotifier) -> None:
    with respx.mock() as mock:
        route = mock.put(NOTIFY_URL).mock(return_value=httpx.Response(201))
        await _notify(notifier)

    import json

    sent = json.loads(route.calls.last.request.content)
    assert sent == DEFAULT_PAYLOAD
