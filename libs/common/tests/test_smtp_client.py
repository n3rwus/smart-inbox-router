from email import message_from_bytes, policy
from email.message import EmailMessage

import pytest
from aiosmtpd.controller import Controller
from common.email_headers import EmailHeader
from common.errors import DeliveryFailedError, UpstreamTimeoutError
from common.smtp import SmtpClient, SmtpConfig

from .conftest import LOOPBACK_HOST, CapturingHandler

FROM_ADDRESS = "router@test.local"
RECIPIENT = "it@example.com"
REPLY_TO = "jan.kowalski@firma.pl"
BODY = "Laptop nie dziala"
FAST_TIMEOUT_SECONDS = 0.5


def _email() -> EmailMessage:
    email = EmailMessage()
    email[EmailHeader.FROM] = FROM_ADDRESS
    email[EmailHeader.TO] = RECIPIENT
    email[EmailHeader.REPLY_TO] = REPLY_TO
    email.set_content(BODY)
    return email


def _client(host: str, port: int) -> SmtpClient:
    return SmtpClient(SmtpConfig(host=host, port=port, timeout_seconds=FAST_TIMEOUT_SECONDS))


async def test_delivers_email_and_preserves_reply_to(
    smtp_server: tuple[Controller, CapturingHandler],
) -> None:
    controller, handler = smtp_server
    await _client(controller.hostname, controller.port).send(_email())

    [envelope] = handler.envelopes
    received = message_from_bytes(envelope.content, policy=policy.default)  # type: ignore[arg-type]
    assert received[EmailHeader.REPLY_TO] == REPLY_TO
    assert received.get_content().strip() == BODY


async def test_reply_to_is_not_an_envelope_recipient(
    smtp_server: tuple[Controller, CapturingHandler],
) -> None:
    controller, handler = smtp_server
    await _client(controller.hostname, controller.port).send(_email())

    [envelope] = handler.envelopes
    assert envelope.rcpt_tos == [RECIPIENT]


async def test_refused_connection_raises_delivery_failed(closed_port: int) -> None:
    with pytest.raises(DeliveryFailedError):
        await _client(LOOPBACK_HOST, closed_port).send(_email())


async def test_silent_server_raises_upstream_timeout(silent_server: tuple[str, int]) -> None:
    host, port = silent_server
    with pytest.raises(UpstreamTimeoutError):
        await _client(host, port).send(_email())
