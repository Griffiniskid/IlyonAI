import pytest

from src.defi.observability import AnalysisMetrics
from src.defi.pipeline.enrich import EnrichmentPipeline
from src.defi.pipeline.scan import MarketScanPipeline
from src.defi.pipeline.synthesize import SynthesisPipeline


def test_analysis_metrics_capture_latency_provider_cache_and_ai_fields():
    metrics = AnalysisMetrics(
        total_latency_ms=24.5,
        stage_latency_ms={"scan": 6.0, "enrich": 10.0, "synthesize": 8.5},
        provider_stats={"defillama": {"calls": 1, "failures": 0, "latency_ms": 6.2}},
        cache_stats={"docs": {"hits": 1, "misses": 0}},
        enrichment_coverage_pct=83.3,
        ai_runtime_ms=310.0,
        ai_cost_usd=0.0042,
        factor_model_version="defi-v2",
        rank_change_reasons=["apr_decay"],
    )

    assert metrics.stage_latency_ms["scan"] == 6.0
    assert metrics.provider_stats["defillama"]["latency_ms"] == 6.2
    assert metrics.rank_change_reasons == ["apr_decay"]


@pytest.mark.asyncio
async def test_pipeline_records_observability_metrics_as_stages_run():
    class DocsStub:
        async def analyze(self, url, docs_url=None):
            return {"available": True, "freshness_hours": 4.0}

    class HistoryStub:
        async def get_pool_history(self, pool_id):
            return [{"apy": 7.2, "tvlUsd": 1000}]

        def summarize_pool_history(self, history):
            return {"available": True, "observations": len(history), "freshness_hours": 1.0}

    metrics = AnalysisMetrics()
    scan = MarketScanPipeline()
    enrich = EnrichmentPipeline(docs=DocsStub(), history=HistoryStub(), provider_timeout_seconds=1)
    synthesize = SynthesisPipeline()

    candidates = scan.normalize_candidates(
        pools=[{"project": "orca-dex", "symbol": "SOL-USDC", "apy": 12.5, "chain": "solana"}],
        yields=[],
        markets=[],
        metrics=metrics,
        provider_stats={"defillama": {"calls": 1, "latency_ms": 6.2}},
    )
    enriched = await enrich.enrich_candidate(candidates[0], metrics=metrics)
    analysis = synthesize.combine(
        identity={
            "id": "opp_1",
            "chain": "solana",
            "kind": "pool",
            "protocol_slug": "orca-dex",
        },
        market={"apy": enriched["apy"], "market_regime": "balanced"},
        deterministic={
            "final_score": 71,
            "safety_score": 71,
            "apr_quality_score": 71,
            "exit_quality_score": 71,
            "resilience_score": 71,
            "confidence_score": 80,
            "hard_caps": [],
            "rank_change_reasons": ["docs_strengthened"],
        },
        ai={"judgment_score": 74, "runtime_ms": 310.0, "cost_usd": 0.0042},
        metrics=metrics,
    )

    assert analysis.observability.factor_model_version == "defi-v2"
    assert metrics.stage_latency_ms["scan"] >= 0
    assert metrics.stage_latency_ms["enrich"] >= 0
    assert metrics.stage_latency_ms["synthesize"] >= 0
    assert metrics.provider_stats["defillama"]["calls"] == 1
    assert metrics.cache_stats["docs"]["misses"] == 1
    assert metrics.enrichment_coverage_pct == 100.0
    assert metrics.ai_runtime_ms == 310.0
    assert metrics.ai_cost_usd == 0.0042
    assert metrics.rank_change_reasons == ["docs_strengthened"]
