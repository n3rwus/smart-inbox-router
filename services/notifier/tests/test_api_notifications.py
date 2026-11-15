from collections.abc import Awaitable, Callable

import httpx
import pytest
from common.errors import DeliveryFailedError, IdempotencyConflictError, UpstreamTimeoutError
from common.http import API_V1_PREFIX, PROBLEM_JSON_MEDIA_TYPE
from fastapi import status
from notifier.api.app import create_app
from notifier.api.notifications import NOTIFICATIONS_PATH, get_deliver
from notifier.application.deliver import DeliveryOutcome, Notification
from notifier.config import NotifierSettings

TEST_BASE_URL = "http://notifier.test"
MESSAGE_ID = "0b6c6f5e-3f0e-4c47-9a51-6d1c1f0b9a11"
ENDPOINT_URL = f"{API_V1_PREFIX}{NOTIFICATIONS_PATH}/{MESSAGE_ID}"
BODY = {
    "department": "it",
    "sender": "jan.kowalski@firma.pl",
    "body": "Laptop nie dziala",
}

Deliver = Callable[[Notification], Awaitable[DeliveryOutcome]]


def _recording(
    outcome: DeliveryOutcome = DeliveryOutcome.SENT,
) -> tuple[list[Notification], Deliver]:
    calls: list[Notification] = []

    async def deliver(notification: Notification) -> DeliveryOutcome:
        calls.append(notification)
        return outcome

    return calls, deliver


def _failing(error: Exception) -> Deliver:
    async def deliver(_notification: Notification) -> DeliveryOutcome:
        raise error

    return deliver


async def _put(
    deliver: Deliver, url: str = ENDPOINT_URL, body: dict | None = None
) -> httpx.Response:
    app = create_app(NotifierSettings(_env_file=None))
    app.dependency_overrides[get_deliver] = lambda: deliver
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=TEST_BASE_URL) as client:
        return await client.put(url, json=body if body is not None else BODY)


async def test_fresh_delivery_returns_201_with_location() -> None:
    calls, deliver = _recording(DeliveryOutcome.SENT)

    response = await _put(deliver)

    assert response.status_code == status.HTTP_201_CREATED
    assert response.headers["Location"] == ENDPOINT_URL
    [notification] = calls
    assert notification.message_id == MESSAGE_ID
    assert notification.sender == BODY["sender"]


async def test_replay_returns_200() -> None:
    _, deliver = _recording(DeliveryOutcome.ALREADY_SENT)

    response = await _put(deliver)

    assert response.status_code == status.HTTP_200_OK
    assert "Location" not in response.headers


async def test_idempotency_conflict_returns_409_problem_details() -> None:
    response = await _put(_failing(IdempotencyConflictError("different body")))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.headers["content-type"].startswith(PROBLEM_JSON_MEDIA_TYPE)
    assert response.json()["code"] == "idempotency_conflict"


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
    response = await _put(_failing(error))

    assert response.status_code == expected_status
    assert response.headers["content-type"].startswith(PROBLEM_JSON_MEDIA_TYPE)


async def test_non_uuid_message_id_is_rejected_with_422() -> None:
    calls, deliver = _recording()
    bad_url = f"{API_V1_PREFIX}{NOTIFICATIONS_PATH}/not-a-uuid"

    response = await _put(deliver, url=bad_url)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert not calls


async def test_sender_with_crlf_is_rejected_with_422() -> None:
    calls, deliver = _recording()

    response = await _put(
        deliver,
        body={
            "department": "it",
            "sender": "jan@firma.pl\r\nBcc: evil@x.com",
            "body": "cokolwiek",
        },
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.headers["content-type"].startswith(PROBLEM_JSON_MEDIA_TYPE)
    assert response.json()["code"] == "validation_failed"
    assert not calls


async def test_422_response_does_not_leak_user_input() -> None:
    calls, deliver = _recording()
    leaky_sender = "leak-me@@x"
    leaky_body = "secret-body-value-xyz"

    response = await _put(
        deliver,
        body={"department": "it", "sender": leaky_sender, "body": leaky_body},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.headers["content-type"].startswith(PROBLEM_JSON_MEDIA_TYPE)
    text = response.text
    assert leaky_sender not in text
    assert "leak-me" not in text
    body = response.json()
    assert body["code"] == "validation_failed"
    assert not calls
