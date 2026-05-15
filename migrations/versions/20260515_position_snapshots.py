"""position_snapshots + position_alerts (Phase 4.2 indexer/notifier)

Revision ID: agent_006
Revises: agent_005
Create Date: 2026-05-15

Phase 4.2 Indexer + Notifier service tables:
  - position_snapshots: PositionHealth snapshot per active position
    on the configured cadence (default 5 min). Stores fees collected,
    IL %, in-range bool, realized fee APR over 7d/30d.
  - position_alerts: emitted alerts (out_of_range / fee_apr_drop /
    near_boundary / tvl_exodus / token_rescan / gas_favorable_rebalance).
    User acknowledges via the chat-thread system message.

The Notifier service is the canonical position-monitoring service per
spec §4 (the ninth service). Snapshots feed the chat-thread alert
cards rendered by the frontend.
"""
from alembic import op
import sqlalchemy as sa

revision = "agent_006"
down_revision = "agent_005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "position_snapshots",
        sa.Column("snapshot_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("position_id", sa.Text(), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("health_json", sa.Text(), nullable=False),
        # health_json shape (canonical):
        #   {
        #     "current_value_usd": float,
        #     "hodl_value_usd": float,
        #     "pnl_vs_hodl_usd": float,
        #     "pnl_vs_hodl_pct": float,
        #     "fees_collected_usd": float,
        #     "fees_uncollected_usd": float,
        #     "il_usd": float,
        #     "il_pct": float,
        #     "in_range": bool,                  // CL only
        #     "time_in_range_24h": float,        // CL only
        #     "time_in_range_7d": float,         // CL only
        #     "time_in_range_30d": float,        // CL only
        #     "realized_fee_apr_7d": float,
        #     "realized_fee_apr_30d": float
        #   }
    )
    op.create_index("ix_position_snapshots_pos_time", "position_snapshots",
                    ["position_id", "snapshot_at"])

    op.create_table(
        "position_alerts",
        sa.Column("alert_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("position_id", sa.Text(), nullable=False),
        sa.Column("alert_kind", sa.Text(), nullable=False),
        # alert_kind enum:
        #   out_of_range | fee_apr_drop | near_boundary | tvl_exodus |
        #   token_rescan | gas_favorable_rebalance
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_position_alerts_pos_fired", "position_alerts",
                    ["position_id", "fired_at"])
    op.create_index("ix_position_alerts_unack", "position_alerts",
                    ["acknowledged_at"])


def downgrade() -> None:
    op.drop_index("ix_position_alerts_unack", table_name="position_alerts")
    op.drop_index("ix_position_alerts_pos_fired", table_name="position_alerts")
    op.drop_table("position_alerts")
    op.drop_index("ix_position_snapshots_pos_time", table_name="position_snapshots")
    op.drop_table("position_snapshots")
