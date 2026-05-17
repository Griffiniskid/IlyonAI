"""SQLAlchemy model for `position_alerts` (V7-023).

The physical table was first created by Phase 4.2 (agent_006) with
columns `alert_id / alert_kind / payload_json / acknowledged_at`.
V7-023 (agent_012) adds the spec-canonical columns `alert_type /
payload / dismissed_at` and the covering index
`(position_id, dismissed_at)`.

This ORM class exposes the spec column names as the canonical Python
attributes. The legacy `alert_id` column remains the primary key
(renaming a PK in an additive migration is unsafe), but it is aliased
to the attribute name `id` so callers see the spec-clean surface:

    alert = PositionAlert(position_id="...", alert_type="out_of_range",
                          payload={"side": "upper"})
    session.add(alert)
    await session.flush()
    alert.id            # autoincrement PK
    alert.fired_at      # server-default CURRENT_TIMESTAMP
    alert.dismissed_at  # None until dismiss_alert() fires

The repo layer (`src.storage.repositories.position_alert`) uses raw
`sa.text()` inserts/selects for portability across PG (JSONB) and
SQLite (TEXT JSON) so the model is primarily for ORM consumers and
typed reads.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import BigInteger, Column, DateTime, Index, JSON, Text, func
from sqlalchemy.orm import declarative_base


Base = declarative_base()


class PositionAlert(Base):
    """A PositionHealth alert emitted by a §4 detector.

    Detector kinds (canonical, written to `alert_type`):
      - out_of_range         (CL position drifted outside tick window)
      - fee_apr_drop         (realised fee APR fell >50% vs prior 7d)
      - tvl_exodus           (pool TVL fell >30% in 24h)
      - gas_favorable        (EVM gas <30 gwei, rebalance window open)
    """

    __tablename__ = "position_alerts"

    # Legacy PK column from agent_006; aliased so Python sees `id`.
    id = Column("alert_id", BigInteger, primary_key=True, autoincrement=True)
    position_id = Column(Text, nullable=False, index=True)
    # Spec-canonical alert kind column (V7-023 / agent_012). The older
    # `alert_kind` column from agent_006 remains in the physical table
    # for backwards compat but is not mapped here.
    alert_type = Column(Text, nullable=True)
    fired_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )
    # JSONB on PostgreSQL, JSON/TEXT on SQLite. SQLAlchemy's generic
    # JSON type round-trips dicts via the dialect's serializer.
    payload = Column(JSON, nullable=True)
    dismissed_at = Column(DateTime(timezone=True), nullable=True)

    # Covering index for `get_open_alerts(position_id)` — mirrors the
    # index `ix_position_alerts_pos_dismissed` created in agent_012.
    __table_args__ = (
        Index(
            "ix_position_alerts_pos_dismissed",
            "position_id",
            "dismissed_at",
        ),
    )

    def to_dict(self) -> dict[str, Any]:
        """Render as the dict shape `get_open_alerts` returns."""
        return {
            "id": self.id,
            "position_id": self.position_id,
            "alert_type": self.alert_type,
            "fired_at": self.fired_at,
            "payload": self.payload,
            "dismissed_at": self.dismissed_at,
        }

    @classmethod
    def from_row(cls, row: Any) -> "PositionAlert":
        """Build from a `Result.mappings()` row.

        Used by the repo's raw-SQL `get_open_alerts` path so callers
        can choose between dict and ORM views.
        """
        inst = cls()
        inst.id = row["id"] if "id" in row else row.get("alert_id")
        inst.position_id = row["position_id"]
        inst.alert_type = row.get("alert_type")
        inst.fired_at = row.get("fired_at")
        inst.payload = row.get("payload")
        inst.dismissed_at = row.get("dismissed_at")
        return inst
