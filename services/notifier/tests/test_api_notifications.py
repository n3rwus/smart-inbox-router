import httpx
import pytest
from common.errors import DeliveryFailedError, UpstreamTimeoutError
from common.http import PROBLEM_JSON_MEDIA_TYPE
from fastapi import status
from notifier.api.app import create_app
from notifier.api.notifications import NOTIFICATIONS_PATH, DeliverHandler, get_deliver
from notifier.application.deliver import DeliveryOutcome, Notification

TEST_BASE_URL = "http://notifier.test"
ENDPOINT_URL = f"/api/v1{NOTIFICATIONS_PATH}"
PAYLOAD = {
    "message_id": "0b6c6f5e-3f0e-4c47-9a51-6d1c1f0b9a11",
    "department": "it",
    "sender": "jan.kowalski@firma.pl",
    "body": "Laptop nie dziala",
}


def _record_calls() -> tuple[list[Notification], DeliverHandler]:
    calls: list[Notification] = []

    async def deliver(notification: Notification) -> DeliveryOutcome:
        calls.append(notification)
        return DeliveryOutcome.SENT

    return calls, deliver


def _failing(error: Exception) -> DeliverHandler:
    async def deliver(_notification: Notification) -> DeliveryOutcome:
        raise error

    return deliver


async def _post(deliver: DeliverHandler, payload: dict | None = None) -> httpx.Response:
    app = create_app()
    app.dependency_overrides[get_deliver] = lambda: deliver
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=TEST_BASE_URL) as client:
        return await client.post(ENDPOINT_URL, json=payload if payload is not None else PAYLOAD)


async def test_accepted_delivery_returns_no_content() -> None:
    calls, deliver = _record_calls()

    response = await _post(deliver)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.content == b""
    [notification] = calls
    assert notification.message_id == PAYLOAD["message_id"]
    assert notification.sender == PAYLOAD["sender"]


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (DeliveryFailedError("smtp down"), status.HTTP_502_BAD_GATEWAY),
        (UpstreamTimeoutError("smtp slow"), status.HTTP_504_GATEWAY_TIMEOUT),
    ],
)
async def test_delivery_errors_map_to_gateway_statuses(
    error: Exception, expected_status: int
) -> None:
    response = await _post(_failing(error))

    assert response.status_code == expected_status
    assert response.headers["content-type"].startswith(PROBLEM_JSON_MEDIA_TYPE)


async def test_crlf_in_message_id_is_rejected() -> None:
    calls, deliver = _record_calls()
    bad_payload = dict(PAYLOAD, message_id="msg-1\r\nX-Evil: 1")

    response = await _post(deliver, payload=bad_payload)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert not calls
