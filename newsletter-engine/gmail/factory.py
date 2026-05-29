import os

from gmail.client import GmailClient
from gmail.local_client import LocalEmailClient


def create_email_client() -> GmailClient | LocalEmailClient:
    backend = os.environ.get("EMAIL_BACKEND", "gmail").lower()
    if backend == "gmail":
        return GmailClient(
            token_path=os.environ.get("GMAIL_TOKEN_PATH", "/app/config/gmail_token.json")
        )
    if backend == "local":
        return LocalEmailClient(
            mailbox_dir=os.environ.get("LOCAL_MAILBOX_DIR", "/app/config/dev_mailbox")
        )
    raise RuntimeError("EMAIL_BACKEND must be 'gmail' or 'local'")
