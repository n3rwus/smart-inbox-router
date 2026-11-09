import pytest
from notifier.config import NotifierSettings
from pydantic import ValidationError


def test_defaults_point_to_compose_services():
    settings = NotifierSettings(_env_file=None)
    assert settings.smtp_host == "mailhog"
    assert settings.smtp_port == 1025


def test_reads_prefixed_env(monkeypatch):
    monkeypatch.setenv("NOTIFIER_SMTP_PORT", "2525")
    assert NotifierSettings(_env_file=None).smtp_port == 2525


def test_invalid_value_fails_fast(monkeypatch):
    monkeypatch.setenv("NOTIFIER_SMTP_PORT", "abc")
    with pytest.raises(ValidationError):
        NotifierSettings(_env_file=None)
