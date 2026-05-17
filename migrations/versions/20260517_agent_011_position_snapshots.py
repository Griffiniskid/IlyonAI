"""position_snapshots: V7-022 PositionHealth payload column + DESC index.

Revision ID: agent_011
Revises: agent_010
Create Date: 2026-05-17

Spec ref: dev-plan §V7-022, spec §4 (PositionHealth snapshots persisted
every 5 min by the Notifier service, surfaced to the chat-thread alert
cards rendered by the frontend).

The `position_snapshots` table was originally introduced by agent_006
(2026-05-15) with a `health_json` TEXT column carrying a canonical
PositionHealth blob. V7-022 layers two additive changes on top so the
table can serve as the persistent snapshot store for the new
position-monitor sidecar without breaking the existing notifier path:

  1. `payload` JSON column — new structured snapshot payload. Stored
     as JSON so it works on both PostgreSQL (native JSONB-compatible)
     and SQLite (the unit-test backing). PostgreSQL deployments can
     migrate this to JSONB out-of-band; SQLAlchemy's `sa.JSON()` type
     adapts to the backend automatically. Existing `health_json` rows
     are untouched; new writers should populate `payload`.

  2. `ix_position_snapshots_pos_time_desc` — descending-order index on
     (position_id, snapshot_at DESC). The legacy index from agent_006
     is ascending; the monitor's hot path is "latest N snapshots for
     this position" which benefits from a DESC index on PostgreSQL.
     SQLite ignores the DESC qualifier but still uses the composite.

The position-monitor sidecar (src/defi/position_monitor/, V7-021)
writes via the helpers in src/storage/repositories/position_snapshot.py;
this migration is the schema half of that wire-up.
"""
from alembic import op
import sqlalchemy as sa


revision = "agent_011"
down_revision = "agent_010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Additive column — preserves all rows written via the agent_006
    # `health_json` path. New monitor writes populate `payload`.
    op.add_column(
        "position_snapshots",
        sa.Column("payload", sa.JSON(), nullable=True),
    )
    # DESC composite index for "latest N snapshots for this position".
    # PostgreSQL honours the DESC ordering; SQLite reads it as plain
    # composite — both back the monitor's hot path efficiently.
    op.create_index(
        "ix_position_snapshots_pos_time_desc",
        "position_snapshots",
        ["position_id", sa.text("snapshot_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_position_snapshots_pos_time_desc",
        table_name="position_snapshots",
    )
    op.drop_column("position_snapshots", "payload")
