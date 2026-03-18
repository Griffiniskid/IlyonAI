import pytest

from src.defi.contracts import AnalysisStatus
from src.defi.intelligence_engine import DefiIntelligenceEngine
from src.defi.opportunity_engine import DefiOpportunityEngine


class ScanStub:
    def __init__(self, provisional=None):
        self.provisional = provisional or [{"id": "opp_1"}]
        self.metrics_seen = None

    def build_request_key(self, filters):
        return f"{filters.get('chain')}:{filters.get('limit')}"

    async def run(self, **filters):
        self.metrics_seen = filters.get("metrics")
        return [{**item, "filters": filters} for item in self.provisional]


class StoreStub:
    def __init__(self):
        self.statuses = {}
        self.request_index = {}
        self.opportunity_documents = {}
        self.counter = 0

    def new_id(self):
        self.counter += 1
        return f"ana_{self.counter}"

    async def save_status(self, analysis_id, payload):
        self.statuses[analysis_id] = payload

    async def get_status(self, analysis_id):
        return self.statuses.get(analysis_id)

    async def save_request_analysis(self, request_key, analysis_id):
        self.request_index[request_key] = analysis_id

    async def get_request_analysis(self, request_key):
        return self.request_index.get(request_key)

    async def save_opportunity_document(self, opportunity_id, payload):
        self.opportunity_documents[opportunity_id] = payload

    async def get_opportunity_document(self, opportunity_id):
        return self.opportunity_documents.get(opportunity_id)


def _make_intelligence_engine(scan_pipeline=None, store=None):
    engine = DefiIntelligenceEngine()
    setattr(engine.engine, "scan_pipeline", scan_pipeline or ScanStub())
    setattr(engine.engine, "analysis_store", store or StoreStub())
    return engine


@pytest.mark.asyncio
async def test_intelligence_engine_returns_async_analysis_status():
    engine = _make_intelligence_engine()

    async def fake_build_market_analysis(**_filters):
        return {"top_opportunities": []}

    setattr(engine.engine, "_build_market_analysis", fake_build_market_analysis)

    first = await engine.start_opportunity_analysis(chain="solana", limit=5)
    second = await engine.start_opportunity_analysis(chain="solana", limit=5)

    assert first.status in {"queued", "running", "completed"}
    assert first.analysis_id.startswith("ana_")
    assert first.error is None
    assert first.observability is not None
    assert first.observability.factor_model_version == "defi-v2"
    assert second.analysis_id == first.analysis_id

    task = engine.engine._analysis_tasks.get(first.analysis_id)
    if task is not None:
        await task


@pytest.mark.asyncio
async def test_opportunity_engine_analyze_market_delegates_to_async_pipeline():
    engine = object.__new__(DefiOpportunityEngine)
    calls = {}

    async def fake_start_opportunity_analysis(**filters):
        calls["filters"] = filters
        return AnalysisStatus(
            analysis_id="ana_test",
            status="running",
            score_model_version="defi-v2",
            provisional_shortlist=[{"id": "opp_1"}],
        )

    async def fake_get_completed_or_provisional_result(analysis_id):
        calls["analysis_id"] = analysis_id
        return {"analysis_id": analysis_id, "top_opportunities": []}

    setattr(engine, "start_opportunity_analysis", fake_start_opportunity_analysis)
    setattr(engine, "get_completed_or_provisional_result", fake_get_completed_or_provisional_result)

    result = await DefiOpportunityEngine.analyze_market(
        engine,
        chain="solana",
        query="jito",
        min_tvl=250_000,
        min_apy=4.0,
        limit=5,
        include_ai=False,
        ranking_profile="balanced",
    )

    assert calls["filters"] == {
        "chain": "solana",
        "query": "jito",
        "min_tvl": 250_000,
        "min_apy": 4.0,
        "limit": 5,
        "include_ai": False,
        "ranking_profile": "balanced",
    }
    assert calls["analysis_id"] == "ana_test"
    assert result == {"analysis_id": "ana_test", "top_opportunities": []}


@pytest.mark.asyncio
async def test_start_opportunity_analysis_restarts_orphaned_running_analysis():
    store = StoreStub()
    store.request_index["solana:5"] = "ana_orphaned"
    store.statuses["ana_orphaned"] = {
        "status": "running",
        "score_model_version": "defi-v2",
        "provisional_shortlist": [{"id": "stale_opp"}],
    }
    engine = _make_intelligence_engine(store=store)

    async def fake_build_market_analysis(**_filters):
        return {"top_opportunities": []}

    setattr(engine.engine, "_build_market_analysis", fake_build_market_analysis)

    status = await engine.start_opportunity_analysis(chain="solana", limit=5)

    assert status.analysis_id != "ana_orphaned"
    assert store.request_index["solana:5"] == status.analysis_id

    task = engine.engine._analysis_tasks.get(status.analysis_id)
    if task is not None:
        await task


@pytest.mark.asyncio
async def test_get_completed_or_provisional_result_returns_failed_envelope():
    engine = _make_intelligence_engine()

    async def fake_build_market_analysis(**_filters):
        raise RuntimeError("scan exploded")

    setattr(engine.engine, "_build_market_analysis", fake_build_market_analysis)

    status = await engine.start_opportunity_analysis(chain="solana", limit=5)
    result = await engine.get_completed_or_provisional_result(status.analysis_id)

    assert result["analysis_id"] == status.analysis_id
    assert result["status"] == "failed"
    assert result["error"] == "scan exploded"
    assert result["provisional_shortlist"]


@pytest.mark.asyncio
async def test_analyze_market_returns_failed_envelope_when_background_analysis_fails():
    engine = _make_intelligence_engine()

    async def fake_build_market_analysis(**_filters):
        raise RuntimeError("market synthesis failed")

    setattr(engine.engine, "_build_market_analysis", fake_build_market_analysis)

    result = await engine.analyze_market(chain="solana", limit=5)

    assert result["status"] == "failed"
    assert result["error"] == "market synthesis failed"


@pytest.mark.asyncio
async def test_analyze_market_threads_observability_through_real_async_entrypoint():
    scan = ScanStub()
    engine = _make_intelligence_engine(scan_pipeline=scan)

    async def fake_build_market_analysis(**filters):
        metrics = filters["metrics"]
        metrics.stage_latency_ms["synthesize"] = 12.5
        metrics.factor_model_version = "defi-v2"
        metrics.rank_change_reasons = ["market_repricing"]
        metrics.finalize_total_latency()
        return {
            "top_opportunities": [],
            "observability": metrics.to_payload(),
        }

    setattr(engine.engine, "_build_market_analysis", fake_build_market_analysis)

    result = await engine.analyze_market(chain="solana", limit=5)

    assert scan.metrics_seen is not None
    assert result["observability"]["factor_model_version"] == "defi-v2"
    assert result["observability"]["stage_latency_ms"]["synthesize"] >= 0
    assert result["observability"]["rank_change_reasons"]


@pytest.mark.asyncio
async def test_completed_analysis_records_enrichment_synthesis_and_cache_metrics():
    scan = ScanStub(provisional=[{"id": "opp_1", "project": "jito", "protocol": "jito", "chain": "solana", "apy": 8.2, "tvlUsd": 2500000, "candidate_kind": "yield"}])
    store = StoreStub()
    engine = _make_intelligence_engine(scan_pipeline=scan, store=store)

    class EnrichmentStub:
        def __init__(self):
            self.calls = 0

        async def enrich_candidate(self, candidate, metrics=None):
            self.calls += 1
            assert metrics is not None
            metrics.stage_latency_ms["enrich"] = 5.0
            return {
                **candidate,
                "docs_profile": {"available": True, "freshness_hours": 1.0},
                "history_summary": {"available": True, "observations": 2, "freshness_hours": 2.0},
                "evidence_sources": {},
            }

    class SynthesisStub:
        def __init__(self):
            self.calls = 0

        def combine(self, **kwargs):
            self.calls += 1
            metrics = kwargs["metrics"]
            metrics.stage_latency_ms["synthesize"] = 7.0
            metrics.factor_model_version = "defi-v2"
            metrics.rank_change_reasons = ["cache_miss"]

            class AnalysisDoc:
                def model_dump(self, mode="json"):
                    return {
                        "identity": {"id": "opp_1", "chain": "solana", "kind": "yield", "protocol_slug": "jito"},
                        "market": {"apy": 8.2, "market_regime": "unknown"},
                        "scores": {
                            "deterministic_score": 55,
                            "ai_judgment_score": 55,
                            "final_deployability_score": 55,
                            "safety_score": 55,
                            "apr_quality_score": 55,
                            "exit_quality_score": 55,
                            "resilience_score": 55,
                            "confidence_score": 55,
                        },
                        "factors": [],
                        "behavior": {},
                        "scenarios": [],
                        "recommendation": {"action": "watch", "rationale": []},
                        "evidence": [],
                        "observability": metrics.to_payload(),
                    }

            return AnalysisDoc()

    async def fake_build_market_analysis(**filters):
        return {"top_opportunities": [], "observability": filters["metrics"].to_payload()}

    async def fake_ai_analysis(_payload):
        return {"judgment_score": 61}

    enrichment_pipeline = EnrichmentStub()
    synthesis_pipeline = SynthesisStub()
    setattr(engine.engine, "enrichment_pipeline", enrichment_pipeline)
    setattr(engine.engine, "synthesis_pipeline", synthesis_pipeline)
    setattr(engine.engine, "_build_market_analysis", fake_build_market_analysis)
    setattr(engine.engine.ai, "build_opportunity_analysis", fake_ai_analysis)

    first = await engine.analyze_market(chain="solana", limit=5)
    second = await engine.analyze_market(chain="base", limit=5)

    assert first["observability"]["stage_latency_ms"]["enrich"] == 5.0
    assert first["observability"]["stage_latency_ms"]["synthesize"] == 7.0
    assert first["observability"]["cache_stats"]["opportunity_documents"]["misses"] == 1
    assert second["observability"]["cache_stats"]["opportunity_documents"]["hits"] == 1
    assert enrichment_pipeline.calls == 1
    assert synthesis_pipeline.calls == 1
