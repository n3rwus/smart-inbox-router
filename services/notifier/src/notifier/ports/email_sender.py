from collections.abc import Awaitable
from email.message import EmailMessage
from typing import Protocol


class EmailSender(Protocol):
    def send(self, email: EmailMessage) -> Awaitable[None]:
        """Deliver the email. Raise DeliveryFailedError on failure."""
