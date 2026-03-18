"""Cache-backed storage for protocol docs and pool history evidence."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.config import settings
from src.storage.cache import CacheManager, get_cache


class EvidenceStore:
    def __init__(self, cache: Optional[CacheManager] = None):
        self.cache = cache or get_cache()
        self.ttl = settings.defi_analysis_ttl_seconds

    async def get_protocol_docs(self, target: str) -> Optional[Dict[str, Any]]:
        return await self.cache.get(self._docs_key(target))

    async def save_protocol_docs(self, target: str, payload: Dict[str, Any]) -> None:
        await self.cache.set(self._docs_key(target), payload, ttl=self.ttl)

    async def get_pool_history(self, pool_id: str) -> Optional[List[Dict[str, Any]]]:
        return await self.cache.get(self._history_key(pool_id))

    async def save_pool_history(self, pool_id: str, payload: List[Dict[str, Any]]) -> None:
        await self.cache.set(self._history_key(pool_id), payload, ttl=self.ttl)

    def _docs_key(self, target: str) -> str:
        return f"defi:evidence:docs:{target}"

    def _history_key(self, pool_id: str) -> str:
        return f"defi:evidence:history:{pool_id}"
