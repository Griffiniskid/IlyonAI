"""Cache-backed storage for DeFi analysis state."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from src.config import settings
from src.defi.observability import AnalysisMetrics
from src.storage.cache import CacheManager, get_cache


class AnalysisStore:
    def __init__(self, cache: Optional[CacheManager] = None):
        self.cache = cache or get_cache()
        self.ttl = settings.defi_analysis_ttl_seconds

    async def save_status(self, analysis_id: str, payload: Dict[str, Any]) -> None:
        await self.cache.set(f"defi:analysis:{analysis_id}", self._normalize_payload(payload), ttl=self.ttl)

    async def get_status(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        return await self.cache.get(f"defi:analysis:{analysis_id}")

    def new_id(self) -> str:
        return f"ana_{uuid.uuid4().hex[:12]}"

    async def save_request_analysis(self, request_key: str, analysis_id: str) -> None:
        await self.cache.set(f"defi:analysis-request:{request_key}", analysis_id, ttl=self.ttl)

    async def get_request_analysis(self, request_key: str) -> Optional[str]:
        return await self.cache.get(f"defi:analysis-request:{request_key}")

    async def save_opportunity_document(self, opportunity_id: str, payload: Dict[str, Any]) -> None:
        await self.cache.set(f"defi:opportunity:{opportunity_id}", self._normalize_payload(payload), ttl=self.ttl)

    async def get_opportunity_document(self, opportunity_id: str) -> Optional[Dict[str, Any]]:
        return await self.cache.get(f"defi:opportunity:{opportunity_id}")

    def _normalize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(payload)
        observability = normalized.get("observability")
        if isinstance(observability, AnalysisMetrics):
            normalized["observability"] = observability.to_payload()
        return normalized
