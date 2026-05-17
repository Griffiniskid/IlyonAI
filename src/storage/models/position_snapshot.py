"""V7-022 — `position_snapshots` ORM surface (spec contract only).

The physical table was first created by agent_006 with columns
`snapshot_id` BIGINT PK + legacy `health_json` TEXT. V7-022's
agent_011 migration added the spec-canonical `payload` JSON column +
DESC index `(position_id, snapshot_at DESC)` without disturbing the
legacy column. This model exposes ONLY the V7-022 spec contract:

  - id (alias of physical `snapshot_id`)
  - position_id
  - snapshot_at
  - payload

Legacy `health_json` rows continue to be written by older Notifier
code paths; new writers populate `payload`. Consumers that need both
can query the table directly via raw SQL.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Text
from sqlalchemy.sql import func

try:
    from sqlalchemy.orm import declarative_base
except ImportError:  # pragma: no cover - sqlalchemy <1.4 fallback
    from sqlalchemy.ext.declarative import declarative_base  # type: ignore

try:
    from sqlalchemy import JSON
except ImportError:  # pragma: no cover
    from sqlalchemy.types import JSON  # type: ignore


Base = declarative_base()


class PositionSnapshot(Base):
    """V7-022 spec contract row in `position_snapshots`."""

    __tablename__ = "position_snapshots"
    __table_args__ = {"extend_existing": True}

    id = Column("snapshot_id", BigInteger, primary_key=True, autoincrement=True)
    position_id = Column(Text, nullable=False, index=True)
    snapshot_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    payload = Column(JSON, nullable=True)
