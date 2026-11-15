import socket
from collections.abc import Iterator

import pytest
from aiosmtpd.controller import Controller
from aiosmtpd.smtp import SMTP, Envelope, Session

LOOPBACK_HOST = "127.0.0.1"
EPHEMERAL_PORT = 0
SMTP_ACCEPTED_REPLY = "250 Message accepted"


class CapturingHandler:
    def __init__(self) -> None:
        self.envelopes: list[Envelope] = []

    async def handle_DATA(self, _server: SMTP, _session: Session, envelope: Envelope) -> str:
        self.envelopes.append(envelope)
        return SMTP_ACCEPTED_REPLY


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind((LOOPBACK_HOST, EPHEMERAL_PORT))
        return int(sock.getsockname()[1])


@pytest.fixture
def smtp_server() -> Iterator[tuple[Controller, CapturingHandler]]:
    handler = CapturingHandler()
    controller = Controller(handler, hostname=LOOPBACK_HOST, port=_free_port())
    controller.start()
    try:
        yield controller, handler
    finally:
        controller.stop()


@pytest.fixture
def closed_port() -> int:
    return _free_port()


@pytest.fixture
def silent_server() -> Iterator[tuple[str, int]]:
    """Accepts TCP connections but never sends the SMTP greeting."""
    sock = socket.socket()
    sock.bind((LOOPBACK_HOST, EPHEMERAL_PORT))
    sock.listen()
    try:
        yield LOOPBACK_HOST, int(sock.getsockname()[1])
    finally:
        sock.close()
