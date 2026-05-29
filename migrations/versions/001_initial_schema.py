"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "emails",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("gmail_message_id", sa.String(255), nullable=False),
        sa.Column("gmail_thread_id", sa.String(255)),
        sa.Column("sender_email", sa.String(255), nullable=False),
        sa.Column("sender_name", sa.String(255)),
        sa.Column("subject", sa.Text),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_content", sa.Text),
        sa.Column("cleaned_content", sa.Text),
        sa.Column("source_category", sa.String(100)),
        sa.Column("processing_state", sa.String(50), nullable=False, server_default="received"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("gmail_message_id", name="uq_emails_gmail_message_id"),
    )
    op.create_index("ix_emails_processing_state", "emails", ["processing_state"])
    op.create_index("ix_emails_sender_email", "emails", ["sender_email"])
    op.create_index("ix_emails_received_at", "emails", ["received_at"])

    op.create_table(
        "summaries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email_id", UUID(as_uuid=True), sa.ForeignKey("emails.id"), nullable=False),
        sa.Column("summary_text", sa.Text, nullable=False),
        sa.Column("key_points", JSONB),
        sa.Column("tags", JSONB),
        sa.Column("model_used", sa.String(100)),
        sa.Column("tokens_input", sa.Integer),
        sa.Column("tokens_output", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_summaries_email_id", "summaries", ["email_id"])

    op.create_table(
        "digests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("digest_date", sa.Date, nullable=False),
        sa.Column("content", sa.Text),
        sa.Column("included_email_ids", JSONB),
        sa.Column("processing_state", sa.String(50), nullable=False, server_default="digest_due"),
        sa.Column("hermes_reasoning", sa.Text),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_digests_digest_date", "digests", ["digest_date"])
    op.create_index("ix_digests_processing_state", "digests", ["processing_state"])

    op.create_table(
        "user_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("gmail_message_id", sa.String(255), nullable=False),
        sa.Column("sender_email", sa.String(255), nullable=False),
        sa.Column("subject", sa.Text),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processing_state", sa.String(50), nullable=False, server_default="user_message_received"),
        sa.Column("hermes_response", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("gmail_message_id", name="uq_user_messages_gmail_message_id"),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(50)),
        sa.Column("entity_id", UUID(as_uuid=True)),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_audit_logs_event_type", "audit_logs", ["event_type"])
    op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    op.create_table(
        "processing_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("from_state", sa.String(50)),
        sa.Column("to_state", sa.String(50), nullable=False),
        sa.Column("event_metadata", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_processing_events_entity_id", "processing_events", ["entity_id"])
    op.create_index("ix_processing_events_created_at", "processing_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("processing_events")
    op.drop_table("audit_logs")
    op.drop_table("user_messages")
    op.drop_table("digests")
    op.drop_table("summaries")
    op.drop_table("emails")
