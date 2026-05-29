from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


class GmailClient:
    def __init__(self, token_path: str):
        self.token_path = Path(token_path)
        self._service = None

    def _load_credentials(self) -> Credentials:
        if not self.token_path.exists():
            raise RuntimeError(
                f"Gmail token not found at {self.token_path}. "
                "Run 'python -m gmail.auth' to authenticate."
            )
        creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(self.token_path, "w") as f:
                f.write(creds.to_json())
        if not creds.valid:
            raise RuntimeError("Gmail credentials are invalid. Re-run 'python -m gmail.auth'.")
        return creds

    @property
    def service(self):
        if not self._service:
            creds = self._load_credentials()
            self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def get_unread_messages(self, max_results: int = 100) -> list[dict]:
        result = (
            self.service.users()
            .messages()
            .list(userId="me", labelIds=["INBOX", "UNREAD"], maxResults=max_results)
            .execute()
        )
        return result.get("messages", [])

    def get_message(self, message_id: str) -> dict:
        return (
            self.service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )

    def mark_as_read(self, message_id: str) -> None:
        self.service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["UNREAD"]},
        ).execute()
