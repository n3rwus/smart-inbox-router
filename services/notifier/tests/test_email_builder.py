import pytest
from common.departments import Department
from notifier.domain.email import build_email

SENDER = "jan.kowalski@firma.pl"


def _build(**overrides):
    kwargs = {"department": Department.IT, "sender": SENDER, "message": "Laptop nie działa"}
    return build_email(**(kwargs | overrides))


def test_to_is_resolved_from_department():
    assert _build()["To"] == "it@example.com"


def test_reply_to_is_original_sender():
    assert _build()["Reply-To"] == SENDER


def test_body_is_message_verbatim():
    assert _build(message="zażółć\nlinia 2").get_content().strip() == "zażółć\nlinia 2"


def test_subject_does_not_contain_user_text():
    assert "Laptop" not in _build()["Subject"]


def test_rejects_header_injection_in_sender():
    with pytest.raises(ValueError):
        _build(sender="a@b.com\r\nBcc: evil@x.com")
