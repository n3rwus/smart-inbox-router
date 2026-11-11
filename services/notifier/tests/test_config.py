import pytest
from common.smtp import SmtpConfig
from notifier.config import NotifierSettings
from pydantic import ValidationError

OVERRIDDEN_SMTP_HOST = "mailhog"
OVERRIDDEN_SMTP_PORT = 2525


def test_smtp_defaults_equal_shared_config():
    assert NotifierSettings(_env_file=None).smtp == SmtpConfig()


def test_smtp_from_nested_env(monkeypatch):
    monkeypatch.setenv("NOTIFIER_SMTP__HOST", OVERRIDDEN_SMTP_HOST)
    monkeypatch.setenv("NOTIFIER_SMTP__PORT", str(OVERRIDDEN_SMTP_PORT))

    smtp = NotifierSettings(_env_file=None).smtp
    assert (smtp.host, smtp.port) == (OVERRIDDEN_SMTP_HOST, OVERRIDDEN_SMTP_PORT)


def test_invalid_port_fails_fast(monkeypatch):
    monkeypatch.setenv("NOTIFIER_SMTP__PORT", "abc")
    with pytest.raises(ValidationError):
        NotifierSettings(_env_file=None)
