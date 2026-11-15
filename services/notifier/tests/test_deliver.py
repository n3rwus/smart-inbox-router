import pytest
from common.departments import Department
from common.errors import DeliveryFailedError, IdempotencyConflictError
from notifier.application.deliver import DeliveryOutcome, Notification, deliver

MESSAGE_ID = "6f7ec47c-6f3a-4b83-a3b5-7c1a7a1aa5c1"
FROM_ADDRESS = "router@test.local"
NOTIFICATION = Notification(
    message_id=MESSAGE_ID,
    department=Department.IT,
    sender="jan.kowalski@firma.pl",
    message="Laptop nie działa",
)


async def test_sends_email_built_from_notification(sender, log):
    outcome = await deliver(NOTIFICATION, sender=sender, log=log, from_address=FROM_ADDRESS)

    assert outcome is DeliveryOutcome.SENT
    [email] = sender.sent
    assert email["To"] == "it@example.com"
    assert email["Reply-To"] == "jan.kowalski@firma.pl"


async def test_replay_with_identical_content_is_not_sent_twice(sender, log):
    await deliver(NOTIFICATION, sender=sender, log=log, from_address=FROM_ADDRESS)
    outcome = await deliver(NOTIFICATION, sender=sender, log=log, from_address=FROM_ADDRESS)

    assert outcome is DeliveryOutcome.ALREADY_SENT
    assert len(sender.sent) == 1


async def test_same_id_different_body_raises_idempotency_conflict(sender, log):
    await deliver(NOTIFICATION, sender=sender, log=log, from_address=FROM_ADDRESS)

    different = Notification(
        message_id=MESSAGE_ID,
        department=Department.IT,
        sender="jan.kowalski@firma.pl",
        message="A tu zupełnie inna treść",
    )
    with pytest.raises(IdempotencyConflictError):
        await deliver(different, sender=sender, log=log, from_address=FROM_ADDRESS)

    assert len(sender.sent) == 1


async def test_logs_only_safe_fields(sender, log, caplog):
    import logging

    with caplog.at_level(logging.INFO, logger="notifier.application.deliver"):
        await deliver(NOTIFICATION, sender=sender, log=log, from_address=FROM_ADDRESS)

    [record] = caplog.records
    assert record.message_id == MESSAGE_ID
    assert record.department == "it"
    assert record.outcome == "sent"
    assert "Laptop" not in record.getMessage()
    assert "jan.kowalski" not in record.getMessage()


async def test_failed_delivery_is_not_recorded_so_retry_sends_fresh(sender, log):
    sender.fail = True

    with pytest.raises(DeliveryFailedError):
        await deliver(NOTIFICATION, sender=sender, log=log, from_address=FROM_ADDRESS)

    assert await log.stored_hash(MESSAGE_ID) is None

    sender.fail = False
    outcome = await deliver(NOTIFICATION, sender=sender, log=log, from_address=FROM_ADDRESS)

    assert outcome is DeliveryOutcome.SENT
    assert len(sender.sent) == 1
