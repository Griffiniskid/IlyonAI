from __future__ import annotations

from typing import Any


class DeadLetterQueue:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def write(self, item: dict[str, Any]) -> dict[str, Any]:
        self.items.append(item)
        return item
