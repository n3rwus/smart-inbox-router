from common.departments import Department


def test_has_exactly_the_allowed_departments():
    assert {d.value for d in Department} == {
        "human-resources",
        "help-desk",
        "it",
        "kadry",
        "other",
    }


def test_is_a_string_enum():
    assert Department.IT == "it"
