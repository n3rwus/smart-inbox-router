import asyncio

import pytest
from common.departments import Department
from notifier.adapters.in_memory_delivery_log import InMemoryDeliveryLog
from notifier.application.deliver import DeliveryOutcome, Notification, deliver

from .conftest import InMemoryEmailSender

MESSAGE_ID = "msg-1"
CONCURRENT_CALLS = 8
FROM_ADDRESS = "router@test.local"


CONTENT_HASH = "abc" * 21 + "def"


async def test_new_id_has_no_stored_hash() -> None:
    log = InMemoryDeliveryLog()

    assert await log.stored_hash(MESSAGE_ID) is None


async def test_record_then_stored_hash_returns_it() -> None:
    log = InMemoryDeliveryLog()

    await log.record(MESSAGE_ID, CONTENT_HASH)

    assert await log.stored_hash(MESSAGE_ID) == CONTENT_HASH


async def test_different_ids_do_not_share_state() -> None:
    log = InMemoryDeliveryLog()

    await log.record(MESSAGE_ID, CONTENT_HASH)

    assert await log.stored_hash("msg-2") is None


async def test_lock_serializes_same_id_sections() -> None:
    log = InMemoryDeliveryLog()
    order: list[str] = []

    async def section(name: str) -> None:
        async with log.lock(MESSAGE_ID):
            order.append(f"{name}:in")
            await asyncio.sleep(0)
            order.append(f"{name}:out")

    await asyncio.gather(section("a"), section("b"))

    assert order in (["a:in", "a:out", "b:in", "b:out"], ["b:in", "b:out", "a:in", "a:out"])


async def test_concurrent_deliver_sends_exactly_one_email() -> None:
    log = InMemoryDeliveryLog()
    sender = InMemoryEmailSender()
    notification = Notification(
        message_id=MESSAGE_ID,
        department=Department.IT,
        sender="jan.kowalski@firma.pl",
        message="Laptop nie dziala",
    )

    outcomes = await asyncio.gather(
        *(
            deliver(notification, sender=sender, log=log, from_address=FROM_ADDRESS)
            for _ in range(CONCURRENT_CALLS)
        )
    )

    assert len(sender.sent) == 1
    assert outcomes.count(DeliveryOutcome.SENT) == 1
    assert outcomes.count(DeliveryOutcome.ALREADY_SENT) == CONCURRENT_CALLS - 1


@pytest.mark.parametrize("message_id", ["a", "b", "c"])
async def test_lock_is_reentrant_across_contexts(message_id: str) -> None:
    log = InMemoryDeliveryLog()

    async with log.lock(message_id):
        pass
    async with log.lock(message_id):
        pass
