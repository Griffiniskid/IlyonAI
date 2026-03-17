"""Cache-backed storage for DeFi analysis state."""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.storage.cache import CacheManager


class AnalysisStore:
    def __init__(self, cache: Optional[CacheManager] = None):
        self.cache = cache or CacheManager()

    async def save_status(self, analysis_id: str, payload: Dict[str, Any]) -> None:
        await self.cache.set(f"defi:analysis:{analysis_id}", payload)

    async def get_status(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        return await self.cache.get(f"defi:analysis:{analysis_id}")

    async def save_opportunity_document(self, opportunity_id: str, payload: Dict[str, Any]) -> None:
        await self.cache.set(f"defi:opportunity:{opportunity_id}", payload)

    async def get_opportunity_document(self, opportunity_id: str) -> Optional[Dict[str, Any]]:
        return await self.cache.get(f"defi:opportunity:{opportunity_id}")
