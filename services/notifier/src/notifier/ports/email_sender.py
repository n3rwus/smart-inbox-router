from email.message import EmailMessage
from typing import Protocol


class EmailSender(Protocol):
    async def send(self, email: EmailMessage) -> None:
        """Deliver the email. Raise DeliveryFailedError on failure."""
