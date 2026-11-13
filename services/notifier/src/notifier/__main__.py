import uvicorn

from notifier.api.app import create_app
from notifier.config import NotifierSettings
from notifier.log_setup import configure_from_settings


def main() -> None:
    settings = NotifierSettings()
    configure_from_settings(settings)
    uvicorn.run(
        create_app(settings),
        host=settings.http.host,
        port=settings.http.port,
    )


if __name__ == "__main__":
    main()
