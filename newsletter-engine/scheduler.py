import hashlib
import hmac
import json as _json
import logging
import os
from datetime import date

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import AppSetting, Digest, DigestState, UserMessage, UserMessageState
from db.session import get_session
from gmail.client import GmailClient
from gmail.poller import poll as gmail_poll
from processing.whitelist import WhitelistFilter

logger = logging.getLogger(__name__)

POLL_INTERVAL_MINUTES = 5


def load_digest_config(session: Session) -> tuple[str, str]:
    """Return (digest_schedule, digest_timezone) from app_settings, with fallbacks."""

    def _get(key: str, default: str) -> str:
        row = session.execute(select(AppSetting).where(AppSetting.key == key)).scalar_one_or_none()
        return row.value if row else default

    return _get("digest_schedule", "07:00"), _get("digest_timezone", "Europe/Zurich")


def reschedule_digest(scheduler: AsyncIOScheduler, schedule: str, timezone: str) -> None:
    hour, minute = map(int, schedule.split(":"))
    scheduler.reschedule_job(
        "daily_digest",
        trigger=CronTrigger(hour=hour, minute=minute, timezone=timezone),
    )
    logger.info("Digest rescheduled to %s %s", schedule, timezone)


async def _wake_hermes(payload: dict) -> None:
    hermes_url = os.environ.get("HERMES_WEBHOOK_URL", "http://hermes:8644")
    secret = os.environ.get("HERMES_WEBHOOK_SECRET", "")
    event = payload.get("event", "unknown")
    endpoint = f"{hermes_url}/webhooks/{event}"
    body = _json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if secret:
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        headers["X-Hub-Signature-256"] = sig
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(endpoint, content=body, headers=headers, timeout=30)
            r.raise_for_status()
            logger.info("Hermes woken: event=%s", event)
    except Exception:
        logger.exception("Failed to wake Hermes (event=%s)", event)


async def _run_daily_digest() -> None:
    today = date.today()
    with get_session() as session:
        existing = session.execute(
            select(Digest).where(Digest.digest_date == today)
        ).scalar_one_or_none()
        if existing:
            logger.info(
                "Digest for %s already exists (state: %s)", today, existing.processing_state
            )
            return
        session.add(Digest(digest_date=today, processing_state=DigestState.digest_due))
    logger.info("Digest created for %s, notifying Hermes", today)
    await _wake_hermes({"event": "daily-digest", "date": str(today)})


async def _run_gmail_poll(
    gmail_client: GmailClient,
    whitelist: WhitelistFilter,
    enrichment_client: OpenAI,
) -> None:
    try:
        with get_session() as session:
            gmail_poll(gmail_client, whitelist, session, enrichment_client)
    except Exception:
        logger.exception("Scheduled Gmail poll failed")


async def _check_user_messages() -> None:
    pending: list[dict] = []
    with get_session() as session:
        msgs = (
            session.execute(
                select(UserMessage).where(
                    UserMessage.processing_state == UserMessageState.user_message_received
                )
            )
            .scalars()
            .all()
        )
        for msg in msgs:
            msg.processing_state = UserMessageState.passed_to_hermes
            pending.append(
                {
                    "event": "user-message",
                    "message_id": str(msg.id),
                    "subject": msg.subject,
                    "content": msg.content,
                }
            )
    if pending:
        logger.info("Forwarding %d user message(s) to Hermes", len(pending))
    for item in pending:
        await _wake_hermes(item)


def create_scheduler(
    digest_schedule: str,
    digest_timezone: str,
    gmail_client: GmailClient,
    whitelist: WhitelistFilter,
    enrichment_client: OpenAI,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    hour, minute = map(int, digest_schedule.split(":"))
    scheduler.add_job(
        _run_daily_digest,
        CronTrigger(hour=hour, minute=minute, timezone=digest_timezone),
        id="daily_digest",
        name="Daily digest trigger",
        misfire_grace_time=300,
        max_instances=1,
    )
    scheduler.add_job(
        _run_gmail_poll,
        "interval",
        minutes=POLL_INTERVAL_MINUTES,
        args=[gmail_client, whitelist, enrichment_client],
        id="gmail_poll",
        name="Gmail polling",
        misfire_grace_time=60,
        max_instances=1,
    )
    scheduler.add_job(
        _check_user_messages,
        "interval",
        minutes=1,
        id="check_user_messages",
        name="User messages check",
        misfire_grace_time=30,
        max_instances=1,
    )

    return scheduler
