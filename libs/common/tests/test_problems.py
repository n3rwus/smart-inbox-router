import json

from common.errors import AppError, DeliveryFailedError, ErrorCode
from common.http import (
    PROBLEM_JSON_MEDIA_TYPE,
    CorrelationIdMiddleware,
    install_problem_handlers,
)
from common.http.problems import STATUS_BY_CODE
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from pydantic import BaseModel


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


class _EchoPayload(BaseModel):
    email: str
    age: int


def _full_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(CorrelationIdMiddleware)
    install_problem_handlers(app)

    @app.post("/echo")
    async def echo(payload: _EchoPayload) -> dict[str, bool]:
        return {"ok": True}

    @app.get("/only-get")
    async def only_get() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/teapot")
    async def teapot() -> None:
        raise HTTPException(status_code=status.HTTP_418_IM_A_TEAPOT, detail="pot")

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret internals: tajna wartosc")

    return app


def test_validation_error_is_problem_json_without_user_input():
    client = TestClient(_full_app())
    sent_email = "leak-me@@x"
    sent_age = "definitely-not-an-int"

    response = client.post("/echo", json={"email": sent_email, "age": sent_age})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.headers["content-type"].startswith(PROBLEM_JSON_MEDIA_TYPE)
    text = response.text
    assert sent_email not in text
    assert sent_age not in text
    body = response.json()
    assert body["type"] == "about:blank"
    assert body["status"] == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert body["code"] == "validation_failed"
    assert body["correlation_id"]
    assert body["errors"]
    for err in body["errors"]:
        assert set(err.keys()) == {"loc", "msg", "type"}


def test_404_uses_problem_json():
    client = TestClient(_full_app())

    response = client.get("/does-not-exist")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_JSON_MEDIA_TYPE)
    body = response.json()
    assert body["code"] == "not_found"
    assert body["title"] == "Not Found"
    assert body["correlation_id"]


def test_405_preserves_allow_header_and_uses_problem_json():
    client = TestClient(_full_app())

    response = client.post("/only-get")

    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
    assert response.headers["content-type"].startswith(PROBLEM_JSON_MEDIA_TYPE)
    allow = response.headers.get("allow") or response.headers.get("Allow")
    assert allow is not None
    assert "GET" in allow
    body = response.json()
    assert body["code"] == "method_not_allowed"


def test_http_exception_detail_is_preserved():
    client = TestClient(_full_app())

    response = client.get("/teapot")

    assert response.status_code == status.HTTP_418_IM_A_TEAPOT
    assert response.headers["content-type"].startswith(PROBLEM_JSON_MEDIA_TYPE)
    body = response.json()
    assert body["detail"] == "pot"


def test_unhandled_exception_becomes_500_without_trace():
    client = TestClient(_full_app(), raise_server_exceptions=False)

    response = client.get("/boom")

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.headers["content-type"].startswith(PROBLEM_JSON_MEDIA_TYPE)
    text = response.text
    assert "Traceback" not in text
    assert "secret internals" not in text
    body = response.json()
    assert body["code"] == "internal_error"
    assert body["correlation_id"]
