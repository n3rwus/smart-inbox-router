from pathlib import Path
from uuid import UUID, uuid4

from common.db import create_engine, create_session_factory
from common.http import PROBLEM_JSON_MEDIA_TYPE
from fastapi import status
from fastapi.testclient import TestClient
from router.adapters.db import Base, MessageRow
from router.adapters.sql_message_repository import SqlMessageRepository
from router.api.app import create_app
from router.api.messages import MESSAGE_MAX_LENGTH
from router.config import RouterSettings
from router.domain.message import MessageStatus
from sqlalchemy import select

from .fakes import InMemoryMessageRepository

MESSAGES_URL = "/api/v1/messages"


def _settings(tmp_path: Path) -> RouterSettings:
    return RouterSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'router.db'}",
    )


def _client_with_repo(tmp_path: Path, repository: object) -> TestClient:
    app = create_app(_settings(tmp_path))
    client = TestClient(app)
    client.__enter__()
    app.state.message_repository = repository
    return client


def test_post_accepts_message_and_sets_location(tmp_path: Path) -> None:
    client = _client_with_repo(tmp_path, InMemoryMessageRepository())
    try:
        response = client.post(
            MESSAGES_URL,
            json={"email": "alice@example.com", "message": "please help"},
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == status.HTTP_202_ACCEPTED
    body = response.json()
    message_id = UUID(body["id"])
    assert body["status"] == MessageStatus.RECEIVED
    assert response.headers["Location"] == f"{MESSAGES_URL}/{message_id}"


def test_post_then_get_returns_received_without_user_fields(tmp_path: Path) -> None:
    client = _client_with_repo(tmp_path, InMemoryMessageRepository())
    try:
        posted = client.post(
            MESSAGES_URL,
            json={"email": "alice@example.com", "message": "please help"},
        )
        message_id = posted.json()["id"]
        fetched = client.get(f"{MESSAGES_URL}/{message_id}")
    finally:
        client.__exit__(None, None, None)

    assert fetched.status_code == status.HTTP_200_OK
    body = fetched.json()
    assert body["id"] == message_id
    assert body["status"] == MessageStatus.RECEIVED
    assert body["department"] is None
    assert body["fallback_used"] is False
    assert body["error_code"] is None
    assert body["attempts"] == 0
    assert "email" not in body
    assert "message" not in body
    assert "sender_email" not in body
    assert "body" not in body


def test_get_unknown_id_returns_404_problem_details(tmp_path: Path) -> None:
    client = _client_with_repo(tmp_path, InMemoryMessageRepository())
    try:
        response = client.get(f"{MESSAGES_URL}/{uuid4()}")
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_JSON_MEDIA_TYPE)
    assert response.json()["code"] == "message_not_found"


def test_get_non_uuid_returns_422(tmp_path: Path) -> None:
    client = _client_with_repo(tmp_path, InMemoryMessageRepository())
    try:
        response = client.get(f"{MESSAGES_URL}/not-a-uuid")
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.headers["content-type"].startswith(PROBLEM_JSON_MEDIA_TYPE)


def test_post_rejects_invalid_email_without_echoing_value(tmp_path: Path) -> None:
    client = _client_with_repo(tmp_path, InMemoryMessageRepository())
    try:
        response = client.post(
            MESSAGES_URL,
            json={"email": "not-an-email", "message": "hello"},
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    text = response.text
    assert "not-an-email" not in text


def test_post_rejects_empty_message_without_echoing_value(tmp_path: Path) -> None:
    client = _client_with_repo(tmp_path, InMemoryMessageRepository())
    try:
        response = client.post(
            MESSAGES_URL,
            json={"email": "alice@example.com", "message": "   "},
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_post_rejects_oversized_message_without_echoing_value(tmp_path: Path) -> None:
    client = _client_with_repo(tmp_path, InMemoryMessageRepository())
    oversized = "x" * (MESSAGE_MAX_LENGTH + 1)
    try:
        response = client.post(
            MESSAGES_URL,
            json={"email": "alice@example.com", "message": oversized},
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert oversized not in response.text


async def test_post_persists_row_with_sql_repository(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'router_sql.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = create_session_factory(engine)
    repo = SqlMessageRepository(session_factory)

    client = _client_with_repo(tmp_path, repo)
    try:
        response = client.post(
            MESSAGES_URL,
            json={"email": "alice@example.com", "message": "please help"},
        )
    finally:
        client.__exit__(None, None, None)

    message_id = response.json()["id"]
    async with session_factory() as session:
        row = (await session.execute(select(MessageRow))).scalar_one()

    await engine.dispose()

    assert response.status_code == status.HTTP_202_ACCEPTED
    assert row.id == message_id
    assert row.sender_email == "alice@example.com"
    assert row.body == "please help"
    assert row.status == MessageStatus.RECEIVED.value
