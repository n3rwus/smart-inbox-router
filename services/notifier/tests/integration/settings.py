from pydantic import HttpUrl, PositiveFloat
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_MAILHOG_API_URL = "http://localhost:8025/api"
DEFAULT_MAILHOG_SMTP_HOST = "localhost"
DEFAULT_MAILHOG_SMTP_PORT = 1025
DEFAULT_MAILHOG_TIMEOUT_SECONDS = 5.0

MESSAGES_V1_PATH = "/v1/messages"
MESSAGES_V2_PATH = "/v2/messages"
ITEMS_KEY = "items"
CONTENT_KEY = "Content"
HEADERS_KEY = "Headers"


class MailhogSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MAILHOG_")

    api_url: str = DEFAULT_MAILHOG_API_URL
    smtp_host: str = DEFAULT_MAILHOG_SMTP_HOST
    smtp_port: int = DEFAULT_MAILHOG_SMTP_PORT
    timeout_seconds: PositiveFloat = DEFAULT_MAILHOG_TIMEOUT_SECONDS


DEFAULT_NOTIFIER_BASE_URL = "http://notifier:8000"


class NotifierClientSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    notifier_base_url: HttpUrl = HttpUrl(DEFAULT_NOTIFIER_BASE_URL)
    timeout_seconds: PositiveFloat = DEFAULT_MAILHOG_TIMEOUT_SECONDS
