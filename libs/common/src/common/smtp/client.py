import logging
from email.message import EmailMessage

import aiosmtplib

from common.email_headers import EmailHeader
from common.errors import DeliveryFailedError
from common.smtp.config import SmtpConfig
from common.timeouts import with_timeout

logger = logging.getLogger(__name__)


class SmtpClient:
    def __init__(self, config: SmtpConfig) -> None:
        self._config = config

    @property
    def timeout_seconds(self) -> float:
        return self._config.timeout_seconds

    @with_timeout
    async def send(self, email: EmailMessage) -> None:
        password = self._config.password.get_secret_value() if self._config.password else None
        try:
            await aiosmtplib.send(
                email,
                hostname=self._config.host,
                port=self._config.port,
                start_tls=self._config.start_tls,
                username=self._config.username,
                password=password,
            )
        except TimeoutError:
            raise
        except (aiosmtplib.SMTPException, OSError) as exc:
            logger.warning("SMTP delivery failed: %s", type(exc).__name__)
            raise DeliveryFailedError(
                f"SMTP delivery to {self._config.host}:{self._config.port} failed"
            ) from exc
        logger.info("email delivered to %s", email[EmailHeader.TO])
