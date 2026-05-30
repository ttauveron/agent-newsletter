import difflib
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from config import CONFIG_DIR, Settings
from db.models import (
    AppSetting,
    Digest,
    DigestState,
    Email,
    EmailState,
    UserMessage,
    UserMessageState,
)
from db.session import get_session
from gmail.client import GmailClient
from processing.state import audit
from scheduler import reschedule_digest

logger = logging.getLogger(__name__)

_DB_KEYS = {"digest_schedule", "digest_timezone"}
_MARKDOWN_KEYS = {"user_profile", "digest_style", "learned_preferences"}
_ALLOWED_KEYS = _DB_KEYS | _MARKDOWN_KEYS
_MARKDOWN_FILES = {
    "user_profile": "user_profile.md",
    "digest_style": "digest_style.md",
    "learned_preferences": "learned_preferences.md",
}


class SendDigestRequest(BaseModel):
    digest_id: uuid.UUID
    content: str
    included_email_ids: list[uuid.UUID] = []


class SendReplyRequest(BaseModel):
    user_message_id: uuid.UUID
    content: str


class PreferencesRequest(BaseModel):
    key: str
    value: str


def create_router(gmail_client: GmailClient, settings: Settings) -> APIRouter:
    router = APIRouter()

    def _require_recipient() -> str:
        addr = settings.email.authorized_user_address
        if not addr:
            raise HTTPException(status_code=503, detail="authorized_user_address not configured")
        return addr

    @router.post("/actions/send-digest")
    def send_digest(body: SendDigestRequest):
        to = _require_recipient()
        with get_session() as session:
            digest = session.execute(
                select(Digest).where(Digest.id == body.digest_id)
            ).scalar_one_or_none()
            if not digest:
                raise HTTPException(status_code=404, detail="Digest not found")
            valid_states = {DigestState.digest_due, DigestState.digest_generation_requested}
            if digest.processing_state not in valid_states:
                raise HTTPException(
                    status_code=409,
                    detail=f"Digest in state '{digest.processing_state}', cannot send",
                )
            subject = f"Hermès — Digest du {digest.digest_date}"
            gmail_client.send_email(to=to, subject=subject, body=body.content)
            digest.processing_state = DigestState.digest_sent
            digest.content = body.content
            digest.sent_at = datetime.now(timezone.utc)
            digest.included_email_ids = [str(eid) for eid in body.included_email_ids]
            if body.included_email_ids:
                emails = (
                    session.execute(
                        select(Email).where(
                            Email.id.in_([str(eid) for eid in body.included_email_ids])
                        )
                    )
                    .scalars()
                    .all()
                )
                for email in emails:
                    email.processing_state = EmailState.sent_in_digest
            audit(
                session,
                event_type="digest_sent",
                entity_type="digest",
                entity_id=body.digest_id,
                payload={"to": to, "subject": subject, "email_count": len(body.included_email_ids)},
            )
        return {"status": "ok", "digest_id": str(body.digest_id)}

    @router.post("/actions/send-reply")
    def send_reply(body: SendReplyRequest):
        to = _require_recipient()
        with get_session() as session:
            msg = session.execute(
                select(UserMessage).where(UserMessage.id == body.user_message_id)
            ).scalar_one_or_none()
            if not msg:
                raise HTTPException(status_code=404, detail="UserMessage not found")
            original_subject = msg.subject or "Hermès"
            subject = (
                original_subject
                if original_subject.lower().startswith("re:")
                else f"Re: {original_subject}"
            )
            gmail_client.send_email(
                to=to,
                subject=subject,
                body=body.content,
                in_reply_to=msg.rfc_message_id,
                thread_id=msg.gmail_thread_id,
            )
            msg.processing_state = UserMessageState.answered
            msg.hermes_response = body.content
            audit(
                session,
                event_type="reply_sent",
                entity_type="user_message",
                entity_id=body.user_message_id,
                payload={"to": to, "subject": subject},
            )
        return {"status": "ok", "user_message_id": str(body.user_message_id)}

    @router.post("/hermes/preferences")
    def update_preferences(request: Request, body: PreferencesRequest):
        if body.key not in _ALLOWED_KEYS:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown key '{body.key}'. Allowed: {sorted(_ALLOWED_KEYS)}",
            )

        if body.key in _DB_KEYS:
            if body.key == "digest_schedule":
                _validate_schedule(body.value)
            reschedule_args = _update_db_setting(body.key, body.value)
            _maybe_reschedule(request, reschedule_args)
        else:
            _update_markdown(body.key, body.value)

        return {"status": "ok", "key": body.key}

    return router


def _validate_schedule(value: str) -> None:
    parts = value.split(":")
    valid = len(parts) == 2
    if valid:
        try:
            h, m = int(parts[0]), int(parts[1])
            valid = 0 <= h <= 23 and 0 <= m <= 59
        except ValueError:
            valid = False
    if not valid:
        raise HTTPException(status_code=422, detail="digest_schedule must be HH:MM (e.g. 08:30)")


def _update_db_setting(key: str, value: str) -> tuple[str, str]:
    """Persist key/value to app_settings, return (new_schedule, new_timezone) for reschedule."""
    companion = "digest_timezone" if key == "digest_schedule" else "digest_schedule"
    companion_default = "Europe/Zurich" if companion == "digest_timezone" else "07:00"

    with get_session() as session:
        row = session.execute(select(AppSetting).where(AppSetting.key == key)).scalar_one_or_none()
        if row:
            row.value = value
        else:
            session.add(AppSetting(key=key, value=value))

        companion_row = session.execute(
            select(AppSetting).where(AppSetting.key == companion)
        ).scalar_one_or_none()
        companion_value = companion_row.value if companion_row else companion_default

        audit(
            session,
            event_type="preference_updated",
            payload={"key": key, "value": value},
        )

    new_schedule = value if key == "digest_schedule" else companion_value
    new_timezone = value if key == "digest_timezone" else companion_value
    return new_schedule, new_timezone


def _maybe_reschedule(request: Request, reschedule_args: tuple[str, str]) -> None:
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is not None:
        reschedule_digest(scheduler, *reschedule_args)


def _update_markdown(key: str, value: str) -> None:
    path = CONFIG_DIR / _MARKDOWN_FILES[key]
    old_content = path.read_text() if path.exists() else ""
    diff = "".join(
        difflib.unified_diff(
            old_content.splitlines(keepends=True),
            value.splitlines(keepends=True),
            fromfile=f"{key}.md (before)",
            tofile=f"{key}.md (after)",
        )
    )
    path.write_text(value)
    with get_session() as session:
        audit(
            session,
            event_type="preference_markdown_updated",
            payload={"key": key, "diff": diff or "(no change)"},
        )
    logger.info("Markdown preference updated: %s", key)
