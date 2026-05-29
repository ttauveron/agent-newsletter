from datetime import datetime, timezone

from gmail.local_client import LocalEmailClient
from gmail.parser import parse_message


def test_local_client_injects_unread_message(tmp_path):
    client = LocalEmailClient(str(tmp_path))
    injected = client.inject_email(
        sender_email="news@example.com",
        sender_name="News",
        subject="Weekly Brief",
        body="Hello",
        received_at=datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc),
    )

    assert client.get_unread_messages() == [{"id": injected["id"]}]


def test_local_client_returns_gmail_shaped_message(tmp_path):
    client = LocalEmailClient(str(tmp_path))
    injected = client.inject_email(
        sender_email="news@example.com",
        sender_name="News",
        subject="Weekly Brief",
        body="Hello",
        received_at=datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc),
    )

    parsed = parse_message(client.get_message(injected["id"]))

    assert parsed.sender_email == "news@example.com"
    assert parsed.sender_name == "News"
    assert parsed.subject == "Weekly Brief"
    assert parsed.raw_content == "Hello"


def test_local_client_marks_message_as_read(tmp_path):
    client = LocalEmailClient(str(tmp_path))
    injected = client.inject_email(
        sender_email="news@example.com",
        subject="Weekly Brief",
        body="Hello",
    )

    client.mark_as_read(injected["id"])

    assert client.get_unread_messages() == []


def test_local_client_writes_outbox(tmp_path):
    client = LocalEmailClient(str(tmp_path))

    client.send_email(to="user@example.com", subject="Digest", body="Today")

    outbox = client.list_outbox()
    assert len(outbox) == 1
    assert outbox[0]["to"] == "user@example.com"
    assert outbox[0]["subject"] == "Digest"
    assert outbox[0]["body"] == "Today"
