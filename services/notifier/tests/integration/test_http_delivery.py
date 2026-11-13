import httpx
import pytest
from common.departments import Department
from common.email_headers import EmailHeader
from common.http import API_V1_PREFIX
from fastapi import status
from notifier.api.notifications import NOTIFICATIONS_PATH
from notifier.domain.recipients import recipient_for

from .settings import (
    CONTENT_KEY,
    HEADERS_KEY,
    ITEMS_KEY,
    MESSAGES_V1_PATH,
    MESSAGES_V2_PATH,
    MailhogSettings,
    NotifierClientSettings,
)

pytestmark = pytest.mark.integration

MESSAGE_ID = "7f3c2a1e-9b4d-4e6f-8a21-0d5b6f7c1234"
DEPARTMENT = Department.HELP_DESK
SENDER = "jan.kowalski@firma.pl"
BODY = {"department": DEPARTMENT.value, "sender": SENDER, "body": "Drukarka nie drukuje"}
CONFLICTING_BODY = {**BODY, "body": "A tutaj zupelnie inne"}


def _url(message_id: str) -> str:
    return f"{API_V1_PREFIX}{NOTIFICATIONS_PATH}/{message_id}"


async def test_put_delivers_replays_and_rejects_conflicts() -> None:
    mailhog = MailhogSettings()
    notifier = NotifierClientSettings()

    async with httpx.AsyncClient(base_url=mailhog.api_url, timeout=mailhog.timeout_seconds) as api:
        await api.delete(MESSAGES_V1_PATH)

    async with httpx.AsyncClient(
        base_url=str(notifier.notifier_base_url).rstrip("/"),
        timeout=notifier.timeout_seconds,
    ) as client:
        first = await client.put(_url(MESSAGE_ID), json=BODY)
        second = await client.put(_url(MESSAGE_ID), json=BODY)
        conflict = await client.put(_url(MESSAGE_ID), json=CONFLICTING_BODY)

    assert first.status_code == status.HTTP_201_CREATED
    assert first.headers["Location"] == _url(MESSAGE_ID)
    assert second.status_code == status.HTTP_200_OK
    assert conflict.status_code == status.HTTP_409_CONFLICT
    assert conflict.json()["code"] == "idempotency_conflict"

    async with httpx.AsyncClient(base_url=mailhog.api_url, timeout=mailhog.timeout_seconds) as api:
        response = await api.get(MESSAGES_V2_PATH)
    response.raise_for_status()
    items = response.json()[ITEMS_KEY]

    assert len(items) == 1
    headers = items[0][CONTENT_KEY][HEADERS_KEY]
    assert headers[EmailHeader.TO] == [recipient_for(DEPARTMENT)]
    assert headers[EmailHeader.REPLY_TO] == [SENDER]
