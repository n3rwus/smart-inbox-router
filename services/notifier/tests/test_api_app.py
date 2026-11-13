from common.http import API_V1_PREFIX
from fastapi import status
from fastapi.testclient import TestClient
from notifier.api.app import create_app
from notifier.api.notifications import NOTIFICATIONS_PATH
from notifier.config import NotifierSettings

DOCS_URL = f"{API_V1_PREFIX}/docs"
OPENAPI_URL = f"{API_V1_PREFIX}/openapi.json"
NOTIFICATIONS_URL = f"{API_V1_PREFIX}{NOTIFICATIONS_PATH}"


def test_app_starts_with_test_settings() -> None:
    app = create_app(NotifierSettings(_env_file=None))

    with TestClient(app) as client:
        assert client.get(DOCS_URL).status_code == status.HTTP_200_OK


def test_docs_and_openapi_are_served_under_api_v1() -> None:
    app = create_app(NotifierSettings(_env_file=None))

    with TestClient(app) as client:
        assert client.get(DOCS_URL).status_code == status.HTTP_200_OK
        schema = client.get(OPENAPI_URL)

    assert schema.status_code == status.HTTP_200_OK
    paths = schema.json()["paths"]
    post_responses = paths[NOTIFICATIONS_URL]["post"]["responses"]
    assert str(status.HTTP_204_NO_CONTENT) in post_responses
    assert str(status.HTTP_422_UNPROCESSABLE_CONTENT) in post_responses
    assert str(status.HTTP_502_BAD_GATEWAY) in post_responses
    assert str(status.HTTP_504_GATEWAY_TIMEOUT) in post_responses


def test_lifespan_wires_deliver_closure() -> None:
    app = create_app(NotifierSettings(_env_file=None))

    with TestClient(app):
        assert callable(app.state.deliver)
