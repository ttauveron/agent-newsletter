import base64
from datetime import timezone

from gmail.parser import parse_message


def b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def make_message(
    msg_id: str = "msg123",
    thread_id: str = "thread123",
    from_header: str = "John Doe <john@example.com>",
    subject: str = "Test Subject",
    date: str = "Mon, 01 Jan 2024 12:00:00 +0000",
    mime_type: str = "text/plain",
    body_text: str = "Hello world",
    parts: list = None,
) -> dict:
    headers = [
        {"name": "From", "value": from_header},
        {"name": "Subject", "value": subject},
        {"name": "Date", "value": date},
    ]
    payload: dict = {"headers": headers, "mimeType": mime_type}
    if parts is not None:
        payload["parts"] = parts
    else:
        payload["body"] = {"data": b64(body_text)}
    return {"id": msg_id, "threadId": thread_id, "payload": payload}


# --- IDs ---


def test_gmail_message_id():
    parsed = parse_message(make_message(msg_id="abc123"))
    assert parsed.gmail_message_id == "abc123"


def test_gmail_thread_id():
    parsed = parse_message(make_message(thread_id="thread456"))
    assert parsed.gmail_thread_id == "thread456"


# --- Sender parsing ---


def test_sender_email_extracted():
    parsed = parse_message(make_message(from_header="John Doe <john@example.com>"))
    assert parsed.sender_email == "john@example.com"


def test_sender_name_extracted():
    parsed = parse_message(make_message(from_header="John Doe <john@example.com>"))
    assert parsed.sender_name == "John Doe"


def test_sender_email_only_no_name():
    parsed = parse_message(make_message(from_header="john@example.com"))
    assert parsed.sender_email == "john@example.com"
    assert parsed.sender_name is None


def test_sender_email_lowercased():
    parsed = parse_message(make_message(from_header="<JOHN@EXAMPLE.COM>"))
    assert parsed.sender_email == "john@example.com"


# --- Subject ---


def test_subject_parsed():
    parsed = parse_message(make_message(subject="Weekly Digest #42"))
    assert parsed.subject == "Weekly Digest #42"


# --- Date ---


def test_received_at_has_timezone():
    parsed = parse_message(make_message(date="Mon, 01 Jan 2024 12:00:00 +0000"))
    assert parsed.received_at.tzinfo is not None


def test_received_at_invalid_date_fallback():
    parsed = parse_message(make_message(date="not a date at all"))
    assert parsed.received_at.tzinfo == timezone.utc


# --- Body extraction ---


def test_plain_text_body():
    parsed = parse_message(make_message(mime_type="text/plain", body_text="Hello world"))
    assert parsed.raw_content == "Hello world"
    assert parsed.content_type == "text/plain"


def test_html_body():
    parsed = parse_message(make_message(mime_type="text/html", body_text="<p>Hello</p>"))
    assert parsed.raw_content == "<p>Hello</p>"
    assert parsed.content_type == "text/html"


def test_multipart_prefers_plain_over_html():
    parts = [
        {"mimeType": "text/plain", "body": {"data": b64("plain text")}},
        {"mimeType": "text/html", "body": {"data": b64("<p>html</p>")}},
    ]
    parsed = parse_message(make_message(mime_type="multipart/alternative", parts=parts))
    assert parsed.raw_content == "plain text"
    assert parsed.content_type == "text/plain"


def test_multipart_falls_back_to_html():
    parts = [
        {"mimeType": "text/html", "body": {"data": b64("<p>html only</p>")}},
    ]
    parsed = parse_message(make_message(mime_type="multipart/alternative", parts=parts))
    assert parsed.raw_content == "<p>html only</p>"
    assert parsed.content_type == "text/html"


def test_multipart_empty_plain_falls_back_to_html():
    parts = [
        {"mimeType": "text/plain", "body": {"data": b64("")}},
        {"mimeType": "text/html", "body": {"data": b64("<p>html</p>")}},
    ]
    parsed = parse_message(make_message(mime_type="multipart/alternative", parts=parts))
    assert parsed.content_type == "text/html"
