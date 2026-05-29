from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dev_routes import create_dev_router
from gmail.local_client import LocalEmailClient


def _client(tmp_path) -> tuple[TestClient, LocalEmailClient]:
    email_client = LocalEmailClient(str(tmp_path))
    app = FastAPI()
    app.include_router(create_dev_router(email_client))
    return TestClient(app), email_client


def test_dev_inject_email(tmp_path):
    client, email_client = _client(tmp_path)

    resp = client.post(
        "/dev/emails",
        json={
            "sender_email": "news@example.com",
            "subject": "Weekly Brief",
            "body": "Hello",
        },
    )

    assert resp.status_code == 200
    message_id = resp.json()["message"]["id"]
    assert email_client.get_unread_messages() == [{"id": message_id}]


def test_dev_inject_email_rejects_bad_content_type(tmp_path):
    client, _ = _client(tmp_path)

    resp = client.post(
        "/dev/emails",
        json={
            "sender_email": "news@example.com",
            "subject": "Weekly Brief",
            "body": "Hello",
            "content_type": "application/json",
        },
    )

    assert resp.status_code == 422


def test_dev_outbox_lists_sent_messages(tmp_path):
    client, email_client = _client(tmp_path)
    email_client.send_email(to="user@example.com", subject="Reply", body="Hello")

    resp = client.get("/dev/outbox")

    assert resp.status_code == 200
    assert resp.json()["messages"][0]["to"] == "user@example.com"
