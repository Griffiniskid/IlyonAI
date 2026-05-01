"""agent_plans

Revision ID: agent_004
Revises: agent_003
Create Date: 2026-06-01

Creates agent_plans table for persisted execution plans.
"""
from alembic import op
import sqlalchemy as sa

revision = 'agent_004'
down_revision = 'agent_003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_plans",
        sa.Column("plan_id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_plans_user_id", "agent_plans", ["user_id"])
    op.create_index("ix_agent_plans_status", "agent_plans", ["status"])
    op.create_index("ix_agent_plans_user_status", "agent_plans", ["user_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_agent_plans_user_status", table_name="agent_plans")
    op.drop_index("ix_agent_plans_status", table_name="agent_plans")
    op.drop_index("ix_agent_plans_user_id", table_name="agent_plans")
    op.drop_table("agent_plans")
