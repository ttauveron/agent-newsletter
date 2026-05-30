import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class EmailState(str, enum.Enum):
    received = "received"
    ingested = "ingested"
    cleaned = "cleaned"
    summarized = "summarized"
    ready_for_hermes = "ready_for_hermes"
    selected_for_digest = "selected_for_digest"
    ignored_by_hermes = "ignored_by_hermes"
    sent_in_digest = "sent_in_digest"
    archived = "archived"


class DigestState(str, enum.Enum):
    digest_due = "digest_due"
    digest_generation_requested = "digest_generation_requested"
    digest_generated = "digest_generated"
    digest_sent = "digest_sent"
    digest_failed = "digest_failed"


class UserMessageState(str, enum.Enum):
    user_message_received = "user_message_received"
    passed_to_hermes = "passed_to_hermes"
    answered = "answered"
    feedback_recorded = "feedback_recorded"
    preference_updated = "preference_updated"


class Email(Base):
    __tablename__ = "emails"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    gmail_message_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    gmail_thread_id: Mapped[Optional[str]] = mapped_column(String(255))
    sender_email: Mapped[str] = mapped_column(String(255), nullable=False)
    sender_name: Mapped[Optional[str]] = mapped_column(String(255))
    subject: Mapped[Optional[str]] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_content: Mapped[Optional[str]] = mapped_column(Text)
    cleaned_content: Mapped[Optional[str]] = mapped_column(Text)
    source_category: Mapped[Optional[str]] = mapped_column(String(100))
    processing_state: Mapped[str] = mapped_column(
        String(50), nullable=False, default=EmailState.received
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    summary: Mapped[Optional["Summary"]] = relationship(
        "Summary", back_populates="email", uselist=False
    )


class Summary(Base):
    __tablename__ = "summaries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("emails.id"), nullable=False
    )
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    key_points: Mapped[Optional[dict]] = mapped_column(JSONB)
    tags: Mapped[Optional[dict]] = mapped_column(JSONB)
    model_used: Mapped[Optional[str]] = mapped_column(String(100))
    tokens_input: Mapped[Optional[int]] = mapped_column(Integer)
    tokens_output: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    email: Mapped["Email"] = relationship("Email", back_populates="summary")


class Digest(Base):
    __tablename__ = "digests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    digest_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text)
    included_email_ids: Mapped[Optional[list]] = mapped_column(JSONB)
    processing_state: Mapped[str] = mapped_column(
        String(50), nullable=False, default=DigestState.digest_due
    )
    hermes_reasoning: Mapped[Optional[str]] = mapped_column(Text)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class UserMessage(Base):
    __tablename__ = "user_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    gmail_message_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    gmail_thread_id: Mapped[Optional[str]] = mapped_column(String(255))
    rfc_message_id: Mapped[Optional[str]] = mapped_column(Text)
    sender_email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processing_state: Mapped[str] = mapped_column(
        String(50), nullable=False, default=UserMessageState.user_message_received
    )
    hermes_response: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(String(50))
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class ProcessingEvent(Base):
    __tablename__ = "processing_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    from_state: Mapped[Optional[str]] = mapped_column(String(50))
    to_state: Mapped[str] = mapped_column(String(50), nullable=False)
    event_metadata: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
