from common.departments import Department
from router.domain.departments import DEPARTMENT_DESCRIPTIONS


def test_catalog_keys_match_department_enum() -> None:
    assert set(DEPARTMENT_DESCRIPTIONS.keys()) == set(Department)


def test_every_description_is_non_empty() -> None:
    for text in DEPARTMENT_DESCRIPTIONS.values():
        assert text.strip()
