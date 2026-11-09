import pytest
from common.departments import Department
from common.errors import DeliveryFailedError
from notifier.application.deliver import DeliveryOutcome, Notification, deliver

NOTIFICATION = Notification(
    message_id="msg-1",
    department=Department.IT,
    sender="jan.kowalski@firma.pl",
    message="Laptop nie działa",
)


async def test_sends_email_built_from_notification(sender, log):
    outcome = await deliver(NOTIFICATION, sender=sender, log=log)

    assert outcome is DeliveryOutcome.SENT
    [email] = sender.sent
    assert email["To"] == "it@example.com"
    assert email["Reply-To"] == "jan.kowalski@firma.pl"


async def test_same_message_is_not_sent_twice(sender, log):
    await deliver(NOTIFICATION, sender=sender, log=log)
    outcome = await deliver(NOTIFICATION, sender=sender, log=log)

    assert outcome is DeliveryOutcome.ALREADY_SENT
    assert len(sender.sent) == 1


async def test_failed_delivery_is_not_marked_so_it_can_be_retried(sender, log):
    sender.fail = True

    with pytest.raises(DeliveryFailedError):
        await deliver(NOTIFICATION, sender=sender, log=log)

    assert not await log.is_delivered("msg-1")
