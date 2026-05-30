import uuid

from sqlalchemy.orm import Session

from db.models import Email, EmailState, UserMessage, UserMessageState
from gmail.parser import ParsedEmail
from processing.cleaner import clean_content
from processing.state import audit, transition_state
from processing.whitelist import WhitelistResult


def ingest_newsletter(
    parsed: ParsedEmail,
    whitelist_result: WhitelistResult,
    session: Session,
) -> Email:
    email_id = uuid.uuid4()
    cleaned = clean_content(parsed.raw_content, parsed.content_type)

    email = Email(
        id=email_id,
        gmail_message_id=parsed.gmail_message_id,
        gmail_thread_id=parsed.gmail_thread_id,
        sender_email=parsed.sender_email,
        sender_name=parsed.sender_name,
        subject=parsed.subject,
        received_at=parsed.received_at,
        raw_content=parsed.raw_content,
        cleaned_content=cleaned,
        source_category=whitelist_result.category,
        processing_state=EmailState.cleaned,
    )
    session.add(email)

    transition_state(session, "email", email_id, EmailState.received)
    transition_state(
        session, "email", email_id, EmailState.ingested, from_state=EmailState.received
    )
    transition_state(session, "email", email_id, EmailState.cleaned, from_state=EmailState.ingested)
    audit(
        session,
        event_type="email_ingested",
        entity_type="email",
        entity_id=email_id,
        payload={
            "gmail_message_id": parsed.gmail_message_id,
            "sender_email": parsed.sender_email,
            "subject": parsed.subject,
            "category": whitelist_result.category,
        },
    )

    return email


def ingest_user_message(parsed: ParsedEmail, session: Session) -> UserMessage:
    msg_id = uuid.uuid4()

    msg = UserMessage(
        id=msg_id,
        gmail_message_id=parsed.gmail_message_id,
        gmail_thread_id=parsed.gmail_thread_id or None,
        rfc_message_id=parsed.rfc_message_id,
        sender_email=parsed.sender_email,
        subject=parsed.subject,
        content=parsed.raw_content,
        received_at=parsed.received_at,
        processing_state=UserMessageState.user_message_received,
    )
    session.add(msg)

    audit(
        session,
        event_type="user_message_received",
        entity_type="user_message",
        entity_id=msg_id,
        payload={
            "gmail_message_id": parsed.gmail_message_id,
            "sender_email": parsed.sender_email,
            "subject": parsed.subject,
        },
    )

    return msg
