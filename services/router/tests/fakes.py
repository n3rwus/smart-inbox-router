from dataclasses import dataclass
from uuid import UUID

from common.departments import Department
from router.ports.notifier import DeliveryResult


@dataclass
class NotifierCall:
    message_id: UUID
    department: Department
    sender_email: str
    body: str


class FakeNotifier:
    def __init__(
        self,
        *,
        result: DeliveryResult = DeliveryResult.SENT,
        error: Exception | None = None,
    ) -> None:
        self.calls: list[NotifierCall] = []
        self.result = result
        self.error = error

    async def notify(
        self,
        *,
        message_id: UUID,
        department: Department,
        sender_email: str,
        body: str,
    ) -> DeliveryResult:
        self.calls.append(
            NotifierCall(
                message_id=message_id,
                department=department,
                sender_email=sender_email,
                body=body,
            )
        )
        if self.error is not None:
            raise self.error
        return self.result
