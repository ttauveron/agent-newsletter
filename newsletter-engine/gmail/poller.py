import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Email, UserMessage
from gmail.client import GmailClient
from gmail.parser import parse_message
from processing.ingestion import ingest_newsletter, ingest_user_message
from processing.state import audit
from processing.whitelist import EmailAction, WhitelistFilter

logger = logging.getLogger(__name__)


def poll(client: GmailClient, whitelist: WhitelistFilter, session: Session) -> dict:
    messages = client.get_unread_messages()
    stats = {"newsletters": 0, "user_messages": 0, "ignored": 0, "duplicates": 0, "errors": 0}

    for stub in messages:
        message_id = stub["id"]
        try:
            _process_message(message_id, client, whitelist, session, stats)
        except Exception:
            logger.exception("Failed to process message %s", message_id)
            stats["errors"] += 1

    session.commit()
    logger.info("Poll complete: %s", stats)
    return stats


def _process_message(
    message_id: str,
    client: GmailClient,
    whitelist: WhitelistFilter,
    session: Session,
    stats: dict,
) -> None:
    already_email = session.execute(
        select(Email).where(Email.gmail_message_id == message_id)
    ).scalar_one_or_none()
    already_msg = session.execute(
        select(UserMessage).where(UserMessage.gmail_message_id == message_id)
    ).scalar_one_or_none()

    if already_email or already_msg:
        stats["duplicates"] += 1
        return

    message = client.get_message(message_id)
    parsed = parse_message(message)
    result = whitelist.classify(parsed.sender_email)

    if result.action == EmailAction.ignored:
        stats["ignored"] += 1
        audit(
            session,
            event_type="email_ignored_not_whitelisted",
            payload={"gmail_message_id": message_id, "sender_email": parsed.sender_email},
        )
        return  # intentionally left unread

    if result.action == EmailAction.user_message:
        ingest_user_message(parsed, session)
        client.mark_as_read(message_id)
        stats["user_messages"] += 1
        logger.info("User message: %s", parsed.subject)

    elif result.action == EmailAction.newsletter:
        ingest_newsletter(parsed, result, session)
        client.mark_as_read(message_id)
        stats["newsletters"] += 1
        logger.info(
            "Newsletter: %s from %s [%s]", parsed.subject, parsed.sender_email, result.category
        )
