import json

import pytest
from common.errors import DeliveryFailedError
from common.http import CORRELATION_ID_HEADER, install_problem_handlers
from common.http.correlation import install_correlation_middleware
from common.log import correlation_id
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

GIVEN_ID = "cid-from-client-01"


def _build_app() -> tuple[FastAPI, dict[str, str | None]]:
    app = FastAPI()
    install_correlation_middleware(app)
    install_problem_handlers(app)
    seen: dict[str, str | None] = {}

    @app.get("/echo")
    async def echo() -> dict[str, str | None]:
        seen["inside"] = correlation_id.get()
        return {"id": correlation_id.get()}

    @app.get("/boom")
    async def boom() -> None:
        raise DeliveryFailedError("smtp down")

    return app, seen


def test_incoming_header_is_echoed_and_set_in_context() -> None:
    app, seen = _build_app()
    client = TestClient(app)

    response = client.get("/echo", headers={CORRELATION_ID_HEADER: GIVEN_ID})

    assert response.headers[CORRELATION_ID_HEADER] == GIVEN_ID
    assert response.json()["id"] == GIVEN_ID
    assert seen["inside"] == GIVEN_ID


def test_missing_header_generates_uuid() -> None:
    app, _ = _build_app()
    client = TestClient(app)

    response = client.get("/echo")

    generated = response.headers[CORRELATION_ID_HEADER]
    assert generated
    assert len(generated) >= 32


def test_context_var_is_reset_after_request() -> None:
    app, _ = _build_app()
    client = TestClient(app)

    client.get("/echo", headers={CORRELATION_ID_HEADER: GIVEN_ID})

    assert correlation_id.get() is None


def test_problem_details_include_correlation_id() -> None:
    app, _ = _build_app()
    client = TestClient(app)

    response = client.get("/boom", headers={CORRELATION_ID_HEADER: GIVEN_ID})

    assert response.status_code == status.HTTP_502_BAD_GATEWAY
    assert response.headers[CORRELATION_ID_HEADER] == GIVEN_ID
    body = json.loads(response.content)
    assert body["correlation_id"] == GIVEN_ID


def test_unhandled_500_still_carries_correlation_id() -> None:
    app, _ = _build_app()

    @app.get("/kaboom")
    async def kaboom() -> None:
        raise RuntimeError("boom")

    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/kaboom", headers={CORRELATION_ID_HEADER: GIVEN_ID})

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.headers.get(CORRELATION_ID_HEADER) == GIVEN_ID


@pytest.mark.parametrize("bad", ["", "with space", "a\r\nb"])
def test_invalid_incoming_id_is_replaced_with_generated(bad: str) -> None:
    app, _ = _build_app()
    client = TestClient(app)

    response = client.get("/echo", headers={CORRELATION_ID_HEADER: bad})

    returned = response.headers[CORRELATION_ID_HEADER]
    assert returned != bad
    assert returned
