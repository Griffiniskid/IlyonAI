"""Async repositories for V7 spec tables.

Repository helpers wrap raw SQLAlchemy session calls with typed,
dialect-portable insert/query/dismiss primitives. They never own a
session — callers pass one in (`async with db.async_session() as s:`)
so a single business operation can compose multiple repo calls in one
transaction.
"""

from src.storage.repositories.position_alert import (
    dismiss_alert,
    get_open_alerts,
    insert_alert,
)

__all__ = ["dismiss_alert", "get_open_alerts", "insert_alert"]
