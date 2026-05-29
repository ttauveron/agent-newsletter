import uuid
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import (
    _update_markdown,
    _validate_schedule,
    create_router,
)
from config import EmailConfig, Settings


def _make_settings(authorized_address="user@example.com"):
    return Settings(email=EmailConfig(authorized_user_address=authorized_address))


def _make_client(
    gmail_client=None,
    settings=None,
    scheduler=None,
    mock_session=None,
):
    app = FastAPI()
    app.state.scheduler = scheduler or MagicMock()
    router = create_router(
        gmail_client or MagicMock(),
        settings or _make_settings(),
    )
    app.include_router(router)

    if mock_session is not None:

        @contextmanager
        def _ctx():
            yield mock_session

        app.dependency_overrides = {}
        # patch get_session at the routes module level
        with patch("api.routes.get_session", _ctx):
            yield TestClient(app)
        return

    yield TestClient(app)


@contextmanager
def _patched_client(gmail_client=None, settings=None, scheduler=None, session=None):
    app = FastAPI()
    app.state.scheduler = scheduler or MagicMock()
    router = create_router(
        gmail_client or MagicMock(),
        settings or _make_settings(),
    )
    app.include_router(router)

    mock_session = session or MagicMock()

    @contextmanager
    def _ctx():
        yield mock_session

    with patch("api.routes.get_session", _ctx):
        yield TestClient(app), mock_session


# --- POST /actions/send-digest ---


def test_send_digest_happy_path():
    from db.models import Digest, DigestState

    digest_id = uuid.uuid4()
    digest = MagicMock(spec=Digest)
    digest.id = digest_id
    digest.digest_date = "2026-05-29"
    digest.processing_state = DigestState.digest_due

    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = digest

    gmail = MagicMock()

    with _patched_client(gmail_client=gmail, session=session) as (client, _):
        resp = client.post(
            "/actions/send-digest",
            json={"digest_id": str(digest_id), "content": "Today's digest."},
        )

    assert resp.status_code == 200
    assert resp.json()["digest_id"] == str(digest_id)
    gmail.send_email.assert_called_once()
    call_kwargs = gmail.send_email.call_args.kwargs
    assert call_kwargs["to"] == "user@example.com"
    assert "2026-05-29" in call_kwargs["subject"]
    assert digest.processing_state == DigestState.digest_sent
    assert digest.content == "Today's digest."


def test_send_digest_not_found():
    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = None

    with _patched_client(session=session) as (client, _):
        resp = client.post(
            "/actions/send-digest",
            json={"digest_id": str(uuid.uuid4()), "content": "x"},
        )

    assert resp.status_code == 404


def test_send_digest_wrong_state():
    from db.models import Digest, DigestState

    digest = MagicMock(spec=Digest)
    digest.processing_state = DigestState.digest_sent  # already sent

    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = digest

    with _patched_client(session=session) as (client, _):
        resp = client.post(
            "/actions/send-digest",
            json={"digest_id": str(uuid.uuid4()), "content": "x"},
        )

    assert resp.status_code == 409


def test_send_digest_no_recipient_configured():
    settings = _make_settings(authorized_address="")
    with _patched_client(settings=settings) as (client, _):
        resp = client.post(
            "/actions/send-digest",
            json={"digest_id": str(uuid.uuid4()), "content": "x"},
        )
    assert resp.status_code == 503


# --- POST /actions/send-reply ---


def test_send_reply_happy_path():
    from db.models import UserMessage, UserMessageState

    msg_id = uuid.uuid4()
    msg = MagicMock(spec=UserMessage)
    msg.id = msg_id
    msg.subject = "Help me"
    msg.processing_state = UserMessageState.passed_to_hermes

    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = msg

    gmail = MagicMock()

    with _patched_client(gmail_client=gmail, session=session) as (client, _):
        resp = client.post(
            "/actions/send-reply",
            json={"user_message_id": str(msg_id), "content": "Here is my answer."},
        )

    assert resp.status_code == 200
    gmail.send_email.assert_called_once()
    assert gmail.send_email.call_args.kwargs["subject"] == "Re: Help me"
    assert msg.processing_state == UserMessageState.answered
    assert msg.hermes_response == "Here is my answer."


def test_send_reply_does_not_double_re_prefix():
    from db.models import UserMessage

    msg = MagicMock(spec=UserMessage)
    msg.subject = "Re: Help me"
    msg.processing_state = "passed_to_hermes"

    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = msg

    gmail = MagicMock()

    with _patched_client(gmail_client=gmail, session=session) as (client, _):
        client.post(
            "/actions/send-reply",
            json={"user_message_id": str(uuid.uuid4()), "content": "answer"},
        )

    assert gmail.send_email.call_args.kwargs["subject"] == "Re: Help me"


def test_send_reply_not_found():
    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = None

    with _patched_client(session=session) as (client, _):
        resp = client.post(
            "/actions/send-reply",
            json={"user_message_id": str(uuid.uuid4()), "content": "x"},
        )

    assert resp.status_code == 404


# --- POST /hermes/preferences ---


def test_preferences_unknown_key():
    with _patched_client() as (client, _):
        resp = client.post("/hermes/preferences", json={"key": "unknown_key", "value": "x"})
    assert resp.status_code == 400
    assert "unknown_key" in resp.json()["detail"]


def test_preferences_digest_schedule_valid():
    schedule_row = MagicMock()
    schedule_row.value = "07:00"
    timezone_row = MagicMock()
    timezone_row.value = "Europe/Zurich"

    session = MagicMock()
    # first call = schedule row (to update), second = timezone companion
    session.execute.return_value.scalar_one_or_none.side_effect = [
        schedule_row,
        timezone_row,
    ]

    scheduler = MagicMock()

    with _patched_client(scheduler=scheduler, session=session) as (client, _):
        resp = client.post("/hermes/preferences", json={"key": "digest_schedule", "value": "09:00"})

    assert resp.status_code == 200
    assert schedule_row.value == "09:00"
    scheduler.reschedule_job.assert_called_once()


def test_preferences_digest_schedule_invalid_format():
    with _patched_client() as (client, _):
        resp = client.post("/hermes/preferences", json={"key": "digest_schedule", "value": "9am"})
    assert resp.status_code == 422


def test_preferences_digest_schedule_out_of_range():
    with _patched_client() as (client, _):
        resp = client.post("/hermes/preferences", json={"key": "digest_schedule", "value": "25:00"})
    assert resp.status_code == 422


def test_preferences_markdown_key_writes_file(tmp_path):

    with patch("api.routes.CONFIG_DIR", tmp_path):
        (tmp_path / "learned_preferences.md").write_text("old content")
        session = MagicMock()

        with _patched_client(session=session) as (client, _):
            resp = client.post(
                "/hermes/preferences",
                json={"key": "learned_preferences", "value": "new content"},
            )

    assert resp.status_code == 200
    assert (tmp_path / "learned_preferences.md").read_text() == "new content"


def test_preferences_markdown_key_logs_diff(tmp_path):
    with patch("api.routes.CONFIG_DIR", tmp_path):
        (tmp_path / "digest_style.md").write_text("old")
        session = MagicMock()

        with _patched_client(session=session) as (client, _):
            client.post("/hermes/preferences", json={"key": "digest_style", "value": "new"})

    session.add.assert_called()
    audit_log = session.add.call_args.args[0]
    assert audit_log.event_type == "preference_markdown_updated"
    assert "diff" in audit_log.payload


# --- _validate_schedule ---


@pytest.mark.parametrize("value", ["07:00", "00:00", "23:59", "08:30"])
def test_validate_schedule_valid(value):
    _validate_schedule(value)  # must not raise


@pytest.mark.parametrize("value", ["9am", "25:00", "08:60", "abc"])
def test_validate_schedule_invalid(value):
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        _validate_schedule(value)


# --- _update_markdown ---


def test_update_markdown_creates_file_if_missing(tmp_path):
    session = MagicMock()
    with patch("api.routes.CONFIG_DIR", tmp_path):
        with patch("api.routes.get_session", lambda: _noop_ctx(session)):
            _update_markdown("user_profile", "# Profile\nNew content")

    assert (tmp_path / "user_profile.md").read_text() == "# Profile\nNew content"


@contextmanager
def _noop_ctx(session):
    yield session
