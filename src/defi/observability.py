"""Observability helpers for DeFi analysis pipelines."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Iterator


@dataclass(slots=True)
class AnalysisMetrics:
    total_latency_ms: float | None = None
    stage_latency_ms: dict[str, float] = field(default_factory=dict)
    provider_stats: dict[str, dict[str, float | int]] = field(default_factory=dict)
    cache_stats: dict[str, dict[str, int]] = field(default_factory=dict)
    enrichment_coverage_pct: float | None = None
    ai_runtime_ms: float | None = None
    ai_cost_usd: float | None = None
    factor_model_version: str | None = None
    rank_change_reasons: list[str] = field(default_factory=list)

    @contextmanager
    def track_stage(self, stage: str) -> Iterator[None]:
        started = perf_counter()
        try:
            yield
        finally:
            self.stage_latency_ms[stage] = round((perf_counter() - started) * 1000, 3)

    def finalize_total_latency(self) -> None:
        self.total_latency_ms = round(sum(self.stage_latency_ms.values()), 3)

    def record_provider(self, name: str, *, calls: int = 0, failures: int = 0, latency_ms: float | None = None) -> None:
        stats = self.provider_stats.setdefault(name, {"calls": 0, "failures": 0, "latency_ms": 0.0})
        stats["calls"] = int(stats["calls"]) + int(calls)
        stats["failures"] = int(stats["failures"]) + int(failures)
        if latency_ms is not None:
            stats["latency_ms"] = round(float(stats.get("latency_ms", 0.0)) + float(latency_ms), 3)

    def record_cache_hit(self, name: str) -> None:
        stats = self.cache_stats.setdefault(name, {"hits": 0, "misses": 0})
        stats["hits"] += 1

    def record_cache_miss(self, name: str) -> None:
        stats = self.cache_stats.setdefault(name, {"hits": 0, "misses": 0})
        stats["misses"] += 1

    def set_enrichment_coverage(self, completed: int, total: int) -> None:
        self.enrichment_coverage_pct = 0.0 if total <= 0 else round((completed / total) * 100, 1)

    def record_ai_usage(self, *, runtime_ms: float | None = None, cost_usd: float | None = None) -> None:
        if runtime_ms is not None:
            self.ai_runtime_ms = float(runtime_ms)
        if cost_usd is not None:
            self.ai_cost_usd = float(cost_usd)

    def set_rank_change_reasons(self, reasons: list[str] | None) -> None:
        self.rank_change_reasons = list(reasons or [])

    def to_payload(self) -> dict[str, Any]:
        self.finalize_total_latency()
        return {
            "total_latency_ms": self.total_latency_ms,
            "stage_latency_ms": dict(self.stage_latency_ms),
            "provider_stats": dict(self.provider_stats),
            "cache_stats": dict(self.cache_stats),
            "enrichment_coverage_pct": self.enrichment_coverage_pct,
            "ai_runtime_ms": self.ai_runtime_ms,
            "ai_cost_usd": self.ai_cost_usd,
            "factor_model_version": self.factor_model_version,
            "rank_change_reasons": list(self.rank_change_reasons),
        }
