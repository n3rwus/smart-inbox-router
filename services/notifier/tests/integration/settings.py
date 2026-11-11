from pydantic import PositiveFloat
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
