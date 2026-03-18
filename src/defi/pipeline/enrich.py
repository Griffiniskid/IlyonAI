"""Pass 2 selective enrichment for shortlisted DeFi candidates."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict

from src.data.defillama import DefiLlamaClient
from src.defi.docs_analyzer import ProtocolDocsAnalyzer
from src.defi.evidence import build_evidence_source_metadata
from src.defi.history_store import DefiHistoryStore
from src.defi.pipeline.budgets import get_provider_budget


@dataclass(slots=True)
class EnrichmentLoad:
    payload: Dict[str, Any]
    meta: Dict[str, Any]


class EnrichmentPipeline:
    def __init__(
        self,
        *,
        docs: ProtocolDocsAnalyzer | Any | None = None,
        history: DefiHistoryStore | Any | None = None,
        provider_timeout_seconds: float | None = None,
    ):
        budget = get_provider_budget("defi")
        self.provider_timeout_seconds = budget.timeout_seconds if provider_timeout_seconds is None else provider_timeout_seconds
        self.docs = docs or ProtocolDocsAnalyzer()
        self.history = history or DefiHistoryStore(DefiLlamaClient())

    async def enrich_candidate(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        docs = await self._load_with_budget(
            "docs",
            lambda: self.docs.analyze(candidate.get("protocol_url"), candidate.get("docs_url")),
            lambda: self.docs.fallback_profile("Protocol docs timed out"),
        )
        history = await self._load_with_budget(
            "history",
            lambda: self._load_history_summary(candidate),
            lambda: self.history.fallback_summary("Pool history timed out"),
        )
        return {
            **candidate,
            "docs_profile": docs.payload,
            "history_summary": history.payload,
            "evidence_sources": {"docs": docs.meta, "history": history.meta},
        }

    async def _load_history_summary(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        pool_id = candidate.get("pool_id") or candidate.get("id") or ""
        history = await self.history.get_pool_history(pool_id)
        return self.history.summarize_pool_history(history)

    async def _load_with_budget(
        self,
        label: str,
        loader: Callable[[], Awaitable[Dict[str, Any]]],
        fallback: Callable[[], Dict[str, Any]],
    ) -> EnrichmentLoad:
        if self.provider_timeout_seconds <= 0:
            payload = fallback()
            return EnrichmentLoad(payload=payload, meta=build_evidence_source_metadata("fallback", payload, fallback_used=True))

        try:
            payload = await asyncio.wait_for(loader(), timeout=self.provider_timeout_seconds)
        except TimeoutError:
            payload = fallback()
            return EnrichmentLoad(payload=payload, meta=build_evidence_source_metadata("fallback", payload, fallback_used=True))
        except Exception:
            payload = fallback()
            return EnrichmentLoad(payload=payload, meta=build_evidence_source_metadata("fallback", payload, fallback_used=True))

        return EnrichmentLoad(payload=payload, meta=build_evidence_source_metadata("provider", payload))
