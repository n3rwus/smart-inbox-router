from common.http import API_V1_PREFIX
from fastapi import status
from fastapi.testclient import TestClient
from notifier.api.app import create_app
from notifier.api.health import HEALTH_PATH
from notifier.config import NotifierSettings

HEALTH_URL = f"{API_V1_PREFIX}{HEALTH_PATH}"


def test_health_returns_no_content_without_dependencies() -> None:
    app = create_app(NotifierSettings(_env_file=None))

    with TestClient(app) as client:
        response = client.get(HEALTH_URL)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.content == b""
