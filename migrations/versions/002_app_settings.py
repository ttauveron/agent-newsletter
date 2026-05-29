"""Add app_settings table

Revision ID: 002
Revises: 001
Create Date: 2026-05-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    op.execute(
        """
        INSERT INTO app_settings (key, value) VALUES
          ('digest_schedule', '07:00'),
          ('digest_timezone', 'Europe/Zurich')
        """
    )

    op.execute("GRANT SELECT ON app_settings TO hermes_readonly")


def downgrade() -> None:
    op.drop_table("app_settings")
