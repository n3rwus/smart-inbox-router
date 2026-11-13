import uvicorn
from common.log import configure_logging

from router.api.app import create_app
from router.config import RouterSettings


def main() -> None:
    settings = RouterSettings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)
    uvicorn.run(
        create_app(settings),
        host=settings.http.host,
        port=settings.http.port,
    )


if __name__ == "__main__":
    main()
