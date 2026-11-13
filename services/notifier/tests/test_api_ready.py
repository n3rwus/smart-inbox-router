from common.errors import NotReadyError
from common.http import PROBLEM_JSON_MEDIA_TYPE
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from notifier.api.app import create_app
from notifier.api.health import READY_PATH, get_probe
from notifier.config import NotifierSettings
from notifier.ports.smtp_probe import SmtpProbe


class _OkProbe:
    async def probe(self) -> None:
        return None


class _FailingProbe:
    async def probe(self) -> None:
        raise NotReadyError("smtp unreachable")


def _app_with(probe: SmtpProbe) -> FastAPI:
    app = create_app(NotifierSettings(_env_file=None))
    app.dependency_overrides[get_probe] = lambda: probe
    return app


def test_ready_returns_200_when_probe_succeeds() -> None:
    with TestClient(_app_with(_OkProbe())) as client:
        response = client.get(READY_PATH)

    assert response.status_code == status.HTTP_200_OK


def test_ready_returns_503_problem_details_when_probe_fails() -> None:
    with TestClient(_app_with(_FailingProbe())) as client:
        response = client.get(READY_PATH)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.headers["content-type"].startswith(PROBLEM_JSON_MEDIA_TYPE)
    assert response.json()["code"] == "not_ready"
