"""Entrypoint for `python -m router.migrate` — runs `alembic upgrade head`."""

from alembic import command
from alembic.config import Config
from common.log import configure_logging

from router.config import RouterSettings

MIGRATIONS_LOCATION = "router:migrations"


def build_config(database_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", MIGRATIONS_LOCATION)
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def main() -> None:
    settings = RouterSettings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)
    command.upgrade(build_config(settings.database_url), "head")


if __name__ == "__main__":
    main()
