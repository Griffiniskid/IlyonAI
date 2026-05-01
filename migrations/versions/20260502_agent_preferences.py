"""agent_preferences

Revision ID: agent_002
Revises: agent_001
Create Date: 2026-05-02

Creates agent_preferences table for user-specific trading and risk settings.
"""
from alembic import op
import sqlalchemy as sa

revision = 'agent_002'
down_revision = 'agent_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_preferences",
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column("risk_budget", sa.String(32), nullable=False, server_default="balanced"),
        sa.Column("preferred_chains", sa.JSON(), nullable=True),
        sa.Column("blocked_protocols", sa.JSON(), nullable=True),
        sa.Column("gas_cap_usd", sa.Float(), nullable=True),
        sa.Column("slippage_cap_bps", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("notional_double_confirm_usd", sa.Float(), nullable=False, server_default="10000"),
        sa.Column("auto_rebalance_opt_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rebalance_auth_signature", sa.String(512), nullable=True),
        sa.Column("rebalance_auth_nonce", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("agent_preferences")
