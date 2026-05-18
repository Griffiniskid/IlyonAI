"""intent_state: V7-075 Unified State Store keyed by intent_id.

Revision ID: agent_013
Revises: agent_012
Create Date: 2026-05-18

Spec ref: IlyonAi_Development_Plan_v2.md V7-075 (§1 invariant).

The runtime persisted execution-plan state across half a dozen tables
(agent_plans, position_snapshots, biconomy_authorizations, ...) keyed
by plan_id / position_id / authorization_id. The §1 invariant says
"every materialised intent has one and only one canonical row whose
status the state-machine reads/writes through a single helper". This
migration creates that canonical row: `intent_state`, keyed by
intent_id, carrying status + current_step + payload + updated_at.

Schema:

    intent_id    TEXT  PRIMARY KEY      -- the canonical key the
                                          state-machine plumbs through
    status       TEXT  NOT NULL          -- e.g. DRAFTING, READY_TO_SIGN,
                                          SIGNING_IN_PROGRESS, ...
    current_step INTEGER NOT NULL DEFAULT 0
    payload      JSONB / JSON            -- structured intent payload
                                          (plan snapshot, recovery hooks,
                                          mirror-check results, etc.)
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()

`payload` is JSONB on PostgreSQL and JSON (TEXT-backed) on SQLite via
the same `_jsonb_or_text()` helper used by agent_012.

Down-revision chain after this migration:
    agent_013 -> agent_012 (V7-023, position_alerts) -> agent_011 ->
    agent_010 -> ... -> 001.

The Python-side accessor lives at `src/storage/state_store.py`:
    * upsert_intent_state(session, intent_id, status, current_step, payload)
    * get_intent_state(session, intent_id) -> Optional[dict]
"""
from alembic import op
import sqlalchemy as sa


revision = "agent_013"
down_revision = "agent_012"
branch_labels = None
depends_on = None


def _jsonb_or_text() -> sa.types.TypeEngine:
    """Return JSONB on PostgreSQL, JSON elsewhere (mirrors agent_012)."""
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
    op.create_table(
        "intent_state",
        sa.Column("intent_id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "current_step",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("payload", _jsonb_or_text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    # Status-bucketed lookups for the state-machine's "in-flight intents"
    # scan (READY_TO_SIGN / SIGNING_IN_PROGRESS / BROADCASTED).
    op.create_index(
        "ix_intent_state_status",
        "intent_state",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_intent_state_status", table_name="intent_state")
    op.drop_table("intent_state")
