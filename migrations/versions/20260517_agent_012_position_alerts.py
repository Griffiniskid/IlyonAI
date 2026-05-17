"""position_alerts: V7-023 spec-canonical columns (alert_type / payload / dismissed_at)

Revision ID: agent_012
Revises: agent_011
Create Date: 2026-05-17

The `position_alerts` table was first created by Phase 4.2 (agent_006,
20260515_position_snapshots.py) with columns:

    alert_id          BIGINT  PK
    position_id       TEXT    NOT NULL
    alert_kind        TEXT    NOT NULL
    fired_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
    payload_json      TEXT    NOT NULL
    acknowledged_at   TIMESTAMPTZ NULL

V7-023 freezes the spec column names that the PositionHealth detectors
(§4 — out_of_range / fee_apr_drop / tvl_exodus / gas_favorable) write
through, and that the chat-thread alert renderer reads back:

    alert_type        TEXT    NULLABLE   (canonical name for "alert kind")
    payload           JSONB / TEXT NULLABLE  (canonical JSON column;
                                              JSONB on PG, TEXT on SQLite)
    dismissed_at      TIMESTAMPTZ NULLABLE   (canonical "user dismissed"
                                              timestamp; mirrors the
                                              older acknowledged_at semantics)

This migration is *additive only*: the existing agent_006 columns stay
in place so historical rows and the older Notifier write path don't
break. The new spec columns are added alongside, and a covering index
`(position_id, dismissed_at)` is created to make
`get_open_alerts(position_id)` a single index seek.

Down-revision chain after this migration:
    agent_012 -> agent_011 (V7-022, position_snapshots) -> agent_010
    (V7-004, Solana position state) -> agent_009 -> ... -> 001.

Spec ref: IlyonAi_Development_Plan_v2.md V7-023; runtime emitters at
src/defi/position_monitor/detectors.py (added in V7-024).
"""
from alembic import op
import sqlalchemy as sa


revision = "agent_012"
down_revision = "agent_011"
branch_labels = None
depends_on = None


def _jsonb_or_text() -> sa.types.TypeEngine:
    """Return JSONB on PostgreSQL, JSON elsewhere.

    The spec asks for JSONB; SQLite (used in unit tests) doesn't have
    JSONB so we fall back to plain JSON which SQLAlchemy maps to TEXT.
    The Python-side repo always serialises with json.dumps so the
    on-disk shape is stable across dialects.
    """
    bind = op.get_bind() if hasattr(op, "get_bind") else None
    try:
        dialect_name = bind.dialect.name if bind is not None else ""
    except Exception:
        dialect_name = ""
    if dialect_name == "postgresql":
        from sqlalchemy.dialects.postgresql import JSONB

        return JSONB()
    return sa.JSON()


def upgrade() -> None:
    # alert_type: canonical spec name (mirror of agent_006.alert_kind).
    op.add_column(
        "position_alerts",
        sa.Column("alert_type", sa.Text(), nullable=True),
    )
    # payload: canonical JSONB column (mirror of agent_006.payload_json
    # which is TEXT).
    op.add_column(
        "position_alerts",
        sa.Column("payload", _jsonb_or_text(), nullable=True),
    )
    # dismissed_at: canonical "user dismissed" timestamp (mirror of
    # agent_006.acknowledged_at).
    op.add_column(
        "position_alerts",
        sa.Column(
            "dismissed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    # Covering index for `get_open_alerts(position_id)` — single seek
    # into (position_id, dismissed_at IS NULL) bucket.
    op.create_index(
        "ix_position_alerts_pos_dismissed",
        "position_alerts",
        ["position_id", "dismissed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_position_alerts_pos_dismissed",
        table_name="position_alerts",
    )
    op.drop_column("position_alerts", "dismissed_at")
    op.drop_column("position_alerts", "payload")
    op.drop_column("position_alerts", "alert_type")
