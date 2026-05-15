"""debridge_events table for §6c webhook persistence

Revision ID: agent_008
Revises: agent_007
Create Date: 2026-05-15

The /api/v1/debridge/webhook route currently caches resolved DLN order
events in aiohttp app state (lost on restart). This migration adds a
table so the runtime rebuild loop can survive process restarts and
reconcile against the DLN status API only when the cache is stale.

Schema mirrors composed_plan.FillResolution shape — minimal fields the
rebuild orchestrator needs to swap the bridge step into REBUILDING and
re-emit the deposit leg with the realised amount.
"""
from alembic import op
import sqlalchemy as sa

revision = "agent_008"
down_revision = "agent_007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "debridge_events",
        sa.Column("order_id", sa.Text(), primary_key=True),
        sa.Column("state", sa.Text(), nullable=False),     # filled | cancelled | failed | created
        sa.Column("actual_dst_amount", sa.Numeric(), nullable=True),
        sa.Column("realized_slippage_bps", sa.Integer(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("raw_json", sa.JSON(), nullable=True),
    )
    op.create_index(
        "ix_debridge_events_state_received",
        "debridge_events",
        ["state", "received_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_debridge_events_state_received", table_name="debridge_events")
    op.drop_table("debridge_events")
