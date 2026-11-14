from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from common.departments import Department
from common.errors import ErrorCode
from router.domain.message import InvalidMessageStateError, Message, MessageStatus


def _message(**overrides: object) -> Message:
    base = datetime(2026, 11, 13, 10, 0, tzinfo=UTC)
    defaults: dict[str, object] = {
        "id": uuid4(),
        "sender_email": "alice@example.com",
        "body": "hello",
        "created_at": base,
        "updated_at": base,
        "available_at": base,
    }
    defaults.update(overrides)
    return Message(**defaults)  # type: ignore[arg-type]


def test_received_to_routing_increments_attempts() -> None:
    now = datetime(2026, 11, 13, 10, 5, tzinfo=UTC)
    message = _message()
    message.start_routing(now=now)
    assert message.status == MessageStatus.ROUTING
    assert message.attempts == 1
    assert message.updated_at == now


def test_cannot_start_routing_from_routing() -> None:
    message = _message()
    message.start_routing(now=datetime(2026, 11, 13, 10, 5, tzinfo=UTC))
    with pytest.raises(InvalidMessageStateError):
        message.start_routing(now=datetime(2026, 11, 13, 10, 6, tzinfo=UTC))


def test_mark_sent_requires_routing() -> None:
    message = _message()
    with pytest.raises(InvalidMessageStateError):
        message.mark_sent(
            Department.IT, fallback_used=False, now=datetime(2026, 11, 13, 10, 6, tzinfo=UTC)
        )


def test_mark_sent_sets_department_and_clears_error() -> None:
    message = _message()
    message.start_routing(now=datetime(2026, 11, 13, 10, 5, tzinfo=UTC))
    message.error_code = ErrorCode.ROUTING_FAILED
    message.mark_sent(
        Department.HELP_DESK,
        fallback_used=True,
        now=datetime(2026, 11, 13, 10, 6, tzinfo=UTC),
    )
    assert message.status == MessageStatus.SENT
    assert message.department is Department.HELP_DESK
    assert message.fallback_used is True
    assert message.error_code is None


def test_mark_failed_requires_routing() -> None:
    message = _message()
    with pytest.raises(InvalidMessageStateError):
        message.mark_failed(ErrorCode.ROUTING_FAILED, now=datetime(2026, 11, 13, 10, 6, tzinfo=UTC))


def test_mark_failed_records_error_code() -> None:
    message = _message()
    message.start_routing(now=datetime(2026, 11, 13, 10, 5, tzinfo=UTC))
    message.mark_failed(ErrorCode.LLM_UNAVAILABLE, now=datetime(2026, 11, 13, 10, 7, tzinfo=UTC))
    assert message.status == MessageStatus.FAILED
    assert message.error_code is ErrorCode.LLM_UNAVAILABLE


def test_release_for_retry_returns_to_received() -> None:
    message = _message()
    message.start_routing(now=datetime(2026, 11, 13, 10, 5, tzinfo=UTC))
    retry_at = datetime(2026, 11, 13, 10, 10, tzinfo=UTC)
    message.release_for_retry(retry_at, now=datetime(2026, 11, 13, 10, 6, tzinfo=UTC))
    assert message.status == MessageStatus.RECEIVED
    assert message.available_at == retry_at


def test_release_for_retry_requires_routing() -> None:
    message = _message()
    with pytest.raises(InvalidMessageStateError):
        message.release_for_retry(
            datetime(2026, 11, 13, 10, 10, tzinfo=UTC),
            now=datetime(2026, 11, 13, 10, 6, tzinfo=UTC),
        )


def test_sent_is_terminal() -> None:
    message = _message()
    message.start_routing(now=datetime(2026, 11, 13, 10, 5, tzinfo=UTC))
    message.mark_sent(
        Department.IT, fallback_used=False, now=datetime(2026, 11, 13, 10, 6, tzinfo=UTC)
    )
    with pytest.raises(InvalidMessageStateError):
        message.start_routing(now=datetime(2026, 11, 13, 10, 7, tzinfo=UTC))


def test_second_claim_increments_attempts_again() -> None:
    message = _message()
    now = datetime(2026, 11, 13, 10, 5, tzinfo=UTC)
    message.start_routing(now=now)
    message.release_for_retry(now + timedelta(minutes=1), now=now)
    message.start_routing(now=now + timedelta(minutes=2))
    assert message.attempts == 2
