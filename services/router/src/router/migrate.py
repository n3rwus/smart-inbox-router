"""Entrypoint for `python -m router.migrate` — runs `alembic upgrade head`."""

from pathlib import Path

from alembic import command
from alembic.config import Config

ALEMBIC_INI_ENV = "ROUTER_ALEMBIC_INI"


def _config() -> Config:
    import os

    override = os.environ.get(ALEMBIC_INI_ENV)
    if override:
        return Config(override)
    return Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))


def main() -> None:
    command.upgrade(_config(), "head")


if __name__ == "__main__":
    main()
