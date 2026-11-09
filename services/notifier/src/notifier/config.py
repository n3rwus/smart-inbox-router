from common.settings import BaseServiceSettings
from pydantic import EmailStr
from pydantic_settings import SettingsConfigDict


class NotifierSettings(BaseServiceSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        frozen=True,
        env_prefix="NOTIFIER_",
    )

    smtp_host: str = "mailhog"
    smtp_port: int = 1025
    from_address: EmailStr = "smart-inbox-router@example.com"
