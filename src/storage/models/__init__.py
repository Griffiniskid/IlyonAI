"""SQLAlchemy ORM models for V7 spec tables.

This package holds the canonical, spec-aligned model classes introduced
by the V7 wave. Older models continue to live in `src.storage.database`
for backwards compatibility; new tables (V7-022 position_snapshots,
V7-023 position_alerts) define their classes here.
"""

from src.storage.models.position_alert import PositionAlert

__all__ = ["PositionAlert"]
