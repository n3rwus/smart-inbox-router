from common.http import API_V1_PREFIX
from fastapi import status
from fastapi.testclient import TestClient
from notifier.api.app import create_app
from notifier.api.notifications import NOTIFICATIONS_PATH
from notifier.config import NotifierSettings

DOCS_URL = f"{API_V1_PREFIX}/docs"
OPENAPI_URL = f"{API_V1_PREFIX}/openapi.json"
NOTIFICATIONS_PATH_TEMPLATE = f"{API_V1_PREFIX}{NOTIFICATIONS_PATH}/{{message_id}}"


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
    put_responses = paths[NOTIFICATIONS_PATH_TEMPLATE]["put"]["responses"]
    assert str(status.HTTP_201_CREATED) in put_responses
    assert str(status.HTTP_200_OK) in put_responses
    assert str(status.HTTP_409_CONFLICT) in put_responses
    assert str(status.HTTP_422_UNPROCESSABLE_CONTENT) in put_responses
    assert str(status.HTTP_502_BAD_GATEWAY) in put_responses
    assert str(status.HTTP_504_GATEWAY_TIMEOUT) in put_responses


def test_lifespan_wires_deliver_closure() -> None:
    app = create_app(NotifierSettings(_env_file=None))

    with TestClient(app):
        assert callable(app.state.deliver)
