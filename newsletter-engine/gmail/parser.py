import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parseaddr, parsedate_to_datetime
from typing import Optional


@dataclass
class ParsedEmail:
    gmail_message_id: str
    gmail_thread_id: str
    sender_email: str
    sender_name: Optional[str]
    subject: Optional[str]
    received_at: datetime
    raw_content: str
    content_type: str  # "text/plain" or "text/html"


def _decode_part(part: dict) -> Optional[str]:
    data = part.get("body", {}).get("data")
    if not data:
        return None
    return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")


def _extract_body(payload: dict) -> tuple[str, str]:
    """Return (content, content_type). Prefers text/plain, falls back to text/html."""
    mime_type = payload.get("mimeType", "")

    if mime_type == "text/plain":
        return _decode_part(payload) or "", "text/plain"

    if mime_type == "text/html":
        return _decode_part(payload) or "", "text/html"

    if mime_type.startswith("multipart/"):
        parts = payload.get("parts", [])
        for part in parts:
            if part.get("mimeType") == "text/plain":
                content = _decode_part(part)
                if content:
                    return content, "text/plain"
        for part in parts:
            if part.get("mimeType") == "text/html":
                content = _decode_part(part)
                if content:
                    return content, "text/html"
        for part in parts:
            if part.get("mimeType", "").startswith("multipart/"):
                return _extract_body(part)

    return "", "text/plain"


def parse_message(message: dict) -> ParsedEmail:
    headers = {
        h["name"].lower(): h["value"]
        for h in message["payload"].get("headers", [])
    }

    sender_name, sender_email = parseaddr(headers.get("from", ""))

    date_str = headers.get("date", "")
    try:
        received_at = parsedate_to_datetime(date_str)
        if received_at.tzinfo is None:
            received_at = received_at.replace(tzinfo=timezone.utc)
    except Exception:
        received_at = datetime.now(timezone.utc)

    raw_content, content_type = _extract_body(message["payload"])

    return ParsedEmail(
        gmail_message_id=message["id"],
        gmail_thread_id=message.get("threadId", ""),
        sender_email=sender_email.lower(),
        sender_name=sender_name or None,
        subject=headers.get("subject"),
        received_at=received_at,
        raw_content=raw_content,
        content_type=content_type,
    )
