import httpx
import pytest
from common.departments import Department
from common.email_headers import EmailHeader
from common.smtp import SmtpClient, SmtpConfig
from notifier.domain.email import MESSAGE_ID_DOMAIN, build_email
from notifier.domain.recipients import recipient_for

from .settings import (
    CONTENT_KEY,
    HEADERS_KEY,
    ITEMS_KEY,
    MESSAGES_V1_PATH,
    MESSAGES_V2_PATH,
    MailhogSettings,
)

pytestmark = pytest.mark.integration

MESSAGE_ID = "4e0f0a21-5f1a-4e4a-9a3e-3b2fc0d7c111"
DEPARTMENT = Department.HELP_DESK
SENDER = "jan.kowalski@firma.pl"
FROM_ADDRESS = "router@test.local"
BODY = "Drukarka nie drukuje"


async def test_email_lands_in_mailhog_with_reply_to() -> None:
    mailhog = MailhogSettings()
    smtp = SmtpClient(
        SmtpConfig(
            host=mailhog.smtp_host,
            port=mailhog.smtp_port,
            timeout_seconds=mailhog.timeout_seconds,
        )
    )

    async with httpx.AsyncClient(base_url=mailhog.api_url, timeout=mailhog.timeout_seconds) as api:
        await api.delete(MESSAGES_V1_PATH)
        await smtp.send(
            build_email(
                message_id=MESSAGE_ID,
                department=DEPARTMENT,
                sender=SENDER,
                message=BODY,
                from_address=FROM_ADDRESS,
            )
        )
        response = await api.get(MESSAGES_V2_PATH)
        response.raise_for_status()

    [item] = response.json()[ITEMS_KEY]
    headers = item[CONTENT_KEY][HEADERS_KEY]
    assert headers[EmailHeader.TO] == [recipient_for(DEPARTMENT)]
    assert headers[EmailHeader.REPLY_TO] == [SENDER]
    assert headers[EmailHeader.MESSAGE_ID] == [f"<{MESSAGE_ID}@{MESSAGE_ID_DOMAIN}>"]
