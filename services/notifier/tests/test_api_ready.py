from common.errors import NotReadyError
from common.http import PROBLEM_JSON_MEDIA_TYPE
from fastapi import status
from fastapi.testclient import TestClient
from notifier.api.app import create_app
from notifier.api.health import READY_PATH
from notifier.config import NotifierSettings
from notifier.ports.smtp_probe import SmtpProbe


class _OkProbe:
    async def probe(self) -> None:
        return None


class _FailingProbe:
    async def probe(self) -> None:
        raise NotReadyError("smtp unreachable")


def _client_with(probe: SmtpProbe) -> TestClient:
    app = create_app(NotifierSettings(_env_file=None))
    client = TestClient(app)
    client.__enter__()
    app.state.smtp_probe = probe
    return client


def test_ready_returns_200_when_probe_succeeds() -> None:
    client = _client_with(_OkProbe())
    try:
        response = client.get(READY_PATH)
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == status.HTTP_200_OK


def test_ready_returns_503_problem_details_when_probe_fails() -> None:
    client = _client_with(_FailingProbe())
    try:
        response = client.get(READY_PATH)
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.headers["content-type"].startswith(PROBLEM_JSON_MEDIA_TYPE)
    assert response.json()["code"] == "not_ready"
