import logging
import os
from datetime import date

import httpx
from anthropic import Anthropic
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from config import Settings
from db.models import Digest, DigestState, UserMessage, UserMessageState
from db.session import get_session
from gmail.client import GmailClient
from gmail.poller import poll as gmail_poll
from processing.whitelist import WhitelistFilter

logger = logging.getLogger(__name__)

POLL_INTERVAL_MINUTES = 5


async def _wake_hermes(payload: dict) -> None:
    hermes_url = os.environ.get("HERMES_URL", "http://hermes:8642")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{hermes_url}/api/trigger", json=payload, timeout=10)
            r.raise_for_status()
            logger.info("Hermes woken: event=%s", payload.get("event"))
    except Exception:
        logger.exception("Failed to wake Hermes (event=%s)", payload.get("event"))


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
    await _wake_hermes({"event": "daily_digest_due", "date": str(today)})


async def _run_gmail_poll(
    gmail_client: GmailClient,
    whitelist: WhitelistFilter,
    anthropic_client: Anthropic,
) -> None:
    try:
        with get_session() as session:
            gmail_poll(gmail_client, whitelist, session, anthropic_client)
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
            pending.append({"message_id": str(msg.id), "subject": msg.subject})
    if pending:
        logger.info("Forwarding %d user message(s) to Hermes", len(pending))
    for item in pending:
        await _wake_hermes({"event": "user_message", **item})


def create_scheduler(
    settings: Settings,
    gmail_client: GmailClient,
    whitelist: WhitelistFilter,
    anthropic_client: Anthropic,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    hour, minute = map(int, settings.digest.schedule.split(":"))
    scheduler.add_job(
        _run_daily_digest,
        CronTrigger(hour=hour, minute=minute, timezone=settings.digest.timezone),
        id="daily_digest",
        name="Daily digest trigger",
        misfire_grace_time=300,
        max_instances=1,
    )
    scheduler.add_job(
        _run_gmail_poll,
        "interval",
        minutes=POLL_INTERVAL_MINUTES,
        args=[gmail_client, whitelist, anthropic_client],
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
