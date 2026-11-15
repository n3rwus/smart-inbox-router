from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, SecretStr

DEFAULT_SMTP_HOST = "localhost"
DEFAULT_SMTP_PORT = 1025  # MailHog SMTP
DEFAULT_SMTP_TIMEOUT_SECONDS = 10.0
MIN_TCP_PORT = 1
MAX_TCP_PORT = 65_535


class SmtpConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    host: str = DEFAULT_SMTP_HOST
    port: int = Field(default=DEFAULT_SMTP_PORT, ge=MIN_TCP_PORT, le=MAX_TCP_PORT)
    timeout_seconds: PositiveFloat = DEFAULT_SMTP_TIMEOUT_SECONDS
    start_tls: bool = False
    username: str | None = None
    password: SecretStr | None = None
