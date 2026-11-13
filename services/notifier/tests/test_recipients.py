import pytest
from common.departments import Department
from notifier.domain.email import build_email
from notifier.domain.recipients import _RECIPIENTS, recipient_for

SENDER = "jan.kowalski@firma.pl"
FROM_ADDRESS = "router@test.local"
MESSAGE_ID = "0b6c6f5e-3f0e-4c47-9a51-6d1c1f0b9a11"


@pytest.mark.parametrize(
    ("department", "expected"),
    [
        (Department.HUMAN_RESOURCES, "human-resources@example.com"),
        (Department.HELP_DESK, "help-desk@example.com"),
        (Department.IT, "it@example.com"),
        (Department.PERSONNEL, "kadry@example.com"),
        (Department.OTHER, "other@example.com"),
    ],
)
def test_maps_department_to_address(department, expected):
    assert recipient_for(department) == expected


def test_every_department_has_a_recipient():
    for department in Department:
        assert recipient_for(department)


def test_allowlist_keys_match_department_enum():
    assert set(_RECIPIENTS.keys()) == set(Department)


@pytest.mark.parametrize("department", list(Department))
def test_builder_routes_each_department_correctly(department: Department) -> None:
    email = build_email(
        message_id=MESSAGE_ID,
        department=department,
        sender=SENDER,
        message="dowolna tresc",
        from_address=FROM_ADDRESS,
    )

    assert email["To"] == recipient_for(department)
    assert email["Reply-To"] == SENDER
    assert email["From"] == FROM_ADDRESS
