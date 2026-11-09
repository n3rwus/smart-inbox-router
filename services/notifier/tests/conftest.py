from email.message import EmailMessage

import pytest
from common.errors import DeliveryFailedError


class InMemoryEmailSender:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []
        self.fail = False

    async def send(self, email: EmailMessage) -> None:
        if self.fail:
            raise DeliveryFailedError("simulated SMTP failure")
        self.sent.append(email)


class InMemoryDeliveryLog:
    def __init__(self) -> None:
        self.delivered: set[str] = set()

    async def is_delivered(self, message_id: str) -> bool:
        return message_id in self.delivered

    async def mark_delivered(self, message_id: str) -> None:
        self.delivered.add(message_id)


@pytest.fixture
def sender() -> InMemoryEmailSender:
    return InMemoryEmailSender()


@pytest.fixture
def log() -> InMemoryDeliveryLog:
    return InMemoryDeliveryLog()
