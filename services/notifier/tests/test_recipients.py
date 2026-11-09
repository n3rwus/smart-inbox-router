import pytest
from common.departments import Department
from notifier.domain.recipients import recipient_for


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
