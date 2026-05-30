"""Add threading fields to user_messages

Revision ID: 003
Revises: 002
Create Date: 2026-05-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_messages", sa.Column("gmail_thread_id", sa.String(255), nullable=True))
    op.add_column("user_messages", sa.Column("rfc_message_id", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_messages", "rfc_message_id")
    op.drop_column("user_messages", "gmail_thread_id")
