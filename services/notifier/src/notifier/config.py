from common.http import HttpServerConfig
from common.settings import BaseServiceSettings
from common.smtp import SmtpConfig
from pydantic import EmailStr, Field
from pydantic_settings import SettingsConfigDict


class NotifierSettings(BaseServiceSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        frozen=True,
        env_prefix="NOTIFIER_",
        env_nested_delimiter="__",
    )

    smtp: SmtpConfig = Field(default_factory=SmtpConfig)
    http: HttpServerConfig = Field(default_factory=HttpServerConfig)
    from_address: EmailStr = "smart-inbox-router@example.com"
