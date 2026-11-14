from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from common.departments import Department
from common.errors import AppError, ErrorCode


class MessageStatus(StrEnum):
    RECEIVED = "received"
    ROUTING = "routing"
    SENT = "sent"
    FAILED = "failed"


class InvalidMessageStateError(AppError):
    code = ErrorCode.INTERNAL_ERROR


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class Message:
    id: UUID
    sender_email: str
    body: str
    status: MessageStatus = MessageStatus.RECEIVED
    department: Department | None = None
    fallback_used: bool = False
    error_code: ErrorCode | None = None
    attempts: int = 0
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    available_at: datetime = field(default_factory=_utcnow)

    def start_routing(self, *, now: datetime) -> None:
        self._require(MessageStatus.RECEIVED, "start_routing")
        self.status = MessageStatus.ROUTING
        self.attempts += 1
        self.updated_at = now

    def mark_sent(self, department: Department, *, fallback_used: bool, now: datetime) -> None:
        self._require(MessageStatus.ROUTING, "mark_sent")
        self.status = MessageStatus.SENT
        self.department = department
        self.fallback_used = fallback_used
        self.error_code = None
        self.updated_at = now

    def mark_failed(self, error_code: ErrorCode, *, now: datetime) -> None:
        self._require(MessageStatus.ROUTING, "mark_failed")
        self.status = MessageStatus.FAILED
        self.error_code = error_code
        self.updated_at = now

    def release_for_retry(self, available_at: datetime, *, now: datetime) -> None:
        self._require(MessageStatus.ROUTING, "release_for_retry")
        self.status = MessageStatus.RECEIVED
        self.available_at = available_at
        self.updated_at = now

    def _require(self, expected: MessageStatus, action: str) -> None:
        if self.status != expected:
            raise InvalidMessageStateError(
                f"cannot {action} from status {self.status.value}: expected {expected.value}"
            )
