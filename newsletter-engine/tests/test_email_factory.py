from gmail.client import GmailClient
from gmail.factory import create_email_client
from gmail.local_client import LocalEmailClient


def test_create_email_client_defaults_to_gmail(monkeypatch):
    monkeypatch.delenv("EMAIL_BACKEND", raising=False)
    monkeypatch.setenv("GMAIL_TOKEN_PATH", "/tmp/token.json")

    client = create_email_client()

    assert isinstance(client, GmailClient)
    assert str(client.token_path) == "/tmp/token.json"


def test_create_email_client_local(monkeypatch, tmp_path):
    monkeypatch.setenv("EMAIL_BACKEND", "local")
    monkeypatch.setenv("LOCAL_MAILBOX_DIR", str(tmp_path))

    client = create_email_client()

    assert isinstance(client, LocalEmailClient)
    assert client.mailbox_dir == tmp_path


def test_create_email_client_rejects_unknown_backend(monkeypatch):
    monkeypatch.setenv("EMAIL_BACKEND", "imap")

    try:
        create_email_client()
    except RuntimeError as e:
        assert "EMAIL_BACKEND" in str(e)
    else:
        raise AssertionError("Expected RuntimeError")
