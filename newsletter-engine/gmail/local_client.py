import base64
import json
import uuid
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Any


class LocalEmailClient:
    def __init__(self, mailbox_dir: str):
        self.mailbox_dir = Path(mailbox_dir)
        self.inbox_dir = self.mailbox_dir / "inbox"
        self.outbox_dir = self.mailbox_dir / "outbox"
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.outbox_dir.mkdir(parents=True, exist_ok=True)

    def get_unread_messages(self, max_results: int = 100) -> list[dict]:
        unread = []
        for path in sorted(self.inbox_dir.glob("*.json")):
            record = self._read_json(path)
            if record.get("unread", True):
                unread.append({"id": record["id"]})
            if len(unread) >= max_results:
                break
        return unread

    def get_message(self, message_id: str) -> dict:
        record = self._read_record(message_id)
        return _to_gmail_message(record)

    def mark_as_read(self, message_id: str) -> None:
        path = self._record_path(message_id)
        record = self._read_json(path)
        record["unread"] = False
        self._write_json(path, record)

    def send_email(self, to: str, subject: str, body: str) -> None:
        sent_at = datetime.now(timezone.utc)
        record = {
            "id": f"out-{sent_at.strftime('%Y%m%d%H%M%S%f')}-{uuid.uuid4().hex[:8]}",
            "to": to,
            "subject": subject,
            "body": body,
            "sent_at": sent_at.isoformat(),
        }
        self._write_json(self.outbox_dir / f"{record['id']}.json", record)

    def inject_email(
        self,
        sender_email: str,
        subject: str,
        body: str,
        content_type: str = "text/plain",
        sender_name: str | None = None,
        received_at: datetime | None = None,
        message_id: str | None = None,
    ) -> dict:
        if content_type not in {"text/plain", "text/html"}:
            raise ValueError("content_type must be text/plain or text/html")

        msg_id = message_id or f"local-{uuid.uuid4()}"
        now = received_at or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        record = {
            "id": msg_id,
            "thread_id": f"thread-{msg_id}",
            "sender_email": sender_email,
            "sender_name": sender_name,
            "subject": subject,
            "date": format_datetime(now),
            "body": body,
            "content_type": content_type,
            "unread": True,
        }
        self._write_json(self._record_path(msg_id), record)
        return {"id": msg_id}

    def list_outbox(self) -> list[dict]:
        return [self._read_json(path) for path in sorted(self.outbox_dir.glob("*.json"))]

    def _record_path(self, message_id: str) -> Path:
        return self.inbox_dir / f"{message_id}.json"

    def _read_record(self, message_id: str) -> dict:
        return self._read_json(self._record_path(message_id))

    @staticmethod
    def _read_json(path: Path) -> dict:
        with path.open() as f:
            return json.load(f)

    @staticmethod
    def _write_json(path: Path, data: dict) -> None:
        with path.open("w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")


def _to_gmail_message(record: dict[str, Any]) -> dict:
    from_header = record["sender_email"]
    if record.get("sender_name"):
        from_header = f"{record['sender_name']} <{record['sender_email']}>"

    payload = {
        "headers": [
            {"name": "From", "value": from_header},
            {"name": "Subject", "value": record.get("subject", "")},
            {"name": "Date", "value": record["date"]},
        ],
        "mimeType": record.get("content_type", "text/plain"),
        "body": {"data": _b64(record.get("body", ""))},
    }
    return {
        "id": record["id"],
        "threadId": record.get("thread_id", record["id"]),
        "payload": payload,
    }


def _b64(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode()
