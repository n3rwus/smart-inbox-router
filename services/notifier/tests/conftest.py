from email.message import EmailMessage

import pytest
from common.errors import DeliveryFailedError
from notifier.adapters.in_memory_delivery_log import InMemoryDeliveryLog


class InMemoryEmailSender:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []
        self.fail = False

    async def send(self, email: EmailMessage) -> None:
        if self.fail:
            raise DeliveryFailedError("simulated SMTP failure")
        self.sent.append(email)


@pytest.fixture
def sender() -> InMemoryEmailSender:
    return InMemoryEmailSender()


@pytest.fixture
def log() -> InMemoryDeliveryLog:
    return InMemoryDeliveryLog()
