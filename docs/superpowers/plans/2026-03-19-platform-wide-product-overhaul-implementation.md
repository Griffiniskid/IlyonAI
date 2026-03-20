# Platform-Wide Product Overhaul Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a cohesive, fast, full-featured AI Sentinel platform by implementing app-shell UX, smart-money intelligence, real-time alerts, rekt intelligence, multi-chain portfolio parity, and reliability hardening.

**Architecture:** Execute in six ordered phases with strict entry/exit gates from the approved spec. Keep implementation event-driven, evidence-first, and progressively rendered (fast lane first, deep lane second). Build shared backend/frontend contracts first, then ship each product surface behind tested route and UI workflows.

**Tech Stack:** Python 3.13, aiohttp, SQLAlchemy, Redis/memory cache, Next.js App Router, React Query, Vitest, pytest

---

## Scope Check and Decomposition

The approved spec spans multiple independent subsystems. To keep execution reliable, this plan decomposes the mega-spec into six independently testable tracks that still ship as one coordinated program:

1. Foundation shell + contracts
2. Smart money platform
3. Real-time + alerts
4. Rekt + multi-chain portfolio
5. Speed + reliability hardening
6. Cross-feature polish + launch verification

This plan intentionally sequences dependencies so each track can be implemented and validated with TDD before the next track consumes it.

## Execution Conventions

- Use @superpowers/test-driven-development for every task.
- Use @superpowers/systematic-debugging for any failing test, flaky stream test, or performance miss.
- Use @superpowers/verification-before-completion before marking each task complete.
- Keep commits small and frequent (one commit per task minimum).
- Do not expand scope beyond the approved spec (YAGNI).

### Atomic Task Slicing Rule

- If a task touches both backend and frontend in the same cycle, split into `Task X.a` (backend contract/tests) and `Task X.b` (frontend integration/tests) before implementation.
- If a task touches more than 5 production files, split it into smaller units with separate failing tests and commits.
- No task should skip the red -> green loop for any changed behavior.

## Resolved Planning Decisions

1. **Event bus standardization**
   - Decision: use Redis pub/sub as primary bus in non-local environments, with `InMemoryEventBus` fallback for local/dev/test.
   - Fallback strategy: auto-degrade to in-memory when Redis is unavailable, while marking `meta.freshness="degraded"` for affected stream payloads.
   - Owner: Platform Delivery.

2. **Alert persistence model**
   - Decision: persist alerts in PostgreSQL via SQLAlchemy tables `alerts`, `alert_rules`, `alert_deliveries` under `src/storage/database.py`.
   - Fallback strategy: in-memory store for tests only; production requires DB-backed persistence.
   - Owner: Safety Loop.

3. **Smart money graph bootstrap sources**
   - Decision: canonical bootstrapping inputs are:
     - Solana: Helius transactions + Solana RPC account history + DexScreener pair context
     - EVM: Moralis wallet/tx data + chain RPC traces + DexScreener market context
   - Fallback strategy: emit reduced-confidence entity/link scores when one source family is missing.
   - Owner: Smart Money Graph.

## File Structure Map

### Backend Platform Contracts and Streaming

- Create: `src/platform/contracts.py` - shared event/envelope contract dataclasses
- Create: `src/platform/event_bus.py` - publish/subscribe abstraction with in-memory default
- Create: `src/platform/stream_hub.py` - WS/SSE subscription manager and fanout
- Create: `src/platform/retry.py` - bounded retry utilities
- Create: `src/platform/dead_letter_queue.py` - dead-letter persistence for failed events
- Create: `src/platform/circuit_breaker.py` - per-source circuit breaker state machine
- Create: `src/api/routes/stream.py` - stream endpoints for live events
- Create: `src/api/response_envelope.py` - standardized API envelope helper
- Modify: `src/api/app.py` - register stream and new domain routes

### Smart Money Domain

- Create: `src/smart_money/models.py` - canonical wallet/entity/flow models
- Create: `src/smart_money/normalizer.py` - Solana/EVM event normalization
- Create: `src/smart_money/graph_store.py` - entity graph persistence and query API
- Create: `src/smart_money/profile_service.py` - wallet/entity profile assembly
- Create: `src/api/routes/smart_money.py` - smart money, flows, profile endpoints
- Modify: `src/analytics/wallet_forensics.py` - replace placeholder pathways
- Modify: `src/data/solana.py` - canonical smart money event extraction
- Modify: `src/analytics/behavior_adapters/evm.py` - canonical event emission

### Alerts and Safety Loop

- Create: `src/alerts/models.py` - alert state model (`new/seen/acknowledged`)
- Create: `src/alerts/store.py` - alert persistence and query layer
- Create: `src/alerts/orchestrator.py` - correlation, dedupe, severity assignment
- Create: `src/api/routes/alerts.py` - alert inbox and rule endpoints
- Create: `src/api/middleware/webhook_signature.py` - outbound webhook signing and verification helpers
- Create: `src/api/middleware/replay_guard.py` - nonce/timestamp replay protection for sensitive mutations
- Create: `src/alerts/audit_log.py` - immutable audit log writer for high-risk config changes
- Modify: `src/agents/sentinel.py` - emit events into orchestrator
- Modify: `src/config.py` - alert/stream SLO config knobs
- Modify: `src/api/middleware/rate_limit.py` - per-scope throttling for alerts and streams
- Modify: `src/api/routes/auth.py` - route scope checks for new alert/rule mutations

### Rekt and Portfolio

- Modify: `src/api/routes/intel.py` - cursor/freshness envelope + richer rekt filters
- Modify: `src/intel/rekt_database.py` - rekt profile and related-incident joins
- Create: `src/portfolio/multichain_aggregator.py` - chain parity holdings aggregation
- Modify: `src/api/routes/portfolio.py` - multi-chain endpoint expansion
- Modify: `src/data/moralis.py` - portfolio ingestion reliability and normalization

### Frontend Shell and Product Surfaces

- Create: `web/components/layout/nav-config.ts` - canonical IA map
- Create: `web/components/layout/app-shell.tsx` - sidebar/topbar/mobile shell
- Create: `web/components/layout/command-palette.tsx` - global action search
- Create: `web/components/layout/alerts-bell.tsx` - unread + quick actions
- Modify: `web/app/layout.tsx` - replace header-only runtime with app shell
- Create: `web/app/smart-money/page.tsx`
- Create: `web/app/flows/page.tsx`
- Create: `web/app/wallet/[address]/page.tsx`
- Create: `web/app/alerts/page.tsx`
- Create: `web/app/rekt/page.tsx`
- Create: `web/app/rekt/[id]/page.tsx`
- Modify: `web/app/whales/page.tsx`
- Modify: `web/app/token/[address]/page.tsx`
- Modify: `web/app/defi/page.tsx`
- Modify: `web/app/defi/[id]/page.tsx`
- Modify: `web/app/portfolio/page.tsx`
- Create: `web/lib/realtime.ts`
- Create: `web/lib/notifications.ts`
- Modify: `web/lib/api.ts`, `web/lib/hooks.ts`, `web/types/index.ts`

### Testing and Verification

- Create: `tests/platform/test_event_contracts.py`
- Create: `tests/platform/test_stream_hub.py`
- Create: `tests/platform/test_reliability_controls.py`
- Create: `tests/smart_money/test_normalizer.py`
- Create: `tests/smart_money/test_graph_store.py`
- Create: `tests/smart_money/test_profile_service.py`
- Create: `tests/alerts/test_orchestrator.py`
- Create: `tests/alerts/test_delivery_failover.py`
- Create: `tests/api/test_smart_money_routes.py`
- Create: `tests/api/test_alert_routes.py`
- Create: `tests/api/test_alert_rule_routes.py`
- Create: `tests/alerts/test_alert_state_machine.py`
- Create: `tests/api/test_stream_routes.py`
- Create: `tests/api/test_security_controls.py`
- Create: `tests/api/test_rate_limits.py`
- Create: `tests/api/test_audit_logging.py`
- Create: `tests/portfolio/test_multichain_aggregator.py`
- Create: `web/tests/app/app-shell-layout.test.tsx`
- Create: `web/tests/app/smart-money.page.test.tsx`
- Create: `web/tests/app/whales.page.test.tsx`
- Create: `web/tests/app/alerts.page.test.tsx`
- Create: `web/tests/app/rekt.page.test.tsx`
- Create: `web/tests/app/token-rekt-context.test.tsx`
- Create: `web/tests/app/defi-rekt-context.test.tsx`
- Create: `web/tests/app/portfolio-multichain.page.test.tsx`
- Create: `tests/portfolio/test_chain_parity_matrix.py`
- Create: `tests/performance/test_slo_thresholds.py`
- Create: `scripts/perf/run_slo_probe.py`
- Create: `tests/quality/test_feedback_hooks.py`
- Create: `tests/quality/test_replay_evaluator.py`
- Create: `tests/quality/test_adaptive_downweighting_gate.py`

---

### Task 1: Platform Contracts and API Envelope Baseline

**Files:**
- Create: `src/platform/contracts.py`
- Create: `src/api/response_envelope.py`
- Modify: `src/api/schemas/responses.py`
- Modify: `web/types/index.ts`
- Test: `tests/platform/test_event_contracts.py`

- [ ] **Step 1: Write the failing test**

```python
def test_event_contract_contains_trace_and_freshness_fields():
    from src.platform.contracts import EventEnvelope

    event = EventEnvelope(
        event_id="evt-1",
        event_type="analysis.progress",
        trace_id="tr-1",
        occurred_at="2026-03-19T00:00:00Z",
        payload={"stage": "scan"},
    )
    assert event.trace_id == "tr-1"
    assert event.payload["stage"] == "scan"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/platform/test_event_contracts.py::test_event_contract_contains_trace_and_freshness_fields -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.platform.contracts'`

- [ ] **Step 3: Write minimal implementation**

```python
@dataclass
class EventEnvelope:
    event_id: str
    event_type: str
    trace_id: str
    occurred_at: str
    payload: dict
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/platform/test_event_contracts.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/platform/test_event_contracts.py src/platform/contracts.py src/api/response_envelope.py src/api/schemas/responses.py web/types/index.ts
git commit -m "feat: add shared event and envelope contracts"
```

### Task 2: App Shell and Discoverability Navigation

**Files:**
- Create: `web/components/layout/nav-config.ts`
- Create: `web/components/layout/app-shell.tsx`
- Create: `web/components/layout/sidebar.tsx`
- Create: `web/components/layout/mobile-nav.tsx`
- Modify: `web/app/layout.tsx`
- Test: `web/tests/app/app-shell-layout.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
it("renders all top-level navigation groups", async () => {
  render(<AppShell>{<div>content</div>}</AppShell>);
  expect(screen.getByText("Discover")).toBeInTheDocument();
  expect(screen.getByText("Analyze")).toBeInTheDocument();
  expect(screen.getByText("Smart Money")).toBeInTheDocument();
  expect(screen.getByText("Protect")).toBeInTheDocument();
  expect(screen.getByText("Portfolio")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix web run test -- --run web/tests/app/app-shell-layout.test.tsx`
Expected: FAIL with missing `AppShell` component

- [ ] **Step 3: Write minimal implementation**

```tsx
export function AppShell({ children }: { children: React.ReactNode }) {
  return <div className="min-h-screen"><Sidebar />{children}</div>;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix web run test -- --run web/tests/app/app-shell-layout.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/components/layout/nav-config.ts web/components/layout/app-shell.tsx web/components/layout/sidebar.tsx web/components/layout/mobile-nav.tsx web/app/layout.tsx web/tests/app/app-shell-layout.test.tsx
git commit -m "feat: add app shell and discoverability-first navigation"
```

### Task 3: Command Palette and Shared Shell Actions

**Files:**
- Create: `web/components/layout/command-palette.tsx`
- Modify: `web/components/providers.tsx`
- Modify: `web/components/layout/app-shell.tsx`
- Test: `web/tests/app/command-palette.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
it("opens command palette with Ctrl+K", async () => {
  render(<CommandPalette />);
  fireEvent.keyDown(window, { key: "k", ctrlKey: true });
  expect(screen.getByPlaceholderText(/search tokens, wallets, pages/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix web run test -- --run web/tests/app/command-palette.test.tsx`
Expected: FAIL with missing `CommandPalette`

- [ ] **Step 3: Write minimal implementation**

```tsx
useEffect(() => {
  const onKey = (e: KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") setOpen(true);
  };
  window.addEventListener("keydown", onKey);
  return () => window.removeEventListener("keydown", onKey);
}, []);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix web run test -- --run web/tests/app/command-palette.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/components/layout/command-palette.tsx web/components/layout/app-shell.tsx web/components/providers.tsx web/tests/app/command-palette.test.tsx
git commit -m "feat: add global command palette for app navigation"
```

### Task 4: Smart Money Canonical Models and Normalizer

**Files:**
- Create: `src/smart_money/models.py`
- Create: `src/smart_money/normalizer.py`
- Modify: `src/data/solana.py`
- Modify: `src/analytics/behavior_adapters/evm.py`
- Test: `tests/smart_money/test_normalizer.py`

- [ ] **Step 1: Write the failing test**

```python
def test_normalizer_emits_canonical_flow_event_for_solana_swap():
    from src.smart_money.normalizer import normalize_event
    event = normalize_event({"chain": "solana", "type": "swap", "wallet": "abc"})
    assert event.chain == "solana"
    assert event.event_type == "swap"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/smart_money/test_normalizer.py::test_normalizer_emits_canonical_flow_event_for_solana_swap -v`
Expected: FAIL with missing normalizer module

- [ ] **Step 3: Write minimal implementation**

```python
def normalize_event(raw: dict) -> CanonicalFlowEvent:
    return CanonicalFlowEvent(
        chain=raw["chain"],
        event_type=raw["type"],
        wallet=raw["wallet"],
        payload=raw,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/smart_money/test_normalizer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/smart_money/models.py src/smart_money/normalizer.py src/data/solana.py src/analytics/behavior_adapters/evm.py tests/smart_money/test_normalizer.py
git commit -m "feat: add canonical smart money event normalization"
```

### Task 5: Entity Graph Store and Wallet Profile Service

**Files:**
- Create: `src/smart_money/graph_store.py`
- Create: `src/smart_money/profile_service.py`
- Test: `tests/smart_money/test_graph_store.py`
- Test: `tests/smart_money/test_profile_service.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_graph_store_links_wallets_into_entity_cluster():
    store = GraphStore()
    entity_id = store.link_wallets(["w1", "w2"], reason="shared_funding")
    assert entity_id.startswith("entity-")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/smart_money/test_graph_store.py tests/smart_money/test_profile_service.py -v`
Expected: FAIL with missing GraphStore/ProfileService

- [ ] **Step 3: Write minimal implementation**

```python
class GraphStore:
    def link_wallets(self, wallets: list[str], reason: str) -> str:
        entity_id = f"entity-{uuid4().hex[:8]}"
        self.entities[entity_id] = {"wallets": wallets, "reason": reason}
        return entity_id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/smart_money/test_graph_store.py tests/smart_money/test_profile_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/smart_money/graph_store.py src/smart_money/profile_service.py tests/smart_money/test_graph_store.py tests/smart_money/test_profile_service.py
git commit -m "feat: add smart money entity graph and profile service"
```

### Task 6: Replace Wallet Forensics Placeholders

**Files:**
- Modify: `src/analytics/wallet_forensics.py`
- Modify: `src/storage/database.py`
- Test: `tests/analytics/test_wallet_forensics_real_paths.py`

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_forensics_reads_deployments_from_persisted_records():
    engine = WalletForensicsEngine()
    records = await engine._get_token_deployments("wallet-1")
    assert isinstance(records, list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/analytics/test_wallet_forensics_real_paths.py -v`
Expected: FAIL because method still returns placeholder empty set in seeded fixture case

- [ ] **Step 3: Write minimal implementation**

```python
async def _get_token_deployments(self, wallet_address: str) -> list[TokenDeploymentRecord]:
    rows = await load_token_deployments(wallet_address)
    return [
        TokenDeploymentRecord(
            token_address=row.token_address,
            token_symbol=row.token_symbol or "",
            chain=row.chain or "solana",
            deployed_at=row.deployed_at,
            status=row.status,
            peak_liquidity_usd=float(row.peak_liquidity_usd or 0),
            final_liquidity_usd=float(row.final_liquidity_usd or 0),
            liquidity_removal_pct=float(row.liquidity_removal_pct or 0),
            lifespan_hours=float(row.lifespan_hours or 0),
            rugged_at=row.rugged_at,
        )
        for row in rows
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/analytics/test_wallet_forensics_real_paths.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/analytics/wallet_forensics.py src/storage/database.py tests/analytics/test_wallet_forensics_real_paths.py
git commit -m "feat: replace wallet forensics placeholder data paths"
```

### Task 7: Smart Money API Routes

**Files:**
- Create: `src/api/routes/smart_money.py`
- Modify: `src/api/app.py`
- Modify: `src/api/schemas/responses.py`
- Test: `tests/api/test_smart_money_routes.py`

- [ ] **Step 1: Write the failing test**

```python
async def test_smart_money_overview_route_returns_entities(aiohttp_client):
    app = web.Application()
    setup_smart_money_routes(app)
    client = await aiohttp_client(app)
    resp = await client.get("/api/v1/smart-money/overview")
    assert resp.status == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/api/test_smart_money_routes.py::test_smart_money_overview_route_returns_entities -v`
Expected: FAIL with missing route setup

- [ ] **Step 3: Write minimal implementation**

```python
app.router.add_get("/api/v1/smart-money/overview", get_smart_money_overview)
return web.json_response(make_envelope(data={"entities": [], "flows": []}))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/api/test_smart_money_routes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/api/routes/smart_money.py src/api/app.py src/api/schemas/responses.py tests/api/test_smart_money_routes.py
git commit -m "feat: add smart money API surface"
```

### Task 8: Smart Money Frontend Pages

**Files:**
- Create: `web/app/smart-money/page.tsx`
- Create: `web/app/flows/page.tsx`
- Create: `web/app/wallet/[address]/page.tsx`
- Modify: `web/lib/api.ts`
- Modify: `web/lib/hooks.ts`
- Modify: `web/types/index.ts`
- Test: `web/tests/app/smart-money.page.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
it("renders smart money overview cards", async () => {
  render(<SmartMoneyPage />);
  expect(await screen.findByText(/net flow/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix web run test -- --run web/tests/app/smart-money.page.test.tsx`
Expected: FAIL with missing page/component

- [ ] **Step 3: Write minimal implementation**

```tsx
export default function SmartMoneyPage() {
  const { data } = useSmartMoneyOverview();
  return <section><h1>Smart Money</h1><p>Net Flow</p></section>;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix web run test -- --run web/tests/app/smart-money.page.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/app/smart-money/page.tsx web/app/flows/page.tsx web/app/wallet/[address]/page.tsx web/lib/api.ts web/lib/hooks.ts web/types/index.ts web/tests/app/smart-money.page.test.tsx
git commit -m "feat: add smart money web surfaces"
```

### Task 8A: Whales Rebuild and Smart-Money Overlays

**Files:**
- Modify: `web/app/whales/page.tsx`
- Modify: `web/app/token/[address]/page.tsx`
- Modify: `web/app/defi/page.tsx`
- Modify: `web/app/defi/[id]/page.tsx`
- Modify: `web/lib/api.ts`
- Modify: `web/lib/hooks.ts`
- Modify: `web/types/index.ts`
- Test: `web/tests/app/whales.page.test.tsx`
- Test: `web/tests/app/token-smart-money-overlay.test.tsx`
- Test: `web/tests/app/defi-smart-money-overlay.test.tsx`

- [ ] **Step 1: Write the failing tests**

```tsx
it("renders multi-chain whale feed controls", async () => {
  render(<WhalesPage />);
  expect(await screen.findByText(/all chains/i)).toBeInTheDocument();
  expect(await screen.findByText(/entity confidence/i)).toBeInTheDocument();
});

it("renders smart money panel on token detail", async () => {
  render(<TokenAnalysisPage />);
  expect(await screen.findByText(/smart money/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm --prefix web run test -- --run web/tests/app/whales.page.test.tsx web/tests/app/token-smart-money-overlay.test.tsx web/tests/app/defi-smart-money-overlay.test.tsx`
Expected: FAIL because whale page lacks multi-chain panel and overlays are absent

- [ ] **Step 3: Write minimal implementation**

```tsx
<section aria-label="smart-money-overlay">
  <h3>Smart Money</h3>
  <p>Entity confidence: {Math.round((entityConfidence ?? 0) * 100)}%</p>
</section>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm --prefix web run test -- --run web/tests/app/whales.page.test.tsx web/tests/app/token-smart-money-overlay.test.tsx web/tests/app/defi-smart-money-overlay.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/app/whales/page.tsx web/app/token/[address]/page.tsx web/app/defi/page.tsx web/app/defi/[id]/page.tsx web/lib/api.ts web/lib/hooks.ts web/types/index.ts web/tests/app/whales.page.test.tsx web/tests/app/token-smart-money-overlay.test.tsx web/tests/app/defi-smart-money-overlay.test.tsx
git commit -m "feat: rebuild whales feed and add smart-money overlays"
```

### Task 9: Stream Gateway (WebSocket + SSE)

**Files:**
- Create: `src/platform/event_bus.py`
- Create: `src/platform/stream_hub.py`
- Create: `src/api/routes/stream.py`
- Modify: `src/api/app.py`
- Create: `web/lib/realtime.ts`
- Test: `tests/platform/test_stream_hub.py`
- Test: `tests/api/test_stream_routes.py`
- Test: `web/tests/app/realtime-fallback.test.tsx`

- [ ] **Step 1: Write the failing tests**

```python
async def test_ws_client_receives_published_event(aiohttp_client):
    app = web.Application()
    setup_stream_routes(app)
    client = await aiohttp_client(app)

    ws = await client.ws_connect("/api/v1/stream/ws?topic=analysis.progress")
    await publish_test_event("analysis.progress", {"event_type": "analysis.progress", "analysis_id": "a-1"})
    msg = await ws.receive_json()
    received = msg

    assert received["event_type"] == "analysis.progress"


async def test_stream_client_falls_back_to_polling_when_socket_closes(aiohttp_client):
    stream = RealtimeClient(base_url="http://localhost:8080")
    stream._force_socket_failure_for_test = True
    mode = await stream.connect_or_fallback(topic="analysis.progress")
    assert mode == "polling"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/platform/test_stream_hub.py tests/api/test_stream_routes.py -v && npm --prefix web run test -- --run web/tests/app/realtime-fallback.test.tsx`
Expected: FAIL due to missing stream hub/routes/fallback client

- [ ] **Step 3: Write minimal implementation**

```python
class InMemoryEventBus:
    async def publish(self, topic: str, event: dict):
        for subscriber in self.subscribers[topic]:
            await subscriber(event)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/platform/test_stream_hub.py tests/api/test_stream_routes.py -v`
Run: `npm --prefix web run test -- --run web/tests/app/realtime-fallback.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/platform/event_bus.py src/platform/stream_hub.py src/api/routes/stream.py src/api/app.py web/lib/realtime.ts tests/platform/test_stream_hub.py tests/api/test_stream_routes.py web/tests/app/realtime-fallback.test.tsx
git commit -m "feat: add realtime stream gateway for live events"
```

### Task 10: Alerts Orchestrator and API

**Files:**
- Create: `src/alerts/models.py`
- Create: `src/alerts/store.py`
- Create: `src/alerts/orchestrator.py`
- Create: `src/api/routes/alerts.py`
- Modify: `src/storage/database.py`
- Modify: `src/agents/sentinel.py`
- Modify: `src/config.py`
- Test: `tests/alerts/test_orchestrator.py`
- Test: `tests/alerts/test_alert_state_machine.py`
- Test: `tests/api/test_alert_routes.py`
- Test: `tests/api/test_alert_rule_routes.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_orchestrator_dedupes_same_alert_within_window():
    store = InMemoryAlertStore()
    orchestrator = AlertOrchestrator(store=store, dedupe_window_seconds=300)
    event = {
        "user_id": "u-1",
        "rule_id": "r-1",
        "subject_id": "token-1",
        "severity": "high",
        "kind": "whale_dump",
    }
    first = orchestrator.ingest(event)
    second = orchestrator.ingest(event)
    assert first is not None
    assert second is None


def test_alert_state_machine_transitions_in_order():
    alert = AlertRecord(id="a-1", state="new", severity="high", title="Whale dump")
    alert = advance_alert_state(alert, "seen")
    alert = advance_alert_state(alert, "acknowledged")
    assert alert.state == "acknowledged"


async def test_alert_rule_crud_and_severity_filter(aiohttp_client):
    app = web.Application()
    setup_alert_routes(app)
    client = await aiohttp_client(app)

    create_resp = await client.post("/api/v1/alerts/rules", json={"name": "high-only", "severity": ["high", "critical"]})
    assert create_resp.status == 201

    list_resp = await client.get("/api/v1/alerts?severity=high")
    assert list_resp.status == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/alerts/test_orchestrator.py tests/alerts/test_alert_state_machine.py tests/api/test_alert_routes.py tests/api/test_alert_rule_routes.py -v`
Expected: FAIL with missing orchestrator/routes

- [ ] **Step 3: Write minimal implementation**

```python
if self._seen.get(dedupe_key):
    return None
self._seen[dedupe_key] = now
return alert
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/alerts/test_orchestrator.py tests/alerts/test_alert_state_machine.py tests/api/test_alert_routes.py tests/api/test_alert_rule_routes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/alerts/models.py src/alerts/store.py src/alerts/orchestrator.py src/api/routes/alerts.py src/storage/database.py src/agents/sentinel.py src/config.py tests/alerts/test_orchestrator.py tests/alerts/test_alert_state_machine.py tests/api/test_alert_routes.py tests/api/test_alert_rule_routes.py
git commit -m "feat: add alert orchestration and inbox API"
```

### Task 11: Alerts UI and Global Notification Bell

**Files:**
- Create: `web/app/alerts/page.tsx`
- Create: `web/components/layout/alerts-bell.tsx`
- Create: `web/lib/notifications.ts`
- Create: `web/public/alerts-sw.js`
- Modify: `web/components/layout/app-shell.tsx`
- Modify: `web/lib/api.ts`
- Modify: `web/lib/hooks.ts`
- Modify: `web/types/index.ts`
- Test: `web/tests/app/alerts.page.test.tsx`
- Test: `web/tests/app/alerts-deeplink-and-filter.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
it("shows unread alert count in shell bell", async () => {
  render(<AlertsBell unreadCount={3} />);
  expect(screen.getByText("3")).toBeInTheDocument();
});

it("requests browser notification permission when user enables alerts", async () => {
  render(<AlertsPage />);
  fireEvent.click(screen.getByRole("button", { name: /enable browser notifications/i }));
  expect(Notification.requestPermission).toHaveBeenCalled();
});

it("filters alerts by severity and opens deep link action", async () => {
  render(<AlertsPage />);
  fireEvent.click(screen.getByRole("button", { name: /severity: high/i }));
  fireEvent.click(screen.getByRole("link", { name: /view token context/i }));
  expect(mockPush).toHaveBeenCalledWith(expect.stringContaining("/token/"));
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix web run test -- --run web/tests/app/alerts.page.test.tsx web/tests/app/alerts-deeplink-and-filter.test.tsx`
Expected: FAIL with missing AlertsBell/page/notification client

- [ ] **Step 3: Write minimal implementation**

```tsx
export function AlertsBell({ unreadCount }: { unreadCount: number }) {
  return <button aria-label="alerts">{unreadCount}</button>;
}

export async function requestAlertPermission(): Promise<NotificationPermission> {
  if (!("Notification" in window)) return "denied";
  return Notification.requestPermission();
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix web run test -- --run web/tests/app/alerts.page.test.tsx web/tests/app/alerts-deeplink-and-filter.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/app/alerts/page.tsx web/components/layout/alerts-bell.tsx web/lib/notifications.ts web/public/alerts-sw.js web/components/layout/app-shell.tsx web/lib/api.ts web/lib/hooks.ts web/types/index.ts web/tests/app/alerts.page.test.tsx web/tests/app/alerts-deeplink-and-filter.test.tsx
git commit -m "feat: add alerts center and global notification bell"
```

### Task 12: Rekt Product Surface (API + UI)

**Files:**
- Modify: `src/api/routes/intel.py`
- Modify: `src/intel/rekt_database.py`
- Create: `web/app/rekt/page.tsx`
- Create: `web/app/rekt/[id]/page.tsx`
- Modify: `web/app/token/[address]/page.tsx`
- Modify: `web/app/defi/[id]/page.tsx`
- Modify: `web/app/portfolio/page.tsx`
- Modify: `web/lib/api.ts`
- Modify: `web/types/index.ts`
- Test: `tests/api/test_rekt_routes.py`
- Test: `web/tests/app/rekt.page.test.tsx`
- Test: `web/tests/app/token-rekt-context.test.tsx`
- Test: `web/tests/app/defi-rekt-context.test.tsx`
- Test: `web/tests/app/portfolio-rekt-context.test.tsx`

- [ ] **Step 1: Write the failing tests**

```python
async def test_rekt_list_returns_cursor_and_freshness(aiohttp_client):
    app = web.Application()
    setup_intel_routes(app)
    client = await aiohttp_client(app)
    resp = await client.get("/api/v1/intel/rekt?limit=10")
    payload = await resp.json()

    assert "freshness" in payload["meta"]
    assert "cursor" in payload["meta"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_rekt_routes.py -v && npm --prefix web run test -- --run web/tests/app/rekt.page.test.tsx web/tests/app/token-rekt-context.test.tsx web/tests/app/defi-rekt-context.test.tsx web/tests/app/portfolio-rekt-context.test.tsx`
Expected: FAIL due to missing cursor/freshness fields, page routes, and risk-context embeds

- [ ] **Step 3: Write minimal implementation**

```python
return web.json_response(make_envelope(data={"incidents": incidents}, meta={"cursor": next_cursor, "freshness": "warm"}))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/test_rekt_routes.py -v && npm --prefix web run test -- --run web/tests/app/rekt.page.test.tsx web/tests/app/token-rekt-context.test.tsx web/tests/app/defi-rekt-context.test.tsx web/tests/app/portfolio-rekt-context.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/api/routes/intel.py src/intel/rekt_database.py web/app/rekt/page.tsx web/app/rekt/[id]/page.tsx web/app/token/[address]/page.tsx web/app/defi/[id]/page.tsx web/app/portfolio/page.tsx web/lib/api.ts web/types/index.ts tests/api/test_rekt_routes.py web/tests/app/rekt.page.test.tsx web/tests/app/token-rekt-context.test.tsx web/tests/app/defi-rekt-context.test.tsx web/tests/app/portfolio-rekt-context.test.tsx
git commit -m "feat: ship rekt intelligence product pages and contract upgrades"
```

### Task 13: Multi-Chain Portfolio Aggregator Backend

**Files:**
- Create: `src/portfolio/multichain_aggregator.py`
- Modify: `src/api/routes/portfolio.py`
- Modify: `src/data/moralis.py`
- Modify: `src/config.py`
- Test: `tests/portfolio/test_multichain_aggregator.py`
- Test: `tests/portfolio/test_chain_parity_matrix.py`

- [ ] **Step 1: Write the failing test**

```python
def test_aggregator_returns_chain_matrix_with_required_capabilities():
    agg = MultiChainPortfolioAggregator(position_providers=[])
    snapshot = agg.aggregate([])
    required_chains = [
        "solana", "ethereum", "base", "arbitrum", "bsc", "polygon", "optimism", "avalanche"
    ]
    required_capabilities = [
        "spot_holdings", "lp_positions", "lending_positions", "vault_positions", "risk_decomposition", "alert_coverage"
    ]

    for chain in required_chains:
        assert chain in snapshot["chains"]
        for capability in required_capabilities:
            assert capability in snapshot["chains"][chain]


def test_aggregator_marks_degraded_capabilities_explicitly():
    agg = MultiChainPortfolioAggregator(position_providers=[])
    snapshot = agg.aggregate([])
    assert snapshot["degraded"]["reason"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/portfolio/test_multichain_aggregator.py tests/portfolio/test_chain_parity_matrix.py -v`
Expected: FAIL with missing aggregator module

- [ ] **Step 3: Write minimal implementation**

```python
class MultiChainPortfolioAggregator:
    def aggregate(self, positions: list[dict]) -> dict:
        return {"chains": {chain: default_capability_row() for chain in SUPPORTED_CHAINS}}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/portfolio/test_multichain_aggregator.py tests/portfolio/test_chain_parity_matrix.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/portfolio/multichain_aggregator.py src/api/routes/portfolio.py src/data/moralis.py src/config.py tests/portfolio/test_multichain_aggregator.py tests/portfolio/test_chain_parity_matrix.py
git commit -m "feat: add multi-chain portfolio aggregation backend"
```

### Task 14: Multi-Chain Portfolio Frontend

**Files:**
- Modify: `web/app/portfolio/page.tsx`
- Create: `web/components/portfolio/chain-exposure-table.tsx`
- Create: `web/components/portfolio/risk-breakdown.tsx`
- Modify: `web/lib/api.ts`
- Modify: `web/lib/hooks.ts`
- Modify: `web/types/index.ts`
- Test: `web/tests/app/portfolio-multichain.page.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
it("renders exposure rows for all supported chains", async () => {
  render(<PortfolioPage />);
  expect(await screen.findByText(/ethereum/i)).toBeInTheDocument();
  expect(await screen.findByText(/solana/i)).toBeInTheDocument();
});

it("shows explicit degraded status when a chain capability is missing", async () => {
  render(<PortfolioPage />);
  expect(await screen.findByText(/degraded capability/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix web run test -- --run web/tests/app/portfolio-multichain.page.test.tsx`
Expected: FAIL with missing multi-chain section/degraded status indicator

- [ ] **Step 3: Write minimal implementation**

```tsx
{supportedChains.map((chain) => (
  <tr key={chain}><td>{chain}</td><td>{exposureByChain[chain] ?? 0}</td></tr>
))}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix web run test -- --run web/tests/app/portfolio-multichain.page.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/app/portfolio/page.tsx web/components/portfolio/chain-exposure-table.tsx web/components/portfolio/risk-breakdown.tsx web/lib/api.ts web/lib/hooks.ts web/types/index.ts web/tests/app/portfolio-multichain.page.test.tsx
git commit -m "feat: add multi-chain portfolio intelligence UI"
```

### Task 15: Fast Lane + Deep Lane Performance Path

**Files:**
- Create: `src/platform/precompute.py`
- Modify: `src/defi/opportunity_engine.py`
- Modify: `src/storage/cache.py`
- Modify: `src/api/routes/opportunities.py`
- Test: `tests/performance/test_fast_lane_contract.py`

- [ ] **Step 1: Write the failing test**

```python
def test_opportunity_analysis_returns_fast_lane_snapshot_before_deep_completion():
    response = run_fast_lane_analysis_request()
    assert response["status"] in {"scanning", "enriching", "completed"}
    assert "quick_view" in response["data"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/performance/test_fast_lane_contract.py -v`
Expected: FAIL due to missing fast-lane payload fields

- [ ] **Step 3: Write minimal implementation**

```python
return {
    "status": analysis.status,
    "data": {"quick_view": build_quick_view(analysis), "analysis_id": analysis.id},
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/performance/test_fast_lane_contract.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/platform/precompute.py src/defi/opportunity_engine.py src/storage/cache.py src/api/routes/opportunities.py tests/performance/test_fast_lane_contract.py
git commit -m "feat: add fast-lane/deep-lane performance path"
```

### Task 16: API Contract Parity and Observability Lock-In

**Files:**
- Modify: `src/api/routes/analysis.py`
- Modify: `src/api/routes/trending.py`
- Modify: `src/api/routes/portfolio.py`
- Modify: `src/api/routes/transactions.py`
- Modify: `src/api/routes/whale.py`
- Modify: `src/api/routes/stats.py`
- Modify: `src/api/routes/chains.py`
- Modify: `src/api/routes/contracts.py`
- Modify: `src/api/routes/shield.py`
- Modify: `src/api/routes/defi.py`
- Modify: `src/api/routes/intel.py`
- Modify: `src/api/routes/opportunities.py`
- Modify: `src/api/routes/smart_money.py`
- Modify: `src/api/routes/alerts.py`
- Modify: `src/api/routes/stream.py`
- Modify: `src/api/response_envelope.py`
- Create: `tests/api/test_envelope_parity.py`
- Create: `tests/platform/test_slo_metrics.py`
- Create: `tests/performance/test_slo_thresholds.py`
- Create: `scripts/perf/run_slo_probe.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_all_primary_routes_return_standard_envelope_shape():
    payload = call_route("/api/v1/trending")
    assert set(payload.keys()) >= {"status", "data", "meta", "errors", "trace_id", "freshness"}


def test_slo_thresholds_are_enforced_from_probe_output():
    report = {
        "first_meaningful_p95_ms": 4200,
        "deep_analysis_p95_ms": 28500,
        "critical_alert_delivery_p95_ms": 4700,
        "route_transition_p95_ms": 1300,
    }
    assert report["first_meaningful_p95_ms"] < 5000
    assert report["deep_analysis_p95_ms"] < 30000
    assert report["critical_alert_delivery_p95_ms"] < 5000
    assert report["route_transition_p95_ms"] < 1500
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_envelope_parity.py tests/platform/test_slo_metrics.py tests/performance/test_slo_thresholds.py -v`
Expected: FAIL on routes still returning ad-hoc payloads

- [ ] **Step 3: Write minimal implementation**

```python
def make_envelope(data, *, status="ok", meta=None, errors=None, trace_id=None, freshness="live"):
    return {
        "status": status,
        "data": data,
        "meta": meta or {},
        "errors": errors or [],
        "trace_id": trace_id,
        "freshness": freshness,
    }
```

- [ ] **Step 4: Run tests and SLO probe to verify they pass**

Run: `python -m pytest tests/api/test_envelope_parity.py tests/platform/test_slo_metrics.py tests/performance/test_slo_thresholds.py -v`
Run: `python scripts/perf/run_slo_probe.py --window-hours 24 --assert first_meaningful_p95_ms<5000 --assert deep_analysis_p95_ms<30000 --assert critical_alert_delivery_p95_ms<5000 --assert route_transition_p95_ms<1500`
Expected: PASS and printed probe JSON with all thresholds satisfied

- [ ] **Step 5: Commit**

```bash
git add src/api/response_envelope.py src/api/routes/analysis.py src/api/routes/trending.py src/api/routes/portfolio.py src/api/routes/transactions.py src/api/routes/whale.py src/api/routes/stats.py src/api/routes/chains.py src/api/routes/contracts.py src/api/routes/shield.py src/api/routes/defi.py src/api/routes/intel.py src/api/routes/opportunities.py src/api/routes/smart_money.py src/api/routes/alerts.py src/api/routes/stream.py tests/api/test_envelope_parity.py tests/platform/test_slo_metrics.py tests/performance/test_slo_thresholds.py scripts/perf/run_slo_probe.py
git commit -m "chore: standardize API envelopes and enforce SLO instrumentation"
```

### Task 16A: Security Controls for Streams, Alerts, and Webhooks

**Files:**
- Create: `src/api/middleware/webhook_signature.py`
- Create: `src/api/middleware/replay_guard.py`
- Create: `src/alerts/audit_log.py`
- Modify: `src/storage/database.py`
- Modify: `src/api/middleware/rate_limit.py`
- Modify: `src/api/routes/auth.py`
- Modify: `src/api/routes/alerts.py`
- Modify: `src/api/routes/stream.py`
- Modify: `src/config.py`
- Test: `tests/api/test_security_controls.py`
- Test: `tests/api/test_rate_limits.py`
- Test: `tests/api/test_audit_logging.py`

- [ ] **Step 1: Write the failing tests**

```python
async def test_alert_rule_mutation_requires_scoped_auth(aiohttp_client):
    app = web.Application(middlewares=[auth_middleware])
    setup_alert_routes(app)
    client = await aiohttp_client(app)
    resp = await client.post("/api/v1/alerts/rules", json={"name": "high-risk"})
    assert resp.status == 401


async def test_webhook_signature_is_verified_for_outbound_ack(aiohttp_client):
    assert verify_webhook_signature("payload", "sig", "secret") is True


async def test_replay_guard_rejects_duplicate_nonce(aiohttp_client):
    guard = ReplayGuard(ttl_seconds=60)
    first = await guard.accept("user-1", "nonce-1", 1_000_000)
    second = await guard.accept("user-1", "nonce-1", 1_000_001)
    assert first is True
    assert second is False


async def test_replay_guard_rejects_stale_timestamp(aiohttp_client):
    guard = ReplayGuard(ttl_seconds=60, max_skew_seconds=30)
    accepted = await guard.accept("user-1", "nonce-old", 1)
    assert accepted is False


async def test_rate_limit_enforces_scope_burst_cap(aiohttp_client):
    app = web.Application(middlewares=[rate_limit_middleware])
    setup_alert_routes(app)
    client = await aiohttp_client(app)
    statuses = []
    for _ in range(8):
        resp = await client.post("/api/v1/alerts/rules", json={"name": "burst"})
        statuses.append(resp.status)
    assert 429 in statuses
    assert "X-RateLimit-Reset" in resp.headers


async def test_alert_rule_change_writes_audit_record(aiohttp_client):
    app = web.Application()
    setup_alert_routes(app)
    client = await aiohttp_client(app)
    await client.post("/api/v1/alerts/rules", json={"name": "high-only", "severity": ["high"]})
    audit = await fetch_latest_audit_record("alert_rule.create")
    assert audit["actor_id"]
    assert audit["trace_id"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_security_controls.py tests/api/test_rate_limits.py tests/api/test_audit_logging.py -v`
Expected: FAIL because replay protection/audit/rate-limit assertions are not implemented yet

- [ ] **Step 3: Write minimal implementation**

```python
def verify_webhook_signature(payload: str, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


class ReplayGuard:
    async def accept(self, actor_id: str, nonce: str, ts: int) -> bool:
        key = f"replay:{actor_id}:{nonce}"
        if await cache_exists(key):
            return False
        await cache_set(key, ts, ttl=60)
        return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/test_security_controls.py tests/api/test_rate_limits.py tests/api/test_audit_logging.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/api/middleware/webhook_signature.py src/api/middleware/replay_guard.py src/alerts/audit_log.py src/storage/database.py src/api/middleware/rate_limit.py src/api/routes/auth.py src/api/routes/alerts.py src/api/routes/stream.py src/config.py tests/api/test_security_controls.py tests/api/test_rate_limits.py tests/api/test_audit_logging.py
git commit -m "feat: enforce scoped auth, signature verification, and abuse controls"
```

### Task 16B: Reliability Controls (Retries, DLQ, Circuit Breakers, Failover)

**Files:**
- Create: `src/platform/retry.py`
- Create: `src/platform/dead_letter_queue.py`
- Create: `src/platform/circuit_breaker.py`
- Modify: `src/platform/event_bus.py`
- Modify: `src/platform/stream_hub.py`
- Modify: `src/alerts/orchestrator.py`
- Test: `tests/platform/test_reliability_controls.py`
- Test: `tests/alerts/test_delivery_failover.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_retry_stops_after_bounded_attempts():
    attempts = []

    def flaky():
        attempts.append(1)
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        run_with_retry(flaky, max_attempts=3)

    assert len(attempts) == 3


def test_circuit_breaker_opens_after_threshold_failures():
    breaker = CircuitBreaker(failure_threshold=3, recovery_seconds=30)
    for _ in range(3):
        breaker.record_failure()
    assert breaker.state == "open"


def test_alert_delivery_falls_back_to_in_app_and_dlq_on_channel_failure():
    result = deliver_alert_with_failover(alert={"id": "a-1"}, channels=["webhook", "in_app"])
    assert result.primary_channel == "in_app"
    assert result.dlq_written is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/platform/test_reliability_controls.py tests/alerts/test_delivery_failover.py -v`
Expected: FAIL because retry/DLQ/circuit-breaker/failover logic does not exist yet

- [ ] **Step 3: Write minimal implementation**

```python
def run_with_retry(fn, max_attempts: int):
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception:
            if attempt == max_attempts:
                raise


class CircuitBreaker:
    def record_failure(self):
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.state = "open"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/platform/test_reliability_controls.py tests/alerts/test_delivery_failover.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/platform/retry.py src/platform/dead_letter_queue.py src/platform/circuit_breaker.py src/platform/event_bus.py src/platform/stream_hub.py src/alerts/orchestrator.py tests/platform/test_reliability_controls.py tests/alerts/test_delivery_failover.py
git commit -m "feat: add reliability controls for streams and alerts"
```

### Task 16C: Data Quality Feedback, Replay Evaluation, and Gated Adaptive Weights

**Files:**
- Create: `src/quality/feedback_store.py`
- Create: `src/quality/replay_evaluator.py`
- Create: `src/quality/heuristic_weights.py`
- Modify: `src/analytics/behavior_signals.py`
- Modify: `src/defi/scoring/factors/behavior.py`
- Test: `tests/quality/test_feedback_hooks.py`
- Test: `tests/quality/test_replay_evaluator.py`
- Test: `tests/quality/test_adaptive_downweighting_gate.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_feedback_hook_persists_usefulness_vote():
    store = FeedbackStore()
    store.record(signal_code="sell_pressure_buildup", useful=True)
    assert store.count("sell_pressure_buildup") == 1


def test_replay_evaluator_computes_precision_recall_band():
    report = evaluate_replay_window(signal_code="sell_pressure_buildup", days=30)
    assert "precision" in report
    assert "recall" in report


def test_adaptive_downweighting_only_enabled_after_gate():
    gate = AdaptiveWeightGate(min_samples=200, min_precision=0.55)
    assert gate.can_enable(current_samples=50, precision=0.7) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/quality/test_feedback_hooks.py tests/quality/test_replay_evaluator.py tests/quality/test_adaptive_downweighting_gate.py -v`
Expected: FAIL because quality feedback/replay/weight-gate modules are missing

- [ ] **Step 3: Write minimal implementation**

```python
class AdaptiveWeightGate:
    def __init__(self, min_samples: int, min_precision: float):
        self.min_samples = min_samples
        self.min_precision = min_precision

    def can_enable(self, current_samples: int, precision: float) -> bool:
        return current_samples >= self.min_samples and precision >= self.min_precision
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/quality/test_feedback_hooks.py tests/quality/test_replay_evaluator.py tests/quality/test_adaptive_downweighting_gate.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quality/feedback_store.py src/quality/replay_evaluator.py src/quality/heuristic_weights.py src/analytics/behavior_signals.py src/defi/scoring/factors/behavior.py tests/quality/test_feedback_hooks.py tests/quality/test_replay_evaluator.py tests/quality/test_adaptive_downweighting_gate.py
git commit -m "feat: add data-quality feedback and gated adaptive weighting"
```

### Task 17: End-to-End Verification Matrix and Launch Readiness

**Files:**
- Create: `tests/e2e/test_primary_user_journeys.py`
- Create: `web/tests/e2e/platform-overhaul.smoke.test.tsx`

- [ ] **Step 1: Write the failing end-to-end tests**

```python
def test_discover_to_alert_journey_has_no_dead_ends(client):
    assert navigate_discover_to_smart_money_to_alerts(client) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/e2e/test_primary_user_journeys.py -v && npm --prefix web run test -- --run web/tests/e2e/platform-overhaul.smoke.test.tsx`
Expected: FAIL before all pages/routes are integrated

- [ ] **Step 3: Write minimal implementation glue and route fixes**

```python
# Example: ensure route registrations and deep links exist for all critical journeys
setup_smart_money_routes(app)
setup_alert_routes(app)
setup_stream_routes(app)
```

- [ ] **Step 4: Run full verification matrix**

Run:

```bash
python -m pytest tests/platform tests/smart_money tests/alerts tests/portfolio tests/api tests/e2e -q
npm --prefix web run test -- --run tests/
npm --prefix web run type-check
npm --prefix web run build
```

Expected: all commands PASS

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/test_primary_user_journeys.py web/tests/e2e/platform-overhaul.smoke.test.tsx
git commit -m "test: add end-to-end verification matrix for platform overhaul"
```

---

## Dependency and Handoff Notes

- Tasks 1-3 are hard prerequisites for all frontend and contract-dependent backend work.
- Tasks 4-8 and 8A unlock smart money pages, whales rebuild, and API integrations.
- Tasks 9-11 unlock safety-loop UX and live alerts.
- Tasks 12-14 deliver rekt context and multi-chain parity.
- Tasks 15-16A deliver performance hardening, contract parity, and required security controls.
- Tasks 16B-16C deliver resilience controls and phase-6 quality governance requirements.
- Task 17 is the final launch-readiness gate.

## Phase Exit Checkpoints

- Foundation complete: shell discoverability tests green and route IA visible.
- Smart money complete: entity/profile/flow APIs and pages green.
- Alerts complete: orchestrator dedupe and alert inbox flows green.
- Portfolio complete: chain parity matrix exposed in API/UI.
- Performance complete: fast/deep lane and SLO tests green.
- Reliability complete: retry/DLQ/circuit-breaker/failover tests green.
- Quality governance complete: feedback/replay/adaptive-gate tests green.
- Final complete: e2e + type-check + build all green.
