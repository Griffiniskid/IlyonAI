"""Pass 2 selective enrichment for shortlisted DeFi candidates."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Awaitable, Callable, Dict

from src.data.defillama import DefiLlamaClient
from src.defi.docs_analyzer import ProtocolDocsAnalyzer
from src.defi.evidence import build_evidence_source_metadata
from src.defi.history_store import DefiHistoryStore
from src.defi.observability import AnalysisMetrics
from src.defi.pipeline.budgets import get_provider_budget

logger = logging.getLogger(__name__)


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

    async def enrich_candidate(self, candidate: Dict[str, Any], metrics: AnalysisMetrics | None = None) -> Dict[str, Any]:
        started = perf_counter()
        docs, history = await asyncio.gather(
            self._load_with_budget(
                "docs",
                lambda: self.docs.analyze(candidate.get("protocol_url"), candidate.get("docs_url")),
                lambda: self.docs.fallback_profile("Protocol docs timed out"),
                metrics=metrics,
            ),
            self._load_with_budget(
                "history",
                lambda: self._load_history_summary(candidate),
                lambda: self.history.fallback_summary("Pool history timed out"),
                metrics=metrics,
            ),
        )
        if metrics is not None:
            metrics.stage_latency_ms["enrich"] = round((perf_counter() - started) * 1000, 3)
            available = int(bool(docs.payload.get("available"))) + int(bool(history.payload.get("available")))
            metrics.set_enrichment_coverage(available, 2)
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
        metrics: AnalysisMetrics | None = None,
    ) -> EnrichmentLoad:
        if self.provider_timeout_seconds <= 0:
            payload = fallback()
            return EnrichmentLoad(payload=payload, meta=build_evidence_source_metadata("fallback", payload, fallback_used=True))

        started = perf_counter()
        try:
            payload = await asyncio.wait_for(loader(), timeout=self.provider_timeout_seconds)
        except TimeoutError:
            logger.warning("%s enrichment timed out after %ss", label, self.provider_timeout_seconds)
            payload = fallback()
            if metrics is not None:
                metrics.record_provider(label, calls=1, failures=1, latency_ms=(perf_counter() - started) * 1000)
                metrics.record_cache_miss(label)
            return EnrichmentLoad(payload=payload, meta=build_evidence_source_metadata("fallback", payload, fallback_used=True))
        except Exception:
            logger.exception("%s enrichment failed", label)
            if metrics is not None:
                metrics.record_provider(label, calls=1, failures=1, latency_ms=(perf_counter() - started) * 1000)
            raise

        if metrics is not None:
            metrics.record_provider(label, calls=1, latency_ms=(perf_counter() - started) * 1000)
            if label == "docs":
                metrics.record_cache_miss(label)
        return EnrichmentLoad(payload=payload, meta=build_evidence_source_metadata("provider", payload))
