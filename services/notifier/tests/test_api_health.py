from fastapi import status
from fastapi.testclient import TestClient
from notifier.api.app import create_app
from notifier.api.health import HEALTH_PATH
from notifier.config import NotifierSettings


def test_health_returns_200_without_dependencies() -> None:
    app = create_app(NotifierSettings(_env_file=None))

    with TestClient(app) as client:
        response = client.get(HEALTH_PATH)

    assert response.status_code == status.HTTP_200_OK


def test_health_is_not_in_openapi_schema() -> None:
    app = create_app(NotifierSettings(_env_file=None))

    with TestClient(app) as client:
        schema = client.get("/api/v1/openapi.json").json()

    assert HEALTH_PATH not in schema["paths"]
