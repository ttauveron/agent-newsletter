import asyncio
import uuid
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from scheduler import (
    _check_user_messages,
    _run_daily_digest,
    _wake_hermes,
    create_scheduler,
    load_digest_config,
    reschedule_digest,
)


def _mock_session_ctx(session):
    @contextmanager
    def _ctx():
        yield session

    return _ctx


# --- _wake_hermes ---


def test_wake_hermes_posts_to_webhook_url():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch.dict("os.environ", {"HERMES_WEBHOOK_URL": "http://test-hermes:9999"}):
        with patch("httpx.AsyncClient", return_value=mock_client):
            asyncio.run(_wake_hermes({"event": "daily-digest", "date": "2026-05-29"}))

    mock_client.post.assert_called_once()
    url, *_ = mock_client.post.call_args.args
    assert url == "http://test-hermes:9999/webhooks/daily-digest"
    import json as _json

    body = mock_client.post.call_args.kwargs["content"]
    assert _json.loads(body)["event"] == "daily-digest"


def test_wake_hermes_does_not_raise_on_connection_error():
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=Exception("connection refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        asyncio.run(_wake_hermes({"event": "test"}))  # must not raise


def test_wake_hermes_does_not_raise_on_http_error():
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = Exception("503")
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        asyncio.run(_wake_hermes({"event": "test"}))  # must not raise


# --- _run_daily_digest ---


def test_run_daily_digest_creates_digest_and_wakes_hermes():
    from db.models import Digest, DigestState

    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = None
    session.execute.return_value.scalars.return_value.first.return_value = MagicMock()

    with patch("scheduler.get_session", _mock_session_ctx(session)):
        with patch("scheduler._wake_hermes", AsyncMock()) as mock_wake:
            asyncio.run(_run_daily_digest())

    session.add.assert_called_once()
    added = session.add.call_args.args[0]
    assert isinstance(added, Digest)
    assert added.processing_state == DigestState.digest_due
    mock_wake.assert_called_once()
    payload = mock_wake.call_args.args[0]
    assert payload["event"] == "daily-digest"
    assert "date" in payload


def test_run_daily_digest_skips_when_already_exists():
    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = MagicMock()

    with patch("scheduler.get_session", _mock_session_ctx(session)):
        with patch("scheduler._wake_hermes", AsyncMock()) as mock_wake:
            asyncio.run(_run_daily_digest())

    session.add.assert_not_called()
    mock_wake.assert_not_called()


def test_run_daily_digest_skips_when_no_pending_emails():
    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = None
    session.execute.return_value.scalars.return_value.first.return_value = None

    with patch("scheduler.get_session", _mock_session_ctx(session)):
        with patch("scheduler._wake_hermes", AsyncMock()) as mock_wake:
            asyncio.run(_run_daily_digest())

    session.add.assert_not_called()
    mock_wake.assert_not_called()


# --- _check_user_messages ---


def test_check_user_messages_updates_state_and_wakes_hermes():
    from db.models import UserMessageState

    msg = MagicMock()
    msg.id = uuid.uuid4()
    msg.subject = "Weekly summary please"
    msg.content = "Can you summarize this week's newsletters?"
    msg.processing_state = UserMessageState.user_message_received

    session = MagicMock()
    session.execute.return_value.scalars.return_value.all.return_value = [msg]

    with patch("scheduler.get_session", _mock_session_ctx(session)):
        with patch("scheduler._wake_hermes", AsyncMock()) as mock_wake:
            asyncio.run(_check_user_messages())

    assert msg.processing_state == UserMessageState.passed_to_hermes
    mock_wake.assert_called_once()
    payload = mock_wake.call_args.args[0]
    assert payload["event"] == "user-message"
    assert payload["message_id"] == str(msg.id)
    assert payload["subject"] == "Weekly summary please"
    assert payload["content"] == "Can you summarize this week's newsletters?"


def test_check_user_messages_wakes_hermes_once_per_message():
    msg1 = MagicMock()
    msg1.id = uuid.uuid4()
    msg1.subject = "Msg 1"
    msg1.content = "Content 1"
    msg2 = MagicMock()
    msg2.id = uuid.uuid4()
    msg2.subject = "Msg 2"
    msg2.content = "Content 2"

    session = MagicMock()
    session.execute.return_value.scalars.return_value.all.return_value = [msg1, msg2]

    with patch("scheduler.get_session", _mock_session_ctx(session)):
        with patch("scheduler._wake_hermes", AsyncMock()) as mock_wake:
            asyncio.run(_check_user_messages())

    assert mock_wake.call_count == 2


def test_check_user_messages_no_op_when_empty():
    session = MagicMock()
    session.execute.return_value.scalars.return_value.all.return_value = []

    with patch("scheduler.get_session", _mock_session_ctx(session)):
        with patch("scheduler._wake_hermes", AsyncMock()) as mock_wake:
            asyncio.run(_check_user_messages())

    mock_wake.assert_not_called()


# --- load_digest_config ---


def test_load_digest_config_returns_db_values():
    from db.models import AppSetting

    def _make_row(value):
        row = MagicMock(spec=AppSetting)
        row.value = value
        return row

    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.side_effect = [
        _make_row("08:30"),
        _make_row("Europe/Paris"),
    ]

    schedule, timezone = load_digest_config(session)

    assert schedule == "08:30"
    assert timezone == "Europe/Paris"


def test_load_digest_config_falls_back_to_defaults_when_missing():
    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = None

    schedule, timezone = load_digest_config(session)

    assert schedule == "07:00"
    assert timezone == "Europe/Zurich"


# --- reschedule_digest ---


def test_reschedule_digest_calls_reschedule_job():
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    scheduler = MagicMock(spec=AsyncIOScheduler)
    reschedule_digest(scheduler, "09:15", "America/New_York")

    scheduler.reschedule_job.assert_called_once()
    call_kwargs = scheduler.reschedule_job.call_args
    assert call_kwargs.args[0] == "daily_digest"
    trigger = call_kwargs.kwargs["trigger"]
    fields = {f.name: str(f) for f in trigger.fields}
    assert fields["hour"] == "9"
    assert fields["minute"] == "15"


# --- create_scheduler ---


def test_create_scheduler_registers_all_jobs():
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    scheduler = create_scheduler("07:00", "Europe/Zurich", MagicMock(), MagicMock(), MagicMock())
    assert isinstance(scheduler, AsyncIOScheduler)
    job_ids = {job.id for job in scheduler.get_jobs()}
    assert job_ids == {"daily_digest", "gmail_poll", "check_user_messages"}


def test_create_scheduler_respects_digest_schedule():
    from apscheduler.triggers.cron import CronTrigger

    scheduler = create_scheduler("08:30", "Europe/Paris", MagicMock(), MagicMock(), MagicMock())
    digest_job = next(j for j in scheduler.get_jobs() if j.id == "daily_digest")
    trigger = digest_job.trigger
    assert isinstance(trigger, CronTrigger)
    fields = {f.name: str(f) for f in trigger.fields}
    assert fields["hour"] == "8"
    assert fields["minute"] == "30"
