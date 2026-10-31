"""paypal credentials, webhook ledger, payment audit

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("merchants", sa.Column("paypal_webhook_id_enc", sa.Text(), nullable=True))

    op.create_table(
        "paypal_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("signature_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_paypal_webhook_events_event_id",
        "paypal_webhook_events",
        ["event_id"],
        unique=True,
    )
    op.create_index(
        "ix_paypal_webhook_events_merchant_id",
        "paypal_webhook_events",
        ["merchant_id"],
    )

    op.create_table(
        "payment_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("result", sa.String(length=32), nullable=False, server_default="success"),
        sa.Column(
            "detail",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "action IN ('create_link', 'refund', 'mark_paid', 'receipt', 'expire')",
            name="ck_payment_actions_action",
        ),
        sa.CheckConstraint(
            "trigger IN ('agent', 'webhook', 'staff', 'system')",
            name="ck_payment_actions_trigger",
        ),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payment_actions_merchant_id", "payment_actions", ["merchant_id"])
    op.create_index(
        "ix_payment_actions_order_created", "payment_actions", ["order_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_payment_actions_order_created", table_name="payment_actions")
    op.drop_index("ix_payment_actions_merchant_id", table_name="payment_actions")
    op.drop_table("payment_actions")
    op.drop_index("ix_paypal_webhook_events_merchant_id", table_name="paypal_webhook_events")
    op.drop_index("ix_paypal_webhook_events_event_id", table_name="paypal_webhook_events")
    op.drop_table("paypal_webhook_events")
    op.drop_column("merchants", "paypal_webhook_id_enc")
