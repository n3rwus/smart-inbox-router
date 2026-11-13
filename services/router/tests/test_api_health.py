from pathlib import Path

from common.errors import NotReadyError
from common.http import PROBLEM_JSON_MEDIA_TYPE
from fastapi import status
from fastapi.testclient import TestClient
from router.api.app import create_app
from router.api.health import HEALTH_PATH, READY_PATH
from router.config import RouterSettings


def _settings(tmp_path: Path) -> RouterSettings:
    return RouterSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'router.db'}",
    )


def test_health_returns_ok(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.get(HEALTH_PATH)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ok"}


def test_ready_returns_ok_when_database_responds(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.get(READY_PATH)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ready"}


def test_ready_returns_503_problem_details_when_database_fails(tmp_path: Path) -> None:
    class _FailingProbe:
        async def probe(self) -> None:
            raise NotReadyError("database probe failed: simulated outage")

    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        app.state.db_probe = _FailingProbe()
        response = client.get(READY_PATH)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.headers["content-type"].startswith(PROBLEM_JSON_MEDIA_TYPE)
    assert response.json()["code"] == "not_ready"


def test_openapi_and_docs_are_reachable(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        docs = client.get("/api/v1/docs")
        openapi = client.get("/api/v1/openapi.json")

    assert docs.status_code == status.HTTP_200_OK
    assert openapi.status_code == status.HTTP_200_OK
    assert openapi.json()["info"]["title"] == "Smart Inbox Router"


def test_health_endpoints_are_hidden_from_schema(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        paths = client.get("/api/v1/openapi.json").json()["paths"]

    assert HEALTH_PATH not in paths
    assert READY_PATH not in paths


def test_unknown_path_returns_404_problem_details(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.get("/api/v1/does-not-exist")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_JSON_MEDIA_TYPE)
