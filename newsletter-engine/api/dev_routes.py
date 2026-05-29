from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from gmail.local_client import LocalEmailClient


class InjectEmailRequest(BaseModel):
    sender_email: str
    subject: str
    body: str
    content_type: str = "text/plain"
    sender_name: str | None = None
    received_at: datetime | None = None
    message_id: str | None = None


def create_dev_router(email_client: LocalEmailClient) -> APIRouter:
    router = APIRouter(prefix="/dev", tags=["dev"])

    @router.post("/emails")
    def inject_email(body: InjectEmailRequest):
        try:
            message = email_client.inject_email(
                sender_email=body.sender_email,
                sender_name=body.sender_name,
                subject=body.subject,
                body=body.body,
                content_type=body.content_type,
                received_at=body.received_at,
                message_id=body.message_id,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        return {"status": "ok", "message": message}

    @router.get("/outbox")
    def outbox():
        return {"messages": email_client.list_outbox()}

    return router
