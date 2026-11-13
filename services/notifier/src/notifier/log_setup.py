from common.log import configure_logging

from notifier.config import NotifierSettings


def configure_from_settings(settings: NotifierSettings) -> None:
    configure_logging(level=settings.log_level, json_output=settings.log_json)
