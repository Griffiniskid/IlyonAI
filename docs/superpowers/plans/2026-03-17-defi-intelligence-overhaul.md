# DeFi Intelligence Overhaul Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a sub-30-second multi-chain DeFi opportunity-analysis system with async analysis resources, richer risk-to-APR scoring, first-layer behavioral signals, and new `/defi` discover/investigate/compare flows.

**Architecture:** Keep `DefiOpportunityEngine` as the compatibility facade, but move the real work into a three-pass pipeline: scan the market cheaply, enrich only the top candidate band, then synthesize deterministic scoring, AI judgment, and recommendation output into one `OpportunityAnalysis` contract. Persist analysis state and evidence through small dedicated stores, expose the pipeline through async opportunity-analysis routes, and let the Next.js app poll provisional-to-final results instead of blocking on the full analysis.

**Tech Stack:** Python 3.13, aiohttp, Pydantic, Redis-backed cache abstractions, DefiLlama adapters, Next.js 14, React Query, TypeScript, Vitest, React Testing Library

---

## Scope Guardrails

- This plan is intentionally bounded to the approved spec: all of Phase 1, the minimum Phase 2 scoring slice for LP, farm, lending-supply, and vault-like opportunities, and the minimum Phase 3 behavior-signal interfaces.
- Do **not** build the full entity graph, standalone `/entities/{wallet_or_cluster}` endpoints, borrow/loop scoring, or watchlist/monitoring features in this plan.
- Preserve the current DeFi routes while introducing the new opportunity-analysis resources; compatibility cleanup can happen later.
- Current worktree baseline note: `python -m pytest` fails during collection because `src/monetization/__init__.py` imports symbols that no longer exist in `src/monetization/affiliates.py`. Fix that first so TDD starts from a stable baseline.

## Execution Rules

- Use `@superpowers/using-git-worktrees` before code changes if you are not already in the dedicated worktree.
- Use `@superpowers/test-driven-development` for every task below.
- Use `@superpowers/verification-before-completion` before every commit and before claiming a task is complete.
- Keep commits small: one task per commit unless a task explicitly calls for two commits.
- Stay DRY and YAGNI: no standalone protocol pages, no `/entities` route, no portfolio features, and no extra scoring families beyond LP, farm, lending-supply, and vault-like.

## File Structure Lock-In

### Core backend files

- Create: `src/defi/contracts.py` - canonical `OpportunityAnalysis`, `AnalysisStatus`, `Recommendation`, factor tree, and progress models.
- Create: `src/defi/pipeline/scan.py` - Pass 1 market scan and candidate normalization.
- Create: `src/defi/pipeline/enrich.py` - Pass 2 selective enrichment with time budgets.
- Create: `src/defi/pipeline/synthesize.py` - Pass 3 deterministic + AI + recommendation synthesis.
- Create: `src/defi/pipeline/budgets.py` - provider budgets, concurrency limits, and timeout helpers.
- Create: `src/defi/pipeline/coalescing.py` - request deduplication and in-flight analysis sharing.
- Create: `src/defi/observability.py` - latency, provider, cache, AI-cost, and rank-change instrumentation helpers.
- Create: `src/defi/assemblers/opportunity_analysis.py` - maps scores/evidence/scenarios into the stable contract.
- Modify: `src/defi/opportunity_engine.py` - become a thin facade over the new pipeline.
- Modify: `src/defi/intelligence_engine.py` - expose async analysis lifecycle methods used by routes.
- Modify: `src/defi/opportunity_taxonomy.py` - make archetype routing explicit for LP, farm, lending-supply, and vault-like opportunities.
- Modify: `src/defi/pool_analyzer.py` - emit normalized scan candidates instead of partially final records.
- Modify: `src/defi/farm_analyzer.py` - emit normalized scan candidates instead of partially final records.
- Modify: `src/defi/lending_analyzer.py` - emit normalized lending-supply candidates; keep borrow/loop deferred.

### Scoring files

- Create: `src/defi/scoring/deterministic.py` - orchestrates shared factor calculators and archetype scorers.
- Create: `src/defi/scoring/ai_judgment.py` - constrained AI judgment score and evidence gating.
- Create: `src/defi/scoring/final_ranker.py` - combines deterministic score, AI score, hard caps, and recommendation rules.
- Create: `src/defi/scoring/factors/protocol_integrity.py`
- Create: `src/defi/scoring/factors/market_structure.py`
- Create: `src/defi/scoring/factors/apr_quality.py`
- Create: `src/defi/scoring/factors/position_risk.py`
- Create: `src/defi/scoring/factors/exit_quality.py`
- Create: `src/defi/scoring/factors/behavior.py`
- Create: `src/defi/scoring/factors/chain_risk.py`
- Create: `src/defi/scoring/factors/confidence.py`
- Create: `src/defi/scoring/archetypes/lp.py`
- Create: `src/defi/scoring/archetypes/farm.py`
- Create: `src/defi/scoring/archetypes/lending_supply.py`
- Create: `src/defi/scoring/archetypes/vault.py`
- Modify: `src/defi/risk_engine.py` - keep as a compatibility wrapper or shrink to shared math helpers.

### Stores and evidence files

- Create: `src/defi/stores/analysis_store.py` - analysis status, provisional shortlist, and final result persistence.
- Create: `src/defi/stores/evidence_store.py` - durable docs/history/evidence snapshots.
- Modify: `src/defi/history_store.py` - move to store-backed reads/writes.
- Modify: `src/defi/docs_analyzer.py` - move to store-backed reads/writes.
- Modify: `src/defi/evidence.py` - add freshness/source/fallback markers required by the spec.
- Modify: `src/storage/cache.py` - add any missing generic cache helpers needed by the new stores.
- Modify: `src/config.py` - add budgets, TTLs, score-model version, and async analysis settings.

### Behavioral intelligence files

- Create: `src/analytics/signal_models.py` - first-layer behavior signal dataclasses.
- Create: `src/analytics/behavior_signals.py` - aggregates whale, concentration, stickiness, anomaly, and deployer-link heuristics.
- Modify: `src/analytics/time_series.py` - durable storage + opportunity/protocol series keys.
- Modify: `src/analytics/anomaly_detector.py` - allocator-grade anomaly signals instead of rug-only output.
- Modify: `src/analytics/wallet_forensics.py` - minimal deployer-linked heuristics only; full clustering stays deferred.
- Modify: `src/data/solana.py` - real whale-summary helpers; synthetic trending whales become a fallback only.
- Modify: `src/api/routes/whale.py` - expose summary-first whale output with freshness/fallback markers.

### API files

- Modify: `src/api/middleware/rate_limit.py` - reuse authenticated limiters and stop creating a new limiter per request.
- Modify: `src/api/routes/auth.py` - stop appending auth middleware after app creation.
- Create: `src/api/routes/opportunities.py` - `POST /opportunities/analyses`, `GET /opportunities/analyses/{analysis_id}`, `GET /opportunities/{id}`, `POST /opportunities/compare`.
- Modify: `src/api/app.py` - register the new routes and document them.
- Modify: `src/api/schemas/requests.py` - request models for async analysis creation and compare-by-id/analysis-id.
- Modify: `src/api/schemas/responses.py` - async analysis envelope and stable `OpportunityAnalysis` API schema.

### Frontend files

- Modify: `web/package.json` - add frontend test scripts and dependencies.
- Create: `web/vitest.config.ts` - Vitest configuration.
- Create: `web/tests/setup.ts` - React Testing Library setup.
- Modify: `web/types/index.ts` - frontend `OpportunityAnalysis` types and async envelopes.
- Modify: `web/lib/api.ts` - client functions for create/read/compare opportunity analysis.
- Modify: `web/lib/hooks.ts` - React Query hooks for create-analysis, poll-analysis, read opportunity, compare opportunities.
- Create: `web/app/defi/page.tsx` - Discover flow.
- Create: `web/app/defi/_components/discover-client.tsx` - client-only discover UI and React Query hooks.
- Create: `web/app/defi/[id]/page.tsx` - Investigate flow.
- Create: `web/app/defi/_components/detail-client.tsx` - client-only investigate UI and React Query hooks.
- Create: `web/app/defi/compare/page.tsx` - Compare flow.
- Create: `web/app/defi/_components/compare-client.tsx` - client-only compare UI and React Query hooks.
- Create: `web/app/defi/loading.tsx` - loading state for async analysis.
- Create: `web/app/defi/error.tsx` - error boundary for async analysis.

### Test files

- Create: `tests/test_monetization_compat.py`
- Create: `tests/defi/test_opportunity_analysis_contract.py`
- Create: `tests/defi/test_analysis_store.py`
- Create: `tests/defi/test_pipeline_budgets.py`
- Create: `tests/defi/test_request_coalescing.py`
- Create: `tests/defi/test_pipeline_scan.py`
- Create: `tests/defi/test_pipeline_enrichment.py`
- Create: `tests/defi/test_pipeline_synthesis.py`
- Create: `tests/defi/test_intelligence_engine_async.py`
- Create: `tests/defi/test_provider_normalization.py`
- Create: `tests/defi/test_chain_support_matrix.py`
- Create: `tests/defi/test_scoring_lp.py`
- Create: `tests/defi/test_scoring_farm.py`
- Create: `tests/defi/test_scoring_lending_supply.py`
- Create: `tests/defi/test_scoring_vault.py`
- Create: `tests/defi/test_apr_haircuts.py`
- Create: `tests/defi/test_risk_to_apr_ratio.py`
- Create: `tests/defi/test_decision_bundle.py`
- Create: `tests/defi/test_ranking_invariants.py`
- Create: `tests/defi/test_opportunity_document_index.py`
- Create: `tests/analytics/test_behavior_signal_models.py`
- Create: `tests/analytics/test_behavior_signals.py`
- Create: `tests/analytics/test_time_series_store.py`
- Create: `tests/analytics/test_anomaly_detector_behavior.py`
- Create: `tests/analytics/test_wallet_forensics_entity_heuristics.py`
- Create: `tests/defi/test_observability_metrics.py`
- Create: `tests/defi/test_ai_explanation_golden.py`
- Create: `tests/fixtures/defi/ai_judgment_golden.json`
- Create: `tests/api/test_auth_rate_limit_middleware.py`
- Create: `tests/api/test_opportunity_routes.py`
- Create: `tests/api/test_opportunity_compare_route.py`
- Create: `tests/api/test_opportunity_read_route.py`
- Create: `web/tests/smoke/frontend-harness.test.ts`
- Create: `web/tests/api/opportunities-api.test.ts`
- Create: `web/tests/hooks/useOpportunityAnalysis.test.tsx`
- Create: `web/tests/app/defi-discover.page.test.tsx`
- Create: `web/tests/app/defi-detail.page.test.tsx`
- Create: `web/tests/app/defi-compare.page.test.tsx`

## Task 1: Restore A Green Baseline For TDD

**Files:**
- Create: `tests/test_monetization_compat.py`
- Modify: `src/monetization/__init__.py`
- Test: `tests/test_basic.py`

- [ ] **Step 1: Write the failing test**

```python
import importlib


def test_monetization_package_imports_without_missing_legacy_symbols():
    module = importlib.import_module("src.monetization")
    assert callable(module.get_manager)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_monetization_compat.py -q`
Expected: FAIL with an `ImportError` for `get_affiliate_buttons` or `get_main_keyboard`

- [ ] **Step 3: Write minimal implementation**

```python
from .affiliates import (
    AffiliateManager,
    get_primary_buy_link,
    get_trojan_link,
    get_trojan_ref_link,
    get_manager,
)
```

- [ ] **Step 4: Run focused verification**

Run: `python -m pytest tests/test_monetization_compat.py -q && python -m pytest tests/test_basic.py --collect-only -q`
Expected: PASS and no import-collection error from `tests/test_basic.py`

- [ ] **Step 5: Commit**

```bash
git add tests/test_monetization_compat.py src/monetization/__init__.py
git commit -m "test: restore monetization import compatibility"
```

### Task 2: Define The Core DeFi Contracts And Runtime Settings

**Files:**
- Create: `src/defi/contracts.py`
- Modify: `src/config.py`
- Modify: `src/defi/entities.py`
- Test: `tests/defi/test_opportunity_analysis_contract.py`

- [ ] **Step 1: Write the failing contract test**

```python
from src.defi.contracts import AnalysisStatus, OpportunityAnalysis


def test_analysis_status_carries_provisional_results_and_version():
    status = AnalysisStatus(
        analysis_id="ana_123",
        status="running",
        score_model_version="defi-v2",
        provisional_shortlist=[],
    )
    assert status.status == "running"
    assert status.score_model_version == "defi-v2"


def test_opportunity_analysis_exposes_behavior_and_recommendation_sections():
    analysis = OpportunityAnalysis.model_validate(
        {
            "identity": {"id": "opp_1", "chain": "solana", "kind": "pool", "protocol_slug": "orca"},
            "scores": {"deterministic_score": 72, "ai_judgment_score": 68, "final_deployability_score": 70},
            "behavior": {"whale_flow_direction": "accumulating"},
            "recommendation": {"action": "watch", "rationale": ["need more evidence"]},
        }
    )
    assert analysis.behavior.whale_flow_direction == "accumulating"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/defi/test_opportunity_analysis_contract.py -q`
Expected: FAIL with `ModuleNotFoundError` or missing-field validation errors

- [ ] **Step 3: Write minimal implementation**

```python
class AnalysisStatus(BaseModel):
    analysis_id: str
    status: Literal["queued", "running", "completed", "failed"]
    score_model_version: str
    provisional_shortlist: list[dict] = []


class BehaviorSummary(BaseModel):
    whale_flow_direction: str = "unknown"


class RecommendationSummary(BaseModel):
    action: Literal["deploy", "deploy_small", "watch", "avoid"]
    rationale: list[str] = []


class OpportunityAnalysis(BaseModel):
    identity: dict
    scores: dict
    behavior: BehaviorSummary
    recommendation: RecommendationSummary
```

- [ ] **Step 4: Add the first runtime settings**

```python
defi_scan_limit: int = Field(48, env="DEFI_SCAN_LIMIT")
defi_top_band_limit: int = Field(12, env="DEFI_TOP_BAND_LIMIT")
defi_provider_timeout_seconds: int = Field(8, env="DEFI_PROVIDER_TIMEOUT_SECONDS")
defi_analysis_ttl_seconds: int = Field(300, env="DEFI_ANALYSIS_TTL_SECONDS")
defi_score_model_version: str = Field("defi-v2", env="DEFI_SCORE_MODEL_VERSION")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/defi/test_opportunity_analysis_contract.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/defi/test_opportunity_analysis_contract.py src/defi/contracts.py src/config.py src/defi/entities.py
git commit -m "feat: add core DeFi analysis contracts"
```

### Task 3: Add Analysis And Evidence Stores

**Files:**
- Create: `src/defi/stores/analysis_store.py`
- Create: `src/defi/stores/evidence_store.py`
- Modify: `src/storage/cache.py`
- Modify: `src/defi/history_store.py`
- Modify: `src/defi/docs_analyzer.py`
- Test: `tests/defi/test_analysis_store.py`
- Test: `tests/defi/test_opportunity_document_index.py`

- [ ] **Step 1: Write the failing store tests**

```python
import pytest

from src.defi.stores.analysis_store import AnalysisStore


@pytest.mark.asyncio
async def test_analysis_store_round_trips_provisional_payload():
    store = AnalysisStore()
    await store.save_status("ana_1", {"status": "running", "provisional_shortlist": [{"id": "opp_1"}]})
    saved = await store.get_status("ana_1")
    assert saved["provisional_shortlist"][0]["id"] == "opp_1"


@pytest.mark.asyncio
async def test_analysis_store_round_trips_completed_opportunity_by_id():
    store = AnalysisStore()
    await store.save_opportunity_document("opp_1", {"identity": {"id": "opp_1"}, "recommendation": {"action": "watch"}})
    saved = await store.get_opportunity_document("opp_1")
    assert saved["identity"]["id"] == "opp_1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/defi/test_analysis_store.py tests/defi/test_opportunity_document_index.py -q`
Expected: FAIL with `ModuleNotFoundError` for `src.defi.stores.analysis_store`

- [ ] **Step 3: Write minimal implementation**

```python
class AnalysisStore:
    def __init__(self, cache: CacheManager | None = None):
        self.cache = cache or CacheManager()

    async def save_status(self, analysis_id: str, payload: dict) -> None:
        await self.cache.set(f"defi:analysis:{analysis_id}", payload)

    async def get_status(self, analysis_id: str) -> dict | None:
        return await self.cache.get(f"defi:analysis:{analysis_id}")

    async def save_opportunity_document(self, opportunity_id: str, payload: dict) -> None:
        await self.cache.set(f"defi:opportunity:{opportunity_id}", payload)

    async def get_opportunity_document(self, opportunity_id: str) -> dict | None:
        return await self.cache.get(f"defi:opportunity:{opportunity_id}")
```

- [ ] **Step 4: Wire docs and history through the evidence store**

```python
cached = await evidence_store.get_docs(protocol_slug)
if cached:
    return cached
profile = await self._analyze_docs_live(protocol_url, docs_url)
await evidence_store.set_docs(protocol_slug, profile)
return profile
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/defi/test_analysis_store.py tests/defi/test_opportunity_document_index.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/defi/test_analysis_store.py tests/defi/test_opportunity_document_index.py src/defi/stores/analysis_store.py src/defi/stores/evidence_store.py src/storage/cache.py src/defi/history_store.py src/defi/docs_analyzer.py
git commit -m "feat: add durable DeFi analysis stores"
```

### Task 4: Add Budgets And Request Coalescing

**Files:**
- Create: `src/defi/pipeline/budgets.py`
- Create: `src/defi/pipeline/coalescing.py`
- Modify: `src/config.py`
- Test: `tests/defi/test_pipeline_budgets.py`
- Test: `tests/defi/test_request_coalescing.py`

- [ ] **Step 1: Write the failing runtime tests**

```python
import asyncio
import pytest

from src.defi.pipeline.coalescing import CoalescedAnalysisRunner


@pytest.mark.asyncio
async def test_coalescing_reuses_the_same_in_flight_task():
    calls = 0

    async def build():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return {"analysis_id": "ana_1"}

    runner = CoalescedAnalysisRunner()
    first, second = await asyncio.gather(runner.run("key", build), runner.run("key", build))
    assert calls == 1
    assert first == second
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/defi/test_pipeline_budgets.py tests/defi/test_request_coalescing.py -q`
Expected: FAIL with missing pipeline modules

- [ ] **Step 3: Write minimal implementation**

```python
@dataclass(slots=True)
class ProviderBudget:
    timeout_seconds: int
    concurrency_limit: int


class CoalescedAnalysisRunner:
    def __init__(self):
        self._inflight: dict[str, asyncio.Task] = {}

    async def run(self, key: str, factory):
        task = self._inflight.get(key)
        if task is None:
            task = asyncio.create_task(factory())
            self._inflight[key] = task
        try:
            return await task
        finally:
            self._inflight.pop(key, None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/defi/test_pipeline_budgets.py tests/defi/test_request_coalescing.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/defi/test_pipeline_budgets.py tests/defi/test_request_coalescing.py src/defi/pipeline/budgets.py src/defi/pipeline/coalescing.py src/config.py
git commit -m "feat: add DeFi runtime budgets and coalescing"
```

### Task 5: Extract Pass 1 Market Scan

**Files:**
- Create: `src/defi/pipeline/scan.py`
- Modify: `src/defi/pool_analyzer.py`
- Modify: `src/defi/farm_analyzer.py`
- Modify: `src/defi/lending_analyzer.py`
- Modify: `src/defi/opportunity_taxonomy.py`
- Test: `tests/defi/test_pipeline_scan.py`
- Test: `tests/defi/test_provider_normalization.py`
- Test: `tests/defi/test_chain_support_matrix.py`
- Test: `tests/test_defi_taxonomy.py`

- [ ] **Step 1: Write the failing market-scan tests**

```python
from src.defi.pipeline.scan import MarketScanPipeline


def test_market_scan_normalizes_pool_farm_and_lending_candidates():
    pipeline = MarketScanPipeline()
    normalized = pipeline.normalize_candidates(
        pools=[{"project": "orca-dex", "symbol": "SOL-USDC", "apy": 12.5}],
        yields=[{"project": "jito", "symbol": "JTO", "apy": 8.0}],
        markets=[{"protocol": "aave-v3", "symbol": "USDC", "apy_supply": 4.2}],
    )
    assert {item["candidate_kind"] for item in normalized} == {"pool", "yield", "lending_supply"}


def test_provider_normalization_preserves_all_phase1_chains():
    pipeline = MarketScanPipeline()
    chains = {"solana", "ethereum", "base", "arbitrum", "bsc", "polygon", "optimism", "avalanche"}
    normalized = {pipeline.normalize_chain_name(chain) for chain in chains}
    assert normalized == chains
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/defi/test_pipeline_scan.py tests/defi/test_provider_normalization.py tests/defi/test_chain_support_matrix.py tests/test_defi_taxonomy.py -q`
Expected: FAIL because `MarketScanPipeline` does not exist or lending candidates are not normalized to `lending_supply`

- [ ] **Step 3: Write minimal implementation**

```python
class MarketScanPipeline:
    def normalize_candidates(self, *, pools: list[dict], yields: list[dict], markets: list[dict]) -> list[dict]:
        candidates = []
        candidates.extend(self._normalize_pool(pool) for pool in pools)
        candidates.extend(self._normalize_yield(item) for item in yields)
        candidates.extend(self._normalize_lending_supply(item) for item in markets)
        return candidates
```

- [ ] **Step 4: Add a cheap first-pass shortlist score**

```python
candidate["scan_score"] = round(
    (candidate["tvl_score"] * 0.35)
    + (candidate["apr_score"] * 0.25)
    + (candidate["protocol_size_score"] * 0.20)
    + (candidate["liquidity_score"] * 0.20),
    2,
)

PHASE1_CHAINS = {"solana", "ethereum", "base", "arbitrum", "bsc", "polygon", "optimism", "avalanche"}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/defi/test_pipeline_scan.py tests/defi/test_provider_normalization.py tests/defi/test_chain_support_matrix.py tests/test_defi_taxonomy.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/defi/test_pipeline_scan.py tests/defi/test_provider_normalization.py tests/defi/test_chain_support_matrix.py tests/test_defi_taxonomy.py src/defi/pipeline/scan.py src/defi/pool_analyzer.py src/defi/farm_analyzer.py src/defi/lending_analyzer.py src/defi/opportunity_taxonomy.py
git commit -m "feat: add DeFi market scan pipeline"
```

### Task 6: Extract Pass 2 Selective Enrichment

**Files:**
- Create: `src/defi/pipeline/enrich.py`
- Modify: `src/defi/history_store.py`
- Modify: `src/defi/docs_analyzer.py`
- Modify: `src/defi/evidence.py`
- Test: `tests/defi/test_pipeline_enrichment.py`

- [ ] **Step 1: Write the failing enrichment tests**

```python
import pytest

from src.defi.pipeline.enrich import EnrichmentPipeline


@pytest.mark.asyncio
async def test_enrichment_marks_timeout_sources_as_fallbacks():
    pipeline = EnrichmentPipeline(provider_timeout_seconds=0)
    enriched = await pipeline.enrich_candidate({"id": "opp_1", "protocol_slug": "aave-v3"})
    assert enriched["evidence_sources"]["docs"]["fallback_used"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/defi/test_pipeline_enrichment.py -q`
Expected: FAIL with missing enrichment pipeline

- [ ] **Step 3: Write minimal implementation**

```python
class EnrichmentPipeline:
    async def enrich_candidate(self, candidate: dict) -> dict:
        docs = await self._load_with_budget("docs", lambda: self.docs.analyze(candidate.get("protocol_url"), candidate.get("docs_url")))
        history = await self._load_with_budget("history", lambda: self.history.get_pool_history(candidate.get("pool_id") or candidate["id"]))
        return {**candidate, "docs_profile": docs.payload, "history_summary": history.payload, "evidence_sources": {"docs": docs.meta, "history": history.meta}}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/defi/test_pipeline_enrichment.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/defi/test_pipeline_enrichment.py src/defi/pipeline/enrich.py src/defi/history_store.py src/defi/docs_analyzer.py src/defi/evidence.py
git commit -m "feat: add selective DeFi enrichment pipeline"
```

### Task 7: Split Deterministic Scoring Into Factor And Archetype Modules

**Files:**
- Create: `src/defi/scoring/deterministic.py`
- Create: `src/defi/scoring/factors/protocol_integrity.py`
- Create: `src/defi/scoring/factors/market_structure.py`
- Create: `src/defi/scoring/factors/apr_quality.py`
- Create: `src/defi/scoring/factors/position_risk.py`
- Create: `src/defi/scoring/factors/exit_quality.py`
- Create: `src/defi/scoring/factors/behavior.py`
- Create: `src/defi/scoring/factors/chain_risk.py`
- Create: `src/defi/scoring/factors/confidence.py`
- Create: `src/defi/scoring/archetypes/lp.py`
- Create: `src/defi/scoring/archetypes/farm.py`
- Create: `src/defi/scoring/archetypes/lending_supply.py`
- Create: `src/defi/scoring/archetypes/vault.py`
- Modify: `src/defi/risk_engine.py`
- Modify: `requirements.txt`
- Test: `tests/defi/test_scoring_lp.py`
- Test: `tests/defi/test_scoring_farm.py`
- Test: `tests/defi/test_scoring_lending_supply.py`
- Test: `tests/defi/test_scoring_vault.py`
- Test: `tests/defi/test_apr_haircuts.py`
- Test: `tests/defi/test_risk_to_apr_ratio.py`
- Test: `tests/defi/test_decision_bundle.py`
- Test: `tests/defi/test_ranking_invariants.py`

- [ ] **Step 1: Write the failing scoring tests**

```python
from src.defi.scoring.deterministic import DeterministicScorer


def test_lp_scoring_returns_haircut_apr_and_risk_to_apr_ratio():
    scorer = DeterministicScorer()
    result = scorer.score(
        kind="pool",
        candidate={"product_type": "stable_lp", "apy": 8.0, "apy_base": 6.0, "apy_reward": 2.0},
        context={"behavior": {"capital_concentration_score": 82, "anomaly_flags": [{"code": "liquidity_drain", "severity": "high"}]}, "history": {}, "docs": {}},
    )
    assert result["summary"]["gross_apr"] == 8.0
    assert result["summary"]["haircut_apr"] < 8.0
    assert result["summary"]["net_expected_apr"] <= result["summary"]["haircut_apr"]
    assert result["summary"]["weighted_risk_burden"] > 0
    assert result["summary"]["risk_to_apr_ratio"] > 0
    assert result["summary"]["best_fit_risk_profile"] in {"conservative", "balanced", "aggressive"}
    assert "liquidity_drain" in result["summary"]["fragility_flags"]


from hypothesis import given, strategies as st


@given(st.floats(min_value=0, max_value=100), st.floats(min_value=0, max_value=100))
def test_missing_evidence_never_increases_confidence(stronger_evidence, weaker_evidence):
    scorer = DeterministicScorer()
    strong = scorer.build_confidence({"evidence_score": stronger_evidence, "missing_critical": False})
    weak = scorer.build_confidence({"evidence_score": weaker_evidence, "missing_critical": True})
    assert weak["confidence_reasoning"]
    assert weak["score"] <= strong["score"] or weaker_evidence <= stronger_evidence
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/defi/test_scoring_lp.py tests/defi/test_apr_haircuts.py tests/defi/test_risk_to_apr_ratio.py tests/defi/test_decision_bundle.py tests/defi/test_ranking_invariants.py -q`
Expected: FAIL because `DeterministicScorer` and the new summary fields do not exist

- [ ] **Step 3: Write minimal implementation**

```python
# requirements.txt
hypothesis>=6.0

gross_apr = max(candidate.get("apy", 0.0), 0.0)
reward_drag = min(candidate.get("apy_reward", 0.0) * 0.35, gross_apr)
haircut_apr = round(max(gross_apr - reward_drag, 0.0), 4)
net_expected_apr = round(max(haircut_apr - exit_drag - rebalance_drag, 0.0), 4)
weighted_risk_burden = round((100 - safety_score) * 0.6 + position_risk_score * 0.4, 4)
behavior_score = score_behavior(context["behavior"])
weighted_risk_burden = round(weighted_risk_burden + (behavior_score * 0.25), 4)
risk_to_apr_ratio = round(weighted_risk_burden / max(haircut_apr, 0.01), 4)
fragility_flags = ["reward_heavy"] if reward_drag > 0 else []
fragility_flags.extend(flag["code"] for flag in context["behavior"].get("anomaly_flags", []))
kill_switches = ["recent_critical_incident"] if recent_critical else []
best_fit_risk_profile = "conservative" if safety_score >= 80 else "balanced"
confidence_reasoning = confidence_report["notes"]
```

- [ ] **Step 4: Move archetype-specific logic out of `src/defi/risk_engine.py`**

```python
ARCHETYPE_SCORERS = {
    "pool": score_lp,
    "yield": score_farm,
    "lending_supply": score_lending_supply,
    "vault": score_vault,
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/defi/test_scoring_lp.py tests/defi/test_scoring_farm.py tests/defi/test_scoring_lending_supply.py tests/defi/test_scoring_vault.py tests/defi/test_apr_haircuts.py tests/defi/test_risk_to_apr_ratio.py tests/defi/test_decision_bundle.py tests/defi/test_ranking_invariants.py tests/test_defi_scoring.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add requirements.txt tests/defi/test_scoring_lp.py tests/defi/test_scoring_farm.py tests/defi/test_scoring_lending_supply.py tests/defi/test_scoring_vault.py tests/defi/test_apr_haircuts.py tests/defi/test_risk_to_apr_ratio.py tests/defi/test_decision_bundle.py tests/defi/test_ranking_invariants.py tests/test_defi_scoring.py src/defi/scoring src/defi/risk_engine.py
git commit -m "feat: split deterministic DeFi scoring modules"
```

### Task 8: Add AI Judgment, Final Ranking, And The Stable Assembler

**Files:**
- Create: `src/defi/scoring/ai_judgment.py`
- Create: `src/defi/scoring/final_ranker.py`
- Create: `src/defi/assemblers/opportunity_analysis.py`
- Modify: `src/defi/ai_router.py`
- Create: `src/defi/pipeline/synthesize.py`
- Test: `tests/defi/test_pipeline_synthesis.py`
- Test: `tests/defi/test_ai_explanation_golden.py`
- Create: `tests/fixtures/defi/ai_judgment_golden.json`

- [ ] **Step 1: Write the failing synthesis tests**

```python
import json
from pathlib import Path

from src.defi.pipeline.synthesize import SynthesisPipeline


def test_synthesis_combines_deterministic_and_ai_scores_without_bypassing_caps():
    pipeline = SynthesisPipeline()
    analysis = pipeline.combine(
        deterministic={"final_score": 62, "hard_caps": ["recent_critical_incident"]},
        ai={"judgment_score": 90},
    )
    assert analysis.scores.final_deployability_score <= 62
    assert analysis.recommendation.action == "avoid"


def test_ai_explanation_matches_golden_headline():
    fixture = json.loads(Path("tests/fixtures/defi/ai_judgment_golden.json").read_text())
    payload = build_ai_judgment_payload(protocol="aave-v3", chain="base", gross_apr=5.2, risk_to_apr_ratio=3.1)
    explanation = render_ai_judgment(payload)
    assert explanation["headline"] == fixture["base_aave_supply_headline"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/defi/test_pipeline_synthesis.py tests/defi/test_ai_explanation_golden.py -q`
Expected: FAIL with missing synthesis pipeline

- [ ] **Step 3: Write minimal implementation**

```python
ai_weight = 0.5 if evidence_confidence >= 60 else 0.2
blended = (deterministic_score * (1 - ai_weight)) + (ai_judgment_score * ai_weight)
if hard_caps:
    blended = min(blended, deterministic_score)
action = "avoid" if hard_caps else "watch"
```

- [ ] **Step 4: Emit the full `OpportunityAnalysis` contract**

```python
return OpportunityAnalysis(
    identity=identity,
    market=market,
    scores=scores,
    factors=factors,
    behavior=behavior,
    scenarios=scenarios,
    recommendation=recommendation,
    evidence=evidence,
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/defi/test_pipeline_synthesis.py tests/defi/test_ai_explanation_golden.py tests/defi/test_opportunity_analysis_contract.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/defi/test_pipeline_synthesis.py tests/defi/test_ai_explanation_golden.py tests/fixtures/defi/ai_judgment_golden.json src/defi/scoring/ai_judgment.py src/defi/scoring/final_ranker.py src/defi/assemblers/opportunity_analysis.py src/defi/ai_router.py src/defi/pipeline/synthesize.py
git commit -m "feat: add AI judgment and opportunity synthesis"
```

### Task 9: Add First-Layer Behavioral Signals

**Files:**
- Create: `src/analytics/signal_models.py`
- Create: `src/analytics/behavior_signals.py`
- Create: `src/analytics/behavior_adapters/evm.py`
- Modify: `src/analytics/time_series.py`
- Modify: `src/analytics/anomaly_detector.py`
- Modify: `src/analytics/wallet_forensics.py`
- Modify: `src/data/solana.py`
- Modify: `src/api/routes/whale.py`
- Test: `tests/analytics/test_behavior_signal_models.py`
- Test: `tests/analytics/test_behavior_signals.py`
- Test: `tests/analytics/test_evm_behavior_adapter.py`
- Test: `tests/analytics/test_time_series_store.py`
- Test: `tests/analytics/test_anomaly_detector_behavior.py`
- Test: `tests/analytics/test_wallet_forensics_entity_heuristics.py`

- [ ] **Step 1: Write the failing behavioral tests**

```python
from src.analytics.behavior_signals import BehaviorSignalBuilder


def test_behavior_signals_emit_direction_concentration_and_stickiness():
    builder = BehaviorSignalBuilder()
    result = builder.build(
        whale_summary={"net_flow_usd": 120000, "buy_count": 5, "sell_count": 1},
        concentration={"top_wallet_share": 0.38},
        anomalies=[{"code": "liquidity_drain", "severity": "high"}],
    )
    assert result.whale_flow_direction == "accumulating"
    assert result.capital_concentration_score > 0
    assert result.anomaly_flags[0].code == "liquidity_drain"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/analytics/test_behavior_signal_models.py tests/analytics/test_behavior_signals.py tests/analytics/test_anomaly_detector_behavior.py -q`
Expected: FAIL because the new signal models and builder do not exist

- [ ] **Step 3: Write minimal implementation**

```python
class BehaviorSignalBuilder:
    def build(self, *, whale_summary: dict, concentration: dict, anomalies: list[dict]):
        direction = "accumulating" if whale_summary.get("net_flow_usd", 0) > 0 else "distributing"
        return BehaviorSummary(
            whale_flow_direction=direction,
            capital_concentration_score=round(concentration.get("top_wallet_share", 0) * 100, 2),
            anomaly_flags=[AnomalySignal.model_validate(item) for item in anomalies],
        )
```

- [ ] **Step 4: Add the shared EVM behavior adapter**

```python
class EvmBehaviorAdapter:
    async def collect(self, *, chain: str, pool_address: str, from_block: int | None = None) -> dict:
        events = await self.registry.get_client(chain).get_logs(pool_address, from_block=from_block)
        return summarize_evm_flow_events(events)
```

- [ ] **Step 5: Replace synthetic-trending whales as the primary Solana path**

```python
if real_transactions:
    return self._summarize_real_whale_transactions(real_transactions)
return self._summarize_fallback_whales(min_amount_usd=min_amount_usd, limit=limit, fallback_used=True)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/analytics/test_behavior_signal_models.py tests/analytics/test_behavior_signals.py tests/analytics/test_evm_behavior_adapter.py tests/analytics/test_time_series_store.py tests/analytics/test_anomaly_detector_behavior.py tests/analytics/test_wallet_forensics_entity_heuristics.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add tests/analytics/test_behavior_signal_models.py tests/analytics/test_behavior_signals.py tests/analytics/test_evm_behavior_adapter.py tests/analytics/test_time_series_store.py tests/analytics/test_anomaly_detector_behavior.py tests/analytics/test_wallet_forensics_entity_heuristics.py src/analytics/signal_models.py src/analytics/behavior_signals.py src/analytics/behavior_adapters/evm.py src/analytics/time_series.py src/analytics/anomaly_detector.py src/analytics/wallet_forensics.py src/data/solana.py src/api/routes/whale.py
git commit -m "feat: add first-layer DeFi behavior signals"
```

### Task 10: Integrate The Pipeline Into `DefiOpportunityEngine`

**Files:**
- Modify: `src/defi/opportunity_engine.py`
- Modify: `src/defi/intelligence_engine.py`
- Modify: `src/defi/contracts.py`
- Modify: `src/defi/stores/analysis_store.py`
- Create: `tests/defi/test_intelligence_engine_async.py`
- Test: `tests/defi/test_pipeline_scan.py`
- Test: `tests/defi/test_pipeline_enrichment.py`
- Test: `tests/defi/test_pipeline_synthesis.py`

- [ ] **Step 1: Write the failing engine integration test**

```python
import pytest

from src.defi.intelligence_engine import DefiIntelligenceEngine


@pytest.mark.asyncio
async def test_intelligence_engine_returns_async_analysis_status():
    engine = DefiIntelligenceEngine()
    first = await engine.start_opportunity_analysis(chain="solana", limit=5)
    second = await engine.start_opportunity_analysis(chain="solana", limit=5)
    status = first
    assert status.status in {"queued", "running", "completed"}
    assert status.analysis_id.startswith("ana_")
    assert second.analysis_id == first.analysis_id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/defi/test_intelligence_engine_async.py -q`
Expected: FAIL because the engine still builds opportunities inline and has no async analysis lifecycle

- [ ] **Step 3: Write minimal implementation**

```python
async def start_opportunity_analysis(self, **filters) -> AnalysisStatus:
    request_key = self.scan_pipeline.build_request_key(filters)

    async def _start_new_analysis() -> AnalysisStatus:
        analysis_id = self.analysis_store.new_id()
        provisional = await self.scan_pipeline.run(**filters)
        await self.analysis_store.save_status(analysis_id, {"status": "running", "provisional_shortlist": provisional})
        asyncio.create_task(self._finish_analysis(analysis_id, filters, provisional))
        return AnalysisStatus(analysis_id=analysis_id, status="running", provisional_shortlist=provisional, score_model_version=settings.defi_score_model_version)

    return await self.coalescer.run(request_key, _start_new_analysis)
```

- [ ] **Step 4: Keep legacy entry points delegating to the new pipeline**

```python
async def analyze_market(self, chain=None, query=None, min_tvl=100_000, min_apy=3.0, limit=12, include_ai=True, ranking_profile=None):
    status = await self.start_opportunity_analysis(chain=chain, query=query, min_tvl=min_tvl, min_apy=min_apy, limit=limit, include_ai=include_ai, ranking_profile=ranking_profile)
    return await self.get_completed_or_provisional_result(status.analysis_id)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/defi/test_intelligence_engine_async.py tests/defi/test_pipeline_scan.py tests/defi/test_pipeline_enrichment.py tests/defi/test_pipeline_synthesis.py tests/test_defi_scoring.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/defi/opportunity_engine.py src/defi/intelligence_engine.py src/defi/contracts.py tests/defi/test_intelligence_engine_async.py tests/defi/test_pipeline_scan.py tests/defi/test_pipeline_enrichment.py tests/defi/test_pipeline_synthesis.py tests/test_defi_scoring.py
git commit -m "feat: wire DeFi engine to async opportunity pipeline"
```

### Task 11: Add Observability And API Reliability Guardrails

**Files:**
- Create: `src/defi/observability.py`
- Modify: `src/defi/contracts.py`
- Modify: `src/defi/stores/analysis_store.py`
- Modify: `src/defi/pipeline/scan.py`
- Modify: `src/defi/pipeline/enrich.py`
- Modify: `src/defi/pipeline/synthesize.py`
- Modify: `src/api/middleware/rate_limit.py`
- Modify: `src/api/routes/auth.py`
- Modify: `src/api/app.py`
- Test: `tests/defi/test_observability_metrics.py`
- Test: `tests/api/test_auth_rate_limit_middleware.py`

- [ ] **Step 1: Write the failing reliability tests**

```python
from src.defi.observability import AnalysisMetrics


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
```

```python
import pytest
from aiohttp import web

from src.api.middleware.rate_limit import rate_limit_middleware
from src.api.routes.auth import auth_middleware


@pytest.mark.asyncio
async def test_authenticated_request_uses_wallet_key_before_rate_limit(aiohttp_client, monkeypatch):
    async def handler(request):
        return web.json_response({"rate_limit_key": request.get("rate_limit_key")})

    async def fake_get_session(_token):
        return {"wallet": "So11111111111111111111111111111111111111112"}

    monkeypatch.setattr("src.storage.sessions.get_session_store", lambda: type("Store", (), {"get_session": fake_get_session})())
    app = web.Application(middlewares=[auth_middleware, rate_limit_middleware])
    app.router.add_get("/check", handler)
    client = await aiohttp_client(app)
    response = await client.get("/check", headers={"Authorization": "Bearer token"})
    payload = await response.json()
    assert payload["rate_limit_key"].startswith("wallet:")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/defi/test_observability_metrics.py tests/api/test_auth_rate_limit_middleware.py -q`
Expected: FAIL because the metrics model and middleware ordering fix do not exist yet

- [ ] **Step 3: Write minimal observability implementation**

```python
class AnalysisMetrics(BaseModel):
    total_latency_ms: float = 0.0
    stage_latency_ms: dict[str, float] = {}
    provider_stats: dict[str, dict[str, float | int]] = {}
    cache_stats: dict[str, dict[str, int]] = {}
    enrichment_coverage_pct: float = 0.0
    ai_runtime_ms: float | None = None
    ai_cost_usd: float | None = None
    factor_model_version: str = "defi-v2"
    rank_change_reasons: list[str] = []
```

- [ ] **Step 4: Fix middleware ordering and authenticated limiter reuse**

```python
def get_authenticated_rate_limiter() -> RateLimiter:
    return _authenticated_rate_limiter


app = web.Application(
    middlewares=[
        cors_middleware,
        auth_middleware,
        rate_limit_middleware,
    ]
)
```

- [ ] **Step 5: Record metrics while the pipeline runs**

```python
metrics.stage_latency_ms[stage_name] = elapsed_ms
metrics.provider_stats.setdefault(provider_name, {"calls": 0, "failures": 0, "latency_ms": 0.0})
metrics.provider_stats[provider_name]["calls"] += 1
metrics.provider_stats[provider_name]["latency_ms"] = elapsed_ms
metrics.enrichment_coverage_pct = round(completed_enrichment_steps / max(total_enrichment_steps, 1) * 100, 1)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/defi/test_observability_metrics.py tests/api/test_auth_rate_limit_middleware.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/defi/observability.py src/defi/contracts.py src/defi/stores/analysis_store.py src/defi/pipeline/scan.py src/defi/pipeline/enrich.py src/defi/pipeline/synthesize.py src/api/middleware/rate_limit.py src/api/routes/auth.py src/api/app.py tests/defi/test_observability_metrics.py tests/api/test_auth_rate_limit_middleware.py
git commit -m "feat: add DeFi observability and API reliability guardrails"
```

### Task 12: Add Opportunity API Schemas And Routes

**Files:**
- Create: `src/api/routes/opportunities.py`
- Modify: `src/api/app.py`
- Modify: `src/api/middleware/rate_limit.py`
- Modify: `src/api/routes/auth.py`
- Modify: `src/api/schemas/requests.py`
- Modify: `src/api/schemas/responses.py`
- Test: `tests/api/test_opportunity_routes.py`
- Test: `tests/api/test_opportunity_compare_route.py`
- Test: `tests/api/test_opportunity_read_route.py`

- [ ] **Step 1: Write the failing API contract tests**

```python
import pytest
from aiohttp import web

from src.api.routes.opportunities import setup_opportunity_routes


class FakeOpportunityService:
    async def start_opportunity_analysis(self, **_filters):
        return {
            "analysis_id": "ana_123",
            "status": "running",
            "score_model_version": "defi-v2",
            "freshness": {"generated_at": "2026-03-17T00:00:00Z"},
            "provisional_shortlist": [],
            "progress": {"stage": "scan", "percent": 25},
        }

    async def get_opportunity_analysis(self, analysis_id: str):
        return {
            "analysis_id": analysis_id,
            "status": "completed",
            "score_model_version": "defi-v2",
            "freshness": {"generated_at": "2026-03-17T00:00:10Z"},
            "provisional_shortlist": [],
            "progress": {"stage": "completed", "percent": 100},
            "result": {"identity": {"id": "opp_1"}, "recommendation": {"action": "watch", "rationale": ["completed payload"]}},
        }

    async def get_opportunity(self, opportunity_id: str):
        return {
            "identity": {"id": opportunity_id, "chain": "solana", "kind": "pool", "protocol_slug": "orca"},
            "scores": {"final_deployability_score": 72},
            "behavior": {"whale_flow_direction": "accumulating"},
            "recommendation": {"action": "watch", "rationale": ["waiting on more evidence"]},
            "evidence": {"freshness": {"generated_at": "2026-03-17T00:00:20Z"}},
        }

    async def compare_opportunities(self, items):
        return {"items": items, "matrix": []}


@pytest.mark.asyncio
async def test_create_opportunity_analysis_returns_analysis_id(aiohttp_client):
    app = web.Application()
    app["opportunity_service"] = FakeOpportunityService()
    setup_opportunity_routes(app)
    client = await aiohttp_client(app)
    response = await client.post("/opportunities/analyses", json={"chain": "solana", "limit": 5})
    payload = await response.json()
    assert response.status == 202
    assert payload["analysis_id"] == "ana_123"
    assert payload["score_model_version"] == "defi-v2"
    assert payload["freshness"]["generated_at"] == "2026-03-17T00:00:00Z"
    second = await client.post("/opportunities/analyses", json={"chain": "solana", "limit": 5})
    second_payload = await second.json()
    assert second_payload["analysis_id"] == payload["analysis_id"]


@pytest.mark.asyncio
async def test_compare_accepts_opportunity_ids_and_analysis_ids(aiohttp_client):
    app = web.Application()
    app["opportunity_service"] = FakeOpportunityService()
    setup_opportunity_routes(app)
    client = await aiohttp_client(app)
    response = await client.post("/opportunities/compare", json={"items": [{"opportunity_id": "opp_1"}, {"analysis_id": "ana_2", "opportunity_id": "opp_2"}]})
    assert response.status == 200


@pytest.mark.asyncio
async def test_get_opportunity_reads_latest_completed_document(aiohttp_client):
    app = web.Application()
    app["opportunity_service"] = FakeOpportunityService()
    setup_opportunity_routes(app)
    client = await aiohttp_client(app)
    response = await client.get("/opportunities/opp_1")
    payload = await response.json()
    assert response.status == 200
    assert payload["identity"]["id"] == "opp_1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_opportunity_routes.py tests/api/test_opportunity_compare_route.py tests/api/test_opportunity_read_route.py -q`
Expected: FAIL with missing routes or missing request/response models

- [ ] **Step 3: Write minimal request and response schemas**

```python
class OpportunityAnalysisCreateRequest(BaseModel):
    chain: str | None = None
    query: str | None = None
    limit: int = Field(default=12, ge=1, le=50)


class OpportunityAnalysisStatusResponse(BaseModel):
    analysis_id: str
    status: str
    score_model_version: str
    freshness: dict[str, Any]
    provisional_shortlist: list[DefiOpportunityResponse] = []
    progress: dict[str, Any] = {}
    metrics: dict[str, Any] = {}
    result: OpportunityAnalysisResponse | None = None
```

- [ ] **Step 4: Implement the four routes and register them**

```python
app.router.add_post("/opportunities/analyses", create_opportunity_analysis)
app.router.add_get("/opportunities/analyses/{analysis_id}", get_opportunity_analysis)
app.router.add_get("/opportunities/{opportunity_id}", get_opportunity)
app.router.add_post("/opportunities/compare", compare_opportunities)

async def create_opportunity_analysis(request):
    payload = OpportunityAnalysisCreateRequest.model_validate(await request.json()).model_dump()
    status = await request.app["opportunity_service"].start_opportunity_analysis(**payload)
    return web.json_response(status, status=202)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/api/test_opportunity_routes.py tests/api/test_opportunity_compare_route.py tests/api/test_opportunity_read_route.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/api/test_opportunity_routes.py tests/api/test_opportunity_compare_route.py tests/api/test_opportunity_read_route.py src/api/routes/opportunities.py src/api/app.py src/api/schemas/requests.py src/api/schemas/responses.py
git commit -m "feat: add opportunity analysis API routes"
```

### Task 13: Install The Frontend Test Harness And Client Helpers

**Files:**
- Modify: `web/package.json`
- Create: `web/vitest.config.ts`
- Create: `web/tests/setup.ts`
- Create: `web/tests/smoke/frontend-harness.test.ts`
- Modify: `web/types/index.ts`
- Modify: `web/lib/api.ts`
- Modify: `web/lib/hooks.ts`
- Create: `web/tests/api/opportunities-api.test.ts`
- Create: `web/tests/hooks/useOpportunityAnalysis.test.tsx`

- [ ] **Step 1: Write the failing frontend smoke test**

```ts
import { describe, expect, it } from "vitest"

describe("frontend test harness", () => {
  it("runs in jsdom", () => {
    expect(document.createElement("div")).toBeTruthy()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix web run test -- --run web/tests/smoke/frontend-harness.test.ts`
Expected: FAIL because the `test` script and Vitest config do not exist yet

- [ ] **Step 3: Install the minimal frontend test stack**

```bash
npm --prefix web install -D vitest jsdom @testing-library/react @testing-library/jest-dom
```

- [ ] **Step 4: Write minimal implementation**

```ts
// web/package.json
"scripts": {
  "test": "vitest"
}

// web/lib/hooks.ts
export function useOpportunityAnalysis(analysisId: string | null) {
  return useQuery({
    queryKey: ["opportunity-analysis", analysisId],
    queryFn: () => api.getOpportunityAnalysis(analysisId!),
    enabled: Boolean(analysisId),
    refetchInterval: (query) => query.state.data?.status === "completed" ? false : 1500,
  })
}
```

- [ ] **Step 5: Run targeted tests to verify they pass**

Run: `npm --prefix web run test -- --run web/tests/smoke/frontend-harness.test.ts web/tests/api/opportunities-api.test.ts web/tests/hooks/useOpportunityAnalysis.test.tsx && npm --prefix web run type-check`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add web/package.json web/package-lock.json web/vitest.config.ts web/tests/setup.ts web/tests/smoke/frontend-harness.test.ts web/tests/api/opportunities-api.test.ts web/tests/hooks/useOpportunityAnalysis.test.tsx web/types/index.ts web/lib/api.ts web/lib/hooks.ts
git commit -m "feat: add frontend opportunity analysis client helpers"
```

### Task 14: Build The `/defi` Discover Flow

**Files:**
- Create: `web/app/defi/page.tsx`
- Create: `web/app/defi/_components/discover-client.tsx`
- Create: `web/app/defi/loading.tsx`
- Create: `web/app/defi/error.tsx`
- Create: `web/tests/app/defi-discover.page.test.tsx`
- Modify: `web/lib/hooks.ts`
- Modify: `web/types/index.ts`

- [ ] **Step 1: Write the failing page test**

```tsx
import { render, screen } from "@testing-library/react"
import DiscoverClient from "@/app/defi/_components/discover-client"


it("shows the provisional shortlist while the analysis is still running", async () => {
  render(<DiscoverClient />)
  expect(await screen.findByText(/provisional shortlist/i)).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix web run test -- --run web/tests/app/defi-discover.page.test.tsx`
Expected: FAIL because `/defi` does not exist yet

- [ ] **Step 3: Write minimal implementation**

```tsx
// web/app/defi/page.tsx
import DiscoverClient from "./_components/discover-client"

export default function DiscoverPage() {
  return <DiscoverClient />
}

// web/app/defi/_components/discover-client.tsx
"use client"

export default function DiscoverPage() {
  const create = useCreateOpportunityAnalysis()
  const analysis = useOpportunityAnalysis(create.data?.analysis_id ?? null)

  return (
    <main>
      <h1>DeFi Opportunity Radar</h1>
      <p>Provisional shortlist</p>
      {analysis.data?.provisional_shortlist?.map((item) => <div key={item.id}>{item.title}</div>)}
    </main>
  )
}
```

- [ ] **Step 4: Run tests and static checks**

Run: `npm --prefix web run test -- --run web/tests/app/defi-discover.page.test.tsx && npm --prefix web run type-check`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/app/defi/page.tsx web/app/defi/_components/discover-client.tsx web/app/defi/loading.tsx web/app/defi/error.tsx web/tests/app/defi-discover.page.test.tsx web/lib/hooks.ts web/types/index.ts
git commit -m "feat: add DeFi discover flow"
```

### Task 15: Build The Investigate And Compare Flows

**Files:**
- Create: `web/app/defi/[id]/page.tsx`
- Create: `web/app/defi/_components/detail-client.tsx`
- Create: `web/app/defi/compare/page.tsx`
- Create: `web/app/defi/_components/compare-client.tsx`
- Create: `web/tests/app/defi-detail.page.test.tsx`
- Create: `web/tests/app/defi-compare.page.test.tsx`
- Modify: `web/lib/api.ts`
- Modify: `web/lib/hooks.ts`

- [ ] **Step 1: Write the failing page tests**

```tsx
it("renders behavior, evidence, and scenarios on the detail page", async () => {
  render(<DetailClient opportunityId="opp_1" />)
  expect(await screen.findByText(/behavior/i)).toBeInTheDocument()
  expect(await screen.findByText(/evidence/i)).toBeInTheDocument()
})

it("renders a side-by-side comparison matrix", async () => {
  render(<CompareClient />)
  expect(await screen.findByText(/comparison matrix/i)).toBeInTheDocument()
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm --prefix web run test -- --run web/tests/app/defi-detail.page.test.tsx web/tests/app/defi-compare.page.test.tsx`
Expected: FAIL because the pages and hooks do not exist yet

- [ ] **Step 3: Write minimal implementation**

```tsx
// web/app/defi/[id]/page.tsx
import DetailClient from "../_components/detail-client"

export default function DefiDetailPage({ params }: { params: { id: string } }) {
  return <DetailClient opportunityId={params.id} />
}

// web/app/defi/_components/detail-client.tsx
"use client"

export default function DetailClient({ opportunityId }: { opportunityId: string }) {
  const { data } = useOpportunity(opportunityId)
  return (
    <main>
      <h1>{data?.identity.display_name ?? data?.identity.id}</h1>
      <section><h2>Behavior</h2></section>
      <section><h2>Evidence</h2></section>
      <section><h2>Scenarios</h2></section>
    </main>
  )
}

// web/app/defi/compare/page.tsx
import CompareClient from "../_components/compare-client"

export default function DefiComparePage() {
  return <CompareClient />
}

// web/app/defi/_components/compare-client.tsx
"use client"

export default function CompareClient() {
  const compare = useCompareOpportunities()
  return (
    <main>
      <h1>Comparison Matrix</h1>
      <div>{compare.data?.matrix?.length ?? 0}</div>
    </main>
  )
}
```

- [ ] **Step 4: Run tests and static checks**

Run: `npm --prefix web run test -- --run web/tests/app/defi-detail.page.test.tsx web/tests/app/defi-compare.page.test.tsx && npm --prefix web run type-check && npm --prefix web run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/app/defi/[id]/page.tsx web/app/defi/_components/detail-client.tsx web/app/defi/compare/page.tsx web/app/defi/_components/compare-client.tsx web/tests/app/defi-detail.page.test.tsx web/tests/app/defi-compare.page.test.tsx web/lib/api.ts web/lib/hooks.ts
git commit -m "feat: add DeFi investigate and compare flows"
```

### Task 16: Add Cross-Stack Regression Coverage And Run The Full Verification Matrix

**Files:**
- Modify: `tests/defi/test_pipeline_scan.py`
- Modify: `tests/defi/test_pipeline_enrichment.py`
- Modify: `tests/defi/test_pipeline_synthesis.py`
- Modify: `tests/api/test_opportunity_routes.py`
- Modify: `tests/api/test_opportunity_compare_route.py`
- Modify: `web/tests/app/defi-discover.page.test.tsx`
- Modify: `web/tests/app/defi-detail.page.test.tsx`
- Modify: `web/tests/app/defi-compare.page.test.tsx`

- [ ] **Step 1: Add Solana and EVM regression fixtures to the failing tests**

```python
SOLANA_FIXTURE = {"chain": "solana", "protocol_slug": "orca", "product_type": "stable_lp"}
CHAIN_MATRIX = ["solana", "ethereum", "base", "arbitrum", "bsc", "polygon", "optimism", "avalanche"]
EVM_FIXTURE = {"chain": "base", "protocol_slug": "aave-v3", "product_type": "lending_supply_like"}
```

- [ ] **Step 2: Run the backend regression suite**

Run: `python -m pytest tests/defi tests/analytics tests/api tests/test_defi_scoring.py tests/test_defi_taxonomy.py -q`
Expected: PASS

- [ ] **Step 3: Run the frontend regression suite**

Run: `npm --prefix web run test -- --run web/tests/api/opportunities-api.test.ts web/tests/hooks/useOpportunityAnalysis.test.tsx web/tests/app/defi-discover.page.test.tsx web/tests/app/defi-detail.page.test.tsx web/tests/app/defi-compare.page.test.tsx`
Expected: PASS

- [ ] **Step 4: Run the final build matrix**

Run: `npm --prefix web run type-check && npm --prefix web run build && python -m pytest tests/test_monetization_compat.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/defi/test_pipeline_scan.py tests/defi/test_pipeline_enrichment.py tests/defi/test_pipeline_synthesis.py tests/api/test_opportunity_routes.py tests/api/test_opportunity_compare_route.py web/tests/api/opportunities-api.test.ts web/tests/hooks/useOpportunityAnalysis.test.tsx web/tests/app/defi-discover.page.test.tsx web/tests/app/defi-detail.page.test.tsx web/tests/app/defi-compare.page.test.tsx
git commit -m "test: add DeFi cross-stack regression coverage"
```

## Final Verification Checklist

- `python -m pytest tests/defi tests/analytics tests/api tests/test_defi_scoring.py tests/test_defi_taxonomy.py tests/test_monetization_compat.py -q`
- `npm --prefix web run test -- --run web/tests/api/opportunities-api.test.ts web/tests/hooks/useOpportunityAnalysis.test.tsx web/tests/app/defi-discover.page.test.tsx web/tests/app/defi-detail.page.test.tsx web/tests/app/defi-compare.page.test.tsx`
- `npm --prefix web run type-check`
- `npm --prefix web run build`

If any verification command fails, stop, fix the failure in the same task, and re-run the exact command before moving on.
