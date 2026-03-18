import pytest

from src.defi.contracts import AnalysisStatus
from src.defi.intelligence_engine import DefiIntelligenceEngine
from src.defi.opportunity_engine import DefiOpportunityEngine


class ScanStub:
    def __init__(self, provisional=None):
        self.provisional = provisional or [{"id": "opp_1"}]

    def build_request_key(self, filters):
        return f"{filters.get('chain')}:{filters.get('limit')}"

    async def run(self, **filters):
        return [{**item, "filters": filters} for item in self.provisional]


class StoreStub:
    def __init__(self):
        self.statuses = {}
        self.request_index = {}
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
