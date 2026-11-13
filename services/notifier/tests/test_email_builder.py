import pytest
from common.departments import Department
from notifier.domain.email import MESSAGE_ID_DOMAIN, build_email

SENDER = "jan.kowalski@firma.pl"
MESSAGE_ID = "0b6c6f5e-3f0e-4c47-9a51-6d1c1f0b9a11"


def _build(**overrides):
    kwargs = {
        "message_id": MESSAGE_ID,
        "department": Department.IT,
        "sender": SENDER,
        "message": "Laptop nie działa",
        "from_address": "router@test.local",
    }
    return build_email(**(kwargs | overrides))


def test_to_is_resolved_from_department():
    assert _build()["To"] == "it@example.com"


def test_from_is_configurable():
    assert _build()["From"] == "router@test.local"


def test_reply_to_is_original_sender():
    assert _build()["Reply-To"] == SENDER


def test_body_is_message_verbatim():
    assert _build(message="zażółć\nlinia 2").get_content().strip() == "zażółć\nlinia 2"


def test_subject_does_not_contain_user_text():
    assert "Laptop" not in _build()["Subject"]


def test_subject_depends_only_on_department():
    first = _build(message="pierwsza tresc")["Subject"]
    second = _build(message="zupelnie inna tresc", sender="other@example.com")["Subject"]
    assert first == second
    assert str(Department.IT) in first
    assert "\r" not in first and "\n" not in first


def test_rejects_header_injection_in_sender():
    with pytest.raises(ValueError):
        _build(sender="a@b.com\r\nBcc: evil@x.com")


def test_body_cannot_inject_headers():
    email = _build(message="hello\r\nSubject: evil\r\nBcc: x@evil.com")

    assert email.get_all("Subject") == [email["Subject"]]
    assert "evil" not in email["Subject"]
    assert email["Bcc"] is None
    assert "Subject: evil" in email.get_content()
    assert "Bcc: x@evil.com" in email.get_content()


def test_message_id_is_deterministic_per_message_id():
    first = _build()["Message-ID"]
    second = _build(sender="inny@example.com", message="inna tresc")["Message-ID"]

    assert first == second
    assert first == f"<{MESSAGE_ID}@{MESSAGE_ID_DOMAIN}>"


def test_message_id_changes_with_message_id():
    other = "7f3c2a1e-9b4d-4e6f-8a21-0d5b6f7c1234"
    assert _build(message_id=other)["Message-ID"] == f"<{other}@{MESSAGE_ID_DOMAIN}>"
