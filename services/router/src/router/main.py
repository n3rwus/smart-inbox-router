"""ASGI entrypoint resolved by `uvicorn router.main:app` in docker/entrypoint.sh."""

from common.log import configure_logging

from router.api.app import create_app
from router.config import RouterSettings

_settings = RouterSettings()
configure_logging(level=_settings.log_level, json_output=_settings.log_json)
app = create_app(_settings)
