import json

from common.errors import AppError, DeliveryFailedError, ErrorCode
from common.http.problems import STATUS_BY_CODE, install_problem_handlers
from fastapi import FastAPI, status
from fastapi.testclient import TestClient


def test_every_error_code_has_a_status():
    missing = [code for code in ErrorCode if code not in STATUS_BY_CODE]
    assert not missing, f"ErrorCode without HTTP status: {missing}"


def test_known_mappings_use_fastapi_constants():
    assert STATUS_BY_CODE[ErrorCode.DELIVERY_FAILED] == status.HTTP_502_BAD_GATEWAY
    assert STATUS_BY_CODE[ErrorCode.UPSTREAM_TIMEOUT] == status.HTTP_504_GATEWAY_TIMEOUT


def _app_raising(error: AppError) -> FastAPI:
    app = FastAPI()
    install_problem_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise error

    return app


def test_app_error_becomes_problem_json():
    client = TestClient(_app_raising(DeliveryFailedError("smtp down")))

    response = client.get("/boom")

    assert response.status_code == status.HTTP_502_BAD_GATEWAY
    assert response.headers["content-type"].startswith("application/problem+json")
    body = json.loads(response.content)
    assert body["code"] == ErrorCode.DELIVERY_FAILED.value
    assert body["detail"] == "smtp down"
    assert body["status"] == status.HTTP_502_BAD_GATEWAY
