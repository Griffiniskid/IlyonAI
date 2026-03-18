"""Cache-backed storage for DeFi analysis state."""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.config import settings
from src.storage.cache import CacheManager, get_cache


class AnalysisStore:
    def __init__(self, cache: Optional[CacheManager] = None):
        self.cache = cache or get_cache()
        self.ttl = settings.defi_analysis_ttl_seconds

    async def save_status(self, analysis_id: str, payload: Dict[str, Any]) -> None:
        await self.cache.set(f"defi:analysis:{analysis_id}", payload, ttl=self.ttl)

    async def get_status(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        return await self.cache.get(f"defi:analysis:{analysis_id}")

    async def save_opportunity_document(self, opportunity_id: str, payload: Dict[str, Any]) -> None:
        await self.cache.set(f"defi:opportunity:{opportunity_id}", payload, ttl=self.ttl)

    async def get_opportunity_document(self, opportunity_id: str) -> Optional[Dict[str, Any]]:
        return await self.cache.get(f"defi:opportunity:{opportunity_id}")
