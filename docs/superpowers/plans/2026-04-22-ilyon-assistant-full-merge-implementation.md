# Ilyon Assistant Full Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver one unified Ilyon product that absorbs every assistant feature, UI element, extension surface, memory capability, and affiliate contract path while routing all recommendations and previews through Ilyon Sentinel intelligence.

**Architecture:** Execute the merge as a coordinated nine-track program inside the existing Ilyon repo. Keep `src/` as the only backend runtime, `web/` as the only full web product, `extension/` as the browser companion, and `contracts/` as the monetization track. Port assistant capabilities into these boundaries, then layer Sentinel, Shield, wallet-intel, and DeFi scoring before marking parity complete.

**Tech Stack:** Python 3.13, aiohttp, SQLAlchemy, PostgreSQL, Next.js App Router, React Query, Vitest, Chrome Extension (Vite), BNB Greenfield SDK, Foundry

---

## Scope Check and Decomposition

The approved spec spans multiple independent subsystems. This implementation plan keeps them in one program document because the merge target is one coordinated product, but execution is intentionally decomposed into nine independently testable tracks:

1. agent contracts and wallet context foundations
2. auth and persisted multi-wallet identity
3. assistant runtime, cards, and deterministic execution routing
4. app shell and full assistant chrome absorption
5. chat and swap surface replacement
6. portfolio and market surface merge
7. extension productization
8. Greenfield memory productization
9. affiliate hook operational integration and final parity verification

Each track must be implemented and verified before the next track depends on it.

## Execution Conventions

- Use `superpowers:test-driven-development` for each task.
- Use `superpowers:systematic-debugging` for any failing test, stream regression, wallet-signature bug, or extension build failure.
- Use `superpowers:verification-before-completion` before closing any task.
- Keep implementation scoped to absorbed assistant parity plus Sentinel-driven integration. Do not add unrelated refactors.
- Preserve user changes already present in the worktree. Do not revert unrelated modified files.
- Keep commits small and per-task during execution, even though this planning document is written before code changes begin.

## Resolved Planning Decisions

1. **Backend architecture**
   - Decision: keep one Ilyon aiohttp backend.
   - Implication: assistant FastAPI endpoints are ported, not run as a sidecar.

2. **Assistant repository role**
   - Decision: `IlyonAi-Wallet-assistant-main/` becomes source/reference only after parity.
   - Implication: no runtime path may depend on the assistant folder once merge tracks are complete.

3. **Partial tracks**
   - Decision: popup, sidepanel, Greenfield memory, and affiliate integration are all promoted to real product features.
   - Implication: the merge is not complete if those remain placeholder-level.

4. **Judgment ownership**
   - Decision: Sentinel/Shield/wallet-intel/DeFi engines are the source of truth for judgment-heavy outputs.
   - Implication: assistant-native heuristics can assist formatting, but not overrule Ilyon evidence engines.

## File Structure Map

### Backend Foundations and Contracts

- Create: `src/api/schemas/agent.py` - canonical SSE frames, card payloads, Sentinel/Shield blocks, tool envelope contracts
- Create: `src/agent/context.py` - unified wallet and session context for runtime and deterministic builders
- Create: `src/agent/services/intent_router.py` - fast-path intent normalization and dispatch
- Create: `src/agent/services/portfolio_service.py` - absorbed multi-address portfolio aggregation
- Create: `src/agent/services/market_service.py` - ticker, movers, and overview aggregation using Ilyon data sources
- Modify: `src/api/routes/agent.py` - full conversational entrypoint, session CRUD, and post-message behavior
- Modify: `src/api/routes/auth.py` - unified MetaMask and Phantom verification under one auth surface
- Modify: `src/agent/runtime.py` - full card-aware streaming runtime with assistant parity
- Modify: `src/agent/decorator.py` - richer Sentinel/Shield/wallet-intel enrichment
- Modify: `src/agent/tools/__init__.py` - register absorbed assistant tools under one runtime
- Modify: `src/agent/tools/balance.py`, `price.py`, `swap_simulate.py`, `swap_build.py`, `solana_swap.py`, `bridge_build.py`, `transfer_build.py`, `stake_build.py`, `lp_build.py`, `market_overview.py`, `analytics.py`, `staking.py`, `dex_search.py`, `pool_find.py`
- Modify: `src/storage/chat.py` - richer stored card/tool metadata and session fetch behavior
- Modify: `src/storage/database.py` - multi-wallet identity and memory metadata models
- Create: `migrations/versions/002_agent_wallet_context_and_memory.py` - wallet-context and memory metadata migration

### Web Product Surfaces

- Create: `web/types/agent.ts` - frontend agent/card frame contracts
- Modify: `web/lib/api.ts` - absorbed assistant endpoints, market overview, ticker, chat session, memory, affiliate metadata calls
- Modify: `web/lib/hooks.ts` - merged queries/mutations for chat, ticker, market overview, portfolio, and memory state
- Modify: `web/hooks/useAgentStream.ts` - richer SSE handling and session replay support
- Modify: `web/lib/agent-client.ts` - canonical SSE client for assistant routes
- Modify: `web/components/layout/app-shell.tsx` - assistant-grade shared chrome host
- Modify: `web/components/layout/sidebar.tsx` - richer wallet rail, saved-chat access, system status, market widgets
- Modify: `web/components/layout/header.tsx` - top ticker and quick actions host
- Create: `web/components/layout/ticker-bar.tsx` - real moving-token strip backed by merged data
- Create: `web/components/home/market-overview.tsx` - absorbed market overview section
- Create: `web/components/home/quick-actions.tsx` - assistant quick-action grid
- Modify: `web/app/page.tsx` - absorb assistant intro and launch surface
- Modify: `web/app/agent/chat/page.tsx` - real chat route, no preview banner
- Modify: `web/app/agent/swap/page.tsx` - real swap composer route, no preview banner
- Modify: `web/app/portfolio/page.tsx` - merged multi-wallet portfolio behavior
- Modify: `web/components/agent/ChatShell.tsx`, `Sidebar.tsx`, `MessageList.tsx`, `Composer.tsx`, `ReasoningAccordion.tsx`
- Modify: `web/components/agent/cards/CardRenderer.tsx`
- Create: `web/components/agent/cards/SimulationPreview.tsx`
- Create: `web/components/agent/cards/LiquidityPoolCard.tsx`
- Create: `web/components/agent/cards/UniversalCardList.tsx`

### Extension Product Surfaces

- Modify: `extension/src/background/index.ts` - session propagation, notifications, and handoff orchestration
- Modify: `extension/src/popup/PopupApp.tsx` - quick-access popup with market/ticker/portfolio context
- Modify: `extension/src/sidepanel/SidePanelApp.tsx` - real saved-session sidepanel chat
- Create: `extension/src/lib/storage.ts` - typed extension auth/session storage helpers
- Create: `extension/src/lib/runtime.ts` - extension-to-web/backend handoff helpers
- Create: `extension/src/components/popup/TickerStrip.tsx`
- Create: `extension/src/components/popup/QuickActions.tsx`
- Modify: `extension/package.json` - add extension type-check, test, and build parity scripts

### Greenfield Memory

- Create: `extension/src/services/GreenfieldService.ts` - absorbed assistant Greenfield manager
- Create: `extension/src/services/spUtils.ts` - absorbed storage-provider helpers
- Create: `src/storage/agent_memory.py` - DB helpers for indexed memory metadata
- Create: `src/api/routes/memory.py` - memory state and summary sync endpoints
- Modify: `src/api/app.py` - register memory routes
- Modify: `web/lib/api.ts`, `web/lib/hooks.ts` - memory status/read/write hooks

### Contracts and Affiliate Integration

- Create: `contracts/foundry.toml` - Foundry configuration restored for this repo
- Create: `contracts/remappings.txt` - Pancake/Infinity/OpenZeppelin remappings
- Modify: `contracts/src/AffiliateHook.sol` - final contract home remains canonical
- Modify: `contracts/test/AffiliateHook.t.sol` - behavior tests for fee override and distributor cut
- Modify: `contracts/script/DeployAffiliateHook.s.sol` - deployment flow
- Modify: `src/agent/tools/swap_build.py` - affiliate-aware preview metadata when route is eligible
- Modify: `src/api/schemas/agent.py` - affiliate fields in preview payloads
- Modify: `web/components/agent/cards/SimulationPreview.tsx` - fee and affiliate disclosure rendering

### Testing and Verification

- Create: `tests/agent/test_agent_schemas.py`
- Create: `tests/agent/test_wallet_context.py`
- Create: `tests/agent/test_intent_router.py`
- Create: `tests/agent/test_runtime_streaming.py`
- Create: `tests/agent/test_execution_previews.py`
- Create: `tests/storage/test_agent_wallet_context.py`
- Create: `tests/storage/test_agent_memory_store.py`
- Create: `tests/api/test_agent_routes.py`
- Create: `tests/api/test_agent_auth_routes.py`
- Create: `tests/api/test_market_overview_routes.py`
- Create: `tests/api/test_memory_routes.py`
- Modify: `tests/api/test_agent_stubs.py`
- Modify: `tests/api/test_wallet_intel.py`
- Create: `web/tests/app/home-assistant-merge.page.test.tsx`
- Create: `web/tests/agent/chat-shell.page.test.tsx`
- Create: `web/tests/agent/swap.page.test.tsx`
- Create: `web/tests/agent/portfolio-merge.page.test.tsx`
- Modify: `web/tests/e2e/platform-overhaul.smoke.test.tsx`
- Create: `extension/src/background/index.test.ts`
- Create: `extension/src/popup/PopupApp.test.tsx`
- Create: `extension/src/sidepanel/SidePanelApp.test.tsx`

---

### Task 1: Restore Agent Contracts and Unified Wallet Context

**Files:**
- Create: `src/api/schemas/agent.py`
- Create: `src/agent/context.py`
- Create: `web/types/agent.ts`
- Test: `tests/agent/test_agent_schemas.py`
- Test: `tests/agent/test_wallet_context.py`

- [ ] **Step 1: Write the failing tests**

```python
from src.api.schemas.agent import ToolEnvelope, SentinelBlock
from src.agent.context import AgentWalletContext


def test_tool_envelope_carries_card_and_sentinel_blocks():
    env = ToolEnvelope(
        ok=True,
        message="preview ready",
        card_type="simulation_preview",
        card_payload={"action_type": "swap"},
        sentinel=SentinelBlock(
            safety=92,
            durability=88,
            exit_quality=90,
            confidence=93,
            risk_level="LOW",
            strategy_fit="balanced",
            warnings=[],
        ),
    )
    assert env.card_type == "simulation_preview"
    assert env.sentinel.risk_level == "LOW"


def test_agent_wallet_context_tracks_evm_and_solana_wallets():
    ctx = AgentWalletContext(
        user_id=7,
        evm_addresses=["0x1111111111111111111111111111111111111111"],
        solana_addresses=["So11111111111111111111111111111111111111112"],
        active_chain_id=101,
        signer="phantom",
    )
    assert ctx.primary_evm == "0x1111111111111111111111111111111111111111"
    assert ctx.primary_solana == "So11111111111111111111111111111111111111112"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/agent/test_agent_schemas.py tests/agent/test_wallet_context.py -v`
Expected: FAIL with `ModuleNotFoundError` for `src.api.schemas.agent` and `src.agent.context`

- [ ] **Step 3: Write minimal implementation**

```python
# src/api/schemas/agent.py
from pydantic import BaseModel, Field


class SentinelBlock(BaseModel):
    safety: int
    durability: int
    exit_quality: int
    confidence: int
    risk_level: str
    strategy_fit: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ShieldBlock(BaseModel):
    verdict: str
    warnings: list[str] = Field(default_factory=list)


class ToolEnvelope(BaseModel):
    ok: bool = True
    message: str = ""
    data: dict | None = None
    card_id: str | None = None
    card_type: str | None = None
    card_payload: dict | None = None
    sentinel: SentinelBlock | None = None
    shield: ShieldBlock | None = None
```

```python
# src/agent/context.py
from dataclasses import dataclass, field


@dataclass(slots=True)
class AgentWalletContext:
    user_id: int = 0
    evm_addresses: list[str] = field(default_factory=list)
    solana_addresses: list[str] = field(default_factory=list)
    active_chain_id: int | None = None
    signer: str | None = None

    @property
    def primary_evm(self) -> str | None:
        return self.evm_addresses[0] if self.evm_addresses else None

    @property
    def primary_solana(self) -> str | None:
        return self.solana_addresses[0] if self.solana_addresses else None
```

```ts
// web/types/agent.ts
export interface SentinelBlock {
  safety: number;
  durability: number;
  exit_quality: number;
  confidence: number;
  risk_level: "HIGH" | "MEDIUM" | "LOW";
  strategy_fit?: "conservative" | "balanced" | "aggressive";
  warnings: string[];
}

export interface CardFrame {
  kind: "card";
  card_id: string;
  card_type: string;
  payload: Record<string, unknown>;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/agent/test_agent_schemas.py tests/agent/test_wallet_context.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/api/schemas/agent.py src/agent/context.py web/types/agent.ts tests/agent/test_agent_schemas.py tests/agent/test_wallet_context.py
git commit -m "feat(agent): restore shared agent contracts and wallet context"
```

### Task 2: Unify Auth and Persisted Multi-Wallet Identity

**Files:**
- Create: `migrations/versions/002_agent_wallet_context_and_memory.py`
- Modify: `src/storage/database.py`
- Modify: `src/api/routes/auth.py`
- Test: `tests/storage/test_agent_wallet_context.py`
- Test: `tests/api/test_agent_auth_routes.py`

- [ ] **Step 1: Write the failing tests**

```python
async def test_verify_route_binds_secondary_wallet_context(aiohttp_client, app):
    client = await aiohttp_client(app)
    payload = {
        "wallet_address": "So11111111111111111111111111111111111111112",
        "challenge": "nonce",
        "signature": "ZmFrZQ==",
        "wallet_type": "phantom",
        "linked_evm_wallet": "0x1111111111111111111111111111111111111111",
    }
    resp = await client.post("/api/v1/auth/verify", json=payload)
    assert resp.status == 200
    body = await resp.json()
    assert body["user"]["linked_wallets"]["evm"][0] == "0x1111111111111111111111111111111111111111"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/storage/test_agent_wallet_context.py tests/api/test_agent_auth_routes.py -v`
Expected: FAIL because wallet-context persistence and linked-wallet response fields do not exist

- [ ] **Step 3: Write minimal implementation**

```python
# src/storage/database.py
class WebUserWallet(Base):
    __tablename__ = "web_user_wallets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("web_users.id", ondelete="CASCADE"), nullable=False)
    wallet_address = Column(String(128), nullable=False, index=True)
    wallet_type = Column(String(32), nullable=False)
    is_primary = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
```

```python
# src/api/routes/auth.py
linked_wallets = {
    "evm": evm_wallets,
    "solana": sol_wallets,
}
return web.json_response({
    "token": token,
    "user": {
        "id": user_id,
        "wallet_address": primary_wallet,
        "linked_wallets": linked_wallets,
    },
})
```

```python
# migrations/versions/002_agent_wallet_context_and_memory.py
op.create_table(
    "web_user_wallets",
    sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
    sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("web_users.id", ondelete="CASCADE"), nullable=False),
    sa.Column("wallet_address", sa.String(length=128), nullable=False),
    sa.Column("wallet_type", sa.String(length=32), nullable=False),
    sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/storage/test_agent_wallet_context.py tests/api/test_agent_auth_routes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add migrations/versions/002_agent_wallet_context_and_memory.py src/storage/database.py src/api/routes/auth.py tests/storage/test_agent_wallet_context.py tests/api/test_agent_auth_routes.py
git commit -m "feat(auth): persist multi-wallet identity for agent surfaces"
```

### Task 3: Complete Assistant Runtime, Session CRUD, and Deterministic Intent Routing

**Files:**
- Create: `src/agent/services/intent_router.py`
- Modify: `src/api/routes/agent.py`
- Modify: `src/agent/runtime.py`
- Modify: `src/agent/tools/__init__.py`
- Modify: `src/storage/chat.py`
- Test: `tests/agent/test_intent_router.py`
- Test: `tests/agent/test_runtime_streaming.py`
- Test: `tests/api/test_agent_routes.py`

- [ ] **Step 1: Write the failing tests**

```python
async def test_short_bridge_prompt_takes_deterministic_path():
    from src.agent.services.intent_router import route_intent

    decision = await route_intent("Bridge 0.2 SOL to BNB on BNB chain")
    assert decision.kind == "bridge_build"
    assert decision.fast_path is True


async def test_agent_route_streams_card_and_final_frames(aiohttp_client, app):
    client = await aiohttp_client(app)
    resp = await client.post("/api/v1/agent", json={"session_id": "abc", "message": "Swap 1 SOL to USDC"})
    text = await resp.text()
    assert "event: card" in text
    assert "event: final" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/agent/test_intent_router.py tests/agent/test_runtime_streaming.py tests/api/test_agent_routes.py -v`
Expected: FAIL because `intent_router` does not exist and the route/runtime do not yet guarantee assistant-parity frames

- [ ] **Step 3: Write minimal implementation**

```python
# src/agent/services/intent_router.py
from dataclasses import dataclass


@dataclass(slots=True)
class IntentDecision:
    kind: str
    fast_path: bool


async def route_intent(message: str) -> IntentDecision:
    lowered = message.lower()
    if lowered.startswith("bridge "):
        return IntentDecision(kind="bridge_build", fast_path=True)
    if lowered.startswith("swap "):
        return IntentDecision(kind="swap_build", fast_path=True)
    return IntentDecision(kind="agent_loop", fast_path=False)
```

```python
# src/api/routes/agent.py
decision = await route_intent(message)
if decision.fast_path:
    async for chunk in run_fast_path(...):
        await response.write(chunk)
else:
    async for chunk in run_turn(...):
        await response.write(chunk)
```

```python
# src/agent/runtime.py
collector.emit_card(env.card_id, env.card_type, env.card_payload)
collector.emit_final(final_text, card_ids)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/agent/test_intent_router.py tests/agent/test_runtime_streaming.py tests/api/test_agent_routes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agent/services/intent_router.py src/api/routes/agent.py src/agent/runtime.py src/agent/tools/__init__.py src/storage/chat.py tests/agent/test_intent_router.py tests/agent/test_runtime_streaming.py tests/api/test_agent_routes.py
git commit -m "feat(agent): add deterministic intent routing and full session streaming"
```

### Task 4: Expand Structured Card Contracts and Frontend Rendering

**Files:**
- Modify: `src/api/schemas/agent.py`
- Modify: `src/agent/decorator.py`
- Modify: `web/components/agent/cards/CardRenderer.tsx`
- Create: `web/components/agent/cards/SimulationPreview.tsx`
- Create: `web/components/agent/cards/LiquidityPoolCard.tsx`
- Create: `web/components/agent/cards/UniversalCardList.tsx`
- Test: `tests/agent/test_execution_previews.py`
- Test: `web/tests/agent/chat-shell.page.test.tsx`

- [ ] **Step 1: Write the failing tests**

```python
def test_bridge_preview_payload_contains_affiliate_and_warning_fields():
    from src.api.schemas.agent import SimulationPreviewPayload

    payload = SimulationPreviewPayload(
        action_type="bridge",
        route="deBridge DLN",
        from_token="SOL",
        to_token="BNB",
        warnings=["Phantom may show a temporary source-chain swap"],
        affiliate_fee_label="0.05% distributor cut",
    )
    assert payload.action_type == "bridge"
    assert payload.affiliate_fee_label == "0.05% distributor cut"
```

```tsx
it("renders a simulation preview card with sentinel block", () => {
  render(
    <CardRenderer
      card={{
        kind: "card",
        card_id: "c1",
        card_type: "simulation_preview",
        payload: {
          action_type: "swap",
          from_token: "SOL",
          to_token: "USDC",
          sentinel: { safety: 90, durability: 88, exit_quality: 92, confidence: 95, risk_level: "LOW", warnings: [] },
        },
      }}
    />,
  );
  expect(screen.getByText(/SOL/i)).toBeInTheDocument();
  expect(screen.getByText(/LOW/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/agent/test_execution_previews.py -v && npm --prefix web run test -- --run web/tests/agent/chat-shell.page.test.tsx`
Expected: FAIL because `SimulationPreviewPayload` and `simulation_preview` rendering are not complete

- [ ] **Step 3: Write minimal implementation**

```python
# src/api/schemas/agent.py
class SimulationPreviewPayload(BaseModel):
    action_type: str
    route: str | None = None
    from_token: str
    to_token: str
    warnings: list[str] = Field(default_factory=list)
    affiliate_fee_label: str | None = None
    sentinel: SentinelBlock | None = None
```

```tsx
// web/components/agent/cards/CardRenderer.tsx
case "simulation_preview":
  return <SimulationPreview payload={payload as SimulationPreviewPayload} />;
case "liquidity_pool":
  return <LiquidityPoolCard payload={payload as LiquidityPoolPayload} />;
case "universal_card_list":
  return <UniversalCardList payload={payload as UniversalCardListPayload} />;
```

```tsx
// web/components/agent/cards/SimulationPreview.tsx
export function SimulationPreview({ payload }: { payload: SimulationPreviewPayload }) {
  return <div>{payload.from_token} to {payload.to_token} - {payload.sentinel?.risk_level}</div>;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/agent/test_execution_previews.py -v && npm --prefix web run test -- --run web/tests/agent/chat-shell.page.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/api/schemas/agent.py src/agent/decorator.py web/components/agent/cards/CardRenderer.tsx web/components/agent/cards/SimulationPreview.tsx web/components/agent/cards/LiquidityPoolCard.tsx web/components/agent/cards/UniversalCardList.tsx tests/agent/test_execution_previews.py web/tests/agent/chat-shell.page.test.tsx
git commit -m "feat(agent-ui): add assistant-grade structured card rendering"
```

### Task 5: Absorb Full Assistant Product Chrome Into Ilyon Shell and Home

**Files:**
- Modify: `web/components/layout/app-shell.tsx`
- Modify: `web/components/layout/sidebar.tsx`
- Modify: `web/components/layout/header.tsx`
- Create: `web/components/layout/ticker-bar.tsx`
- Create: `web/components/home/market-overview.tsx`
- Create: `web/components/home/quick-actions.tsx`
- Modify: `web/app/page.tsx`
- Modify: `src/api/routes/tokens_bar.py`
- Modify: `src/agent/services/market_service.py`
- Test: `tests/api/test_market_overview_routes.py`
- Test: `web/tests/app/home-assistant-merge.page.test.tsx`

- [ ] **Step 1: Write the failing tests**

```python
async def test_ticker_route_returns_real_tokens_array(aiohttp_client, app):
    client = await aiohttp_client(app)
    resp = await client.get("/api/v1/tokens/ticker")
    assert resp.status == 200
    body = await resp.json()
    assert len(body["tokens"]) >= 5
    assert "symbol" in body["tokens"][0]
```

```tsx
it("renders assistant chrome inside the Ilyon shell", () => {
  render(<AppShell><div>content</div></AppShell>);
  expect(screen.getByText(/Market/i)).toBeInTheDocument();
  expect(screen.getByText(/AI Agent/i)).toBeInTheDocument();
  expect(screen.getByText(/Portfolio/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_market_overview_routes.py -v && npm --prefix web run test -- --run web/tests/app/home-assistant-merge.page.test.tsx`
Expected: FAIL because the ticker route is placeholder-backed and the shell/home do not yet expose full assistant chrome

- [ ] **Step 3: Write minimal implementation**

```python
# src/agent/services/market_service.py
class MarketService:
    async def ticker(self) -> list[dict]:
        return await fetch_trending_ticker(limit=8)

    async def overview(self) -> dict:
        return {
            "ticker": await self.ticker(),
            "dashboard": await fetch_dashboard_overview(),
            "trending": await fetch_trending_cards(),
        }
```

```python
# src/api/routes/tokens_bar.py
service = request.app["market_service"]
tokens = await service.ticker()
return web.json_response({"tokens": tokens})
```

```tsx
// web/components/layout/ticker-bar.tsx
export function TickerBar({ items }: { items: TickerItem[] }) {
  return <div className="ticker-bar">{items.map((item) => <span key={item.symbol}>{item.symbol}</span>)}</div>;
}
```

```tsx
// web/app/page.tsx
<TickerBar items={tickerItems} />
<MarketOverview data={overview} />
<QuickActions items={quickActions} />
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/test_market_overview_routes.py -v && npm --prefix web run test -- --run web/tests/app/home-assistant-merge.page.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/api/routes/tokens_bar.py src/agent/services/market_service.py web/components/layout/app-shell.tsx web/components/layout/sidebar.tsx web/components/layout/header.tsx web/components/layout/ticker-bar.tsx web/components/home/market-overview.tsx web/components/home/quick-actions.tsx web/app/page.tsx tests/api/test_market_overview_routes.py web/tests/app/home-assistant-merge.page.test.tsx
git commit -m "feat(web): absorb assistant shell chrome and market surfaces"
```

### Task 6: Replace `/agent/chat` and `/agent/swap` Preview Pages With Real Flows

**Files:**
- Modify: `web/app/agent/chat/page.tsx`
- Modify: `web/app/agent/swap/page.tsx`
- Modify: `web/components/agent/ChatShell.tsx`
- Modify: `web/components/agent/Sidebar.tsx`
- Modify: `web/components/agent/Composer.tsx`
- Modify: `web/hooks/useAgentStream.ts`
- Modify: `web/lib/api.ts`
- Test: `web/tests/agent/chat-shell.page.test.tsx`
- Test: `web/tests/agent/swap.page.test.tsx`

- [ ] **Step 1: Write the failing tests**

```tsx
it("loads saved sessions in the agent chat rail", async () => {
  render(<AgentChatPage />);
  expect(await screen.findByText(/New Chat/i)).toBeInTheDocument();
  expect(await screen.findByPlaceholderText(/Type your request/i)).toBeInTheDocument();
});

it("hands swap form state into chat as a structured prompt", async () => {
  render(<AgentSwapPage />);
  fireEvent.change(screen.getByLabelText(/You pay/i), { target: { value: "0.5" } });
  fireEvent.click(screen.getByRole("button", { name: /Continue in Agent Chat/i }));
  expect(mockPush).toHaveBeenCalledWith(expect.stringContaining("/agent/chat"));
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm --prefix web run test -- --run web/tests/agent/chat-shell.page.test.tsx web/tests/agent/swap.page.test.tsx`
Expected: FAIL because both routes are still preview pages

- [ ] **Step 3: Write minimal implementation**

```tsx
// web/app/agent/chat/page.tsx
export default function AgentChatPage() {
  return <ChatShell token={null} />;
}
```

```tsx
// web/app/agent/swap/page.tsx
const prompt = `Swap ${amount} ${fromSymbol} to ${toSymbol}`;
router.push(`/agent/chat?prompt=${encodeURIComponent(prompt)}`);
```

```tsx
// web/components/agent/ChatShell.tsx
const { sessions, createSession, deleteSession } = useAgentSessions(token);
<Sidebar sessions={sessions} onNew={createSession} onDelete={deleteSession} />
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm --prefix web run test -- --run web/tests/agent/chat-shell.page.test.tsx web/tests/agent/swap.page.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/app/agent/chat/page.tsx web/app/agent/swap/page.tsx web/components/agent/ChatShell.tsx web/components/agent/Sidebar.tsx web/components/agent/Composer.tsx web/hooks/useAgentStream.ts web/lib/api.ts web/tests/agent/chat-shell.page.test.tsx web/tests/agent/swap.page.test.tsx
git commit -m "feat(agent-web): replace preview routes with live chat and swap flows"
```

### Task 7: Merge Portfolio and Assistant Market Utility Surfaces

**Files:**
- Modify: `src/agent/services/portfolio_service.py`
- Modify: `src/api/routes/portfolio.py`
- Modify: `web/app/portfolio/page.tsx`
- Modify: `web/lib/hooks.ts`
- Test: `tests/api/test_market_overview_routes.py`
- Test: `web/tests/agent/portfolio-merge.page.test.tsx`

- [ ] **Step 1: Write the failing tests**

```python
async def test_portfolio_route_accepts_comma_separated_wallets(aiohttp_client, app):
    client = await aiohttp_client(app)
    resp = await client.get("/api/v1/portfolio?wallets=So11111111111111111111111111111111111111112,0x1111111111111111111111111111111111111111")
    assert resp.status == 200
    body = await resp.json()
    assert body["summary"]["wallet_count"] == 2
```

```tsx
it("shows merged wallet holdings and health framing", async () => {
  render(<PortfolioPage />);
  expect(await screen.findByText(/Total Value/i)).toBeInTheDocument();
  expect(await screen.findByText(/Health Score/i)).toBeInTheDocument();
  expect(await screen.findByText(/Track Another Wallet/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_market_overview_routes.py -v && npm --prefix web run test -- --run web/tests/agent/portfolio-merge.page.test.tsx`
Expected: FAIL because portfolio aggregation does not yet expose merged assistant semantics

- [ ] **Step 3: Write minimal implementation**

```python
# src/agent/services/portfolio_service.py
class PortfolioService:
    async def aggregate(self, wallets: list[str]) -> dict:
        positions = await scan_wallets(wallets)
        return {
            "summary": {"wallet_count": len(wallets), "total_value_usd": sum(p["value_usd"] for p in positions)},
            "positions": positions,
        }
```

```tsx
// web/app/portfolio/page.tsx
const { data } = useMergedPortfolio(connectedWallets);
<GlassCard><h3>Total Value</h3></GlassCard>
<GlassCard><h3>Health Score</h3></GlassCard>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/test_market_overview_routes.py -v && npm --prefix web run test -- --run web/tests/agent/portfolio-merge.page.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agent/services/portfolio_service.py src/api/routes/portfolio.py web/app/portfolio/page.tsx web/lib/hooks.ts tests/api/test_market_overview_routes.py web/tests/agent/portfolio-merge.page.test.tsx
git commit -m "feat(portfolio): merge assistant multi-wallet utility into Ilyon portfolio"
```

### Task 8: Productize Popup, Sidepanel, and Background Worker

**Files:**
- Modify: `extension/src/background/index.ts`
- Modify: `extension/src/popup/PopupApp.tsx`
- Modify: `extension/src/sidepanel/SidePanelApp.tsx`
- Create: `extension/src/lib/storage.ts`
- Create: `extension/src/lib/runtime.ts`
- Create: `extension/src/components/popup/TickerStrip.tsx`
- Create: `extension/src/components/popup/QuickActions.tsx`
- Test: `extension/src/background/index.test.ts`
- Test: `extension/src/popup/PopupApp.test.tsx`
- Test: `extension/src/sidepanel/SidePanelApp.test.tsx`

- [ ] **Step 1: Write the failing tests**

```ts
it("stores and clears the shared auth token", async () => {
  await setToken("jwt-1");
  expect(await getToken()).toBe("jwt-1");
  await clearToken();
  expect(await getToken()).toBeNull();
});
```

```tsx
it("shows quick actions and ticker in the popup", async () => {
  render(<PopupApp />);
  expect(await screen.findByText(/Market/i)).toBeInTheDocument();
  expect(await screen.findByText(/Swap/i)).toBeInTheDocument();
});
```

```json
{
  "scripts": {
    "test": "vitest run --environment jsdom"
  }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm --prefix extension run test -- --run src/popup/PopupApp.test.tsx src/sidepanel/SidePanelApp.test.tsx src/background/index.test.ts`
Expected: FAIL because popup and sidepanel are still thin wrappers

- [ ] **Step 3: Write minimal implementation**

```ts
// extension/src/lib/storage.ts
export async function getToken(): Promise<string | null> {
  const result = await chrome.storage.local.get("ilyon_token");
  return result.ilyon_token ?? null;
}

export async function setToken(token: string): Promise<void> {
  await chrome.storage.local.set({ ilyon_token: token });
}
```

```tsx
// extension/src/popup/PopupApp.tsx
return (
  <div>
    <TickerStrip items={tickerItems} />
    <QuickActions onSelect={openSidepanelPrompt} />
    <CompactPortfolioSummary token={token} />
  </div>
);
```

```ts
// extension/src/background/index.ts
if (msg.type === "OPEN_AGENT_WITH_PROMPT") {
  await chrome.sidePanel.open({ windowId: sender.tab?.windowId });
  await chrome.storage.local.set({ pending_prompt: msg.prompt });
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm --prefix extension run build`
Expected: PASS

Run: `npm --prefix extension run test -- --run src/popup/PopupApp.test.tsx src/sidepanel/SidePanelApp.test.tsx src/background/index.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add extension/src/background/index.ts extension/src/popup/PopupApp.tsx extension/src/sidepanel/SidePanelApp.tsx extension/src/lib/storage.ts extension/src/lib/runtime.ts extension/src/components/popup/TickerStrip.tsx extension/src/components/popup/QuickActions.tsx extension/src/background/index.test.ts extension/src/popup/PopupApp.test.tsx extension/src/sidepanel/SidePanelApp.test.tsx
git commit -m "feat(extension): productize popup and sidepanel assistant surfaces"
```

### Task 9: Productize Greenfield Memory Across Extension and Web

**Files:**
- Create: `extension/src/services/GreenfieldService.ts`
- Create: `extension/src/services/spUtils.ts`
- Create: `src/storage/agent_memory.py`
- Create: `src/api/routes/memory.py`
- Modify: `src/api/app.py`
- Modify: `web/lib/api.ts`
- Modify: `web/lib/hooks.ts`
- Test: `tests/storage/test_agent_memory_store.py`
- Test: `tests/api/test_memory_routes.py`

- [ ] **Step 1: Write the failing tests**

```python
async def test_memory_route_lists_latest_memory_objects(aiohttp_client, app):
    client = await aiohttp_client(app)
    resp = await client.get("/api/v1/memory")
    assert resp.status == 200
    body = await resp.json()
    assert "objects" in body
```

```python
def test_agent_memory_store_tracks_greenfield_object_name(session):
    from src.storage.agent_memory import save_memory_record

    record = save_memory_record(session, user_id=7, object_name="memory/agent-memory-1.json", provider="greenfield")
    assert record.object_name == "memory/agent-memory-1.json"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/storage/test_agent_memory_store.py tests/api/test_memory_routes.py -v`
Expected: FAIL because memory storage and routes do not exist

- [ ] **Step 3: Write minimal implementation**

```python
# src/storage/agent_memory.py
def save_memory_record(session, *, user_id: int, object_name: str, provider: str):
    record = AgentMemoryRecord(user_id=user_id, object_name=object_name, provider=provider)
    session.add(record)
    return record
```

```python
# src/api/routes/memory.py
async def list_memory(request: web.Request) -> web.Response:
    objects = await get_memory_records_for_user(request.get("user_id", 0))
    return web.json_response({"objects": objects})
```

```ts
// web/lib/hooks.ts
export function useMemoryStatus() {
  return useQuery({ queryKey: ["memory-status"], queryFn: () => api.getMemoryStatus() });
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/storage/test_agent_memory_store.py tests/api/test_memory_routes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add extension/src/services/GreenfieldService.ts extension/src/services/spUtils.ts src/storage/agent_memory.py src/api/routes/memory.py src/api/app.py web/lib/api.ts web/lib/hooks.ts tests/storage/test_agent_memory_store.py tests/api/test_memory_routes.py
git commit -m "feat(memory): productize Greenfield-backed assistant memory"
```

### Task 10: Integrate Affiliate Hook Into Contracts, Previews, and Analytics

**Files:**
- Create: `contracts/foundry.toml`
- Create: `contracts/remappings.txt`
- Modify: `contracts/src/AffiliateHook.sol`
- Modify: `contracts/test/AffiliateHook.t.sol`
- Modify: `contracts/script/DeployAffiliateHook.s.sol`
- Modify: `src/agent/tools/swap_build.py`
- Modify: `src/api/schemas/agent.py`
- Modify: `web/components/agent/cards/SimulationPreview.tsx`
- Test: `tests/agent/test_execution_previews.py`
- Test: `contracts/test/AffiliateHook.t.sol`

- [ ] **Step 1: Write the failing tests**

```solidity
function testAffiliateSwapOverridesFeeAndAccruesDistributorCut() public {
    bytes memory hookData = abi.encode(true);
    ICLPoolManager.SwapParams memory params = ICLPoolManager.SwapParams({
        zeroForOne: true,
        amountSpecified: 1_000_000e18,
        sqrtPriceLimitX96: 0
    });
    (, , uint24 feeOverride) = hook.exposedBeforeSwap(address(this), key, params, hookData);
    uint256 expectedCut = (1_000_000e18 * hook.DISTRIBUTOR_FEE()) / 1_000_000;
    assertEq(feeOverride, LPFeeLibrary.OVERRIDE_FEE_FLAG | hook.AFFILIATE_LP_FEE());
    assertEq(hook.pendingFees(currency0), expectedCut);
}
```

```python
def test_swap_preview_exposes_affiliate_fee_label():
    preview = build_preview({"affiliate_fee_percent": 0.05, "route": "PancakeSwap Infinity"})
    assert preview["affiliate_fee_label"] == "0.05% affiliate fee"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `forge test --root contracts`
Expected: FAIL if Foundry config/remappings are missing or hook behavior is incomplete

Run: `python -m pytest tests/agent/test_execution_previews.py -v`
Expected: FAIL because affiliate fee labeling is not yet wired into preview payloads

- [ ] **Step 3: Write minimal implementation**

```toml
# contracts/foundry.toml
[profile.default]
src = "src"
test = "test"
script = "script"
solc_version = "0.8.26"
libs = ["lib"]
```

```python
# src/agent/tools/swap_build.py
if route.get("affiliate_fee_percent"):
    card_payload["affiliate_fee_label"] = f"{route['affiliate_fee_percent']}% affiliate fee"
```

```tsx
// web/components/agent/cards/SimulationPreview.tsx
{payload.affiliate_fee_label && (
  <div className="text-xs text-amber-300">{payload.affiliate_fee_label}</div>
)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `forge test --root contracts`
Expected: PASS

Run: `python -m pytest tests/agent/test_execution_previews.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add contracts/foundry.toml contracts/remappings.txt contracts/src/AffiliateHook.sol contracts/test/AffiliateHook.t.sol contracts/script/DeployAffiliateHook.s.sol src/agent/tools/swap_build.py src/api/schemas/agent.py web/components/agent/cards/SimulationPreview.tsx tests/agent/test_execution_previews.py
git commit -m "feat(affiliate): wire affiliate hook disclosures into execution previews"
```

### Task 11: End-to-End Parity Verification and Reference Freeze

**Files:**
- Modify: `web/tests/e2e/platform-overhaul.smoke.test.tsx`
- Modify: `tests/e2e/test_primary_user_journeys.py`
- Modify: `extension/manifest.json`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/ai-agent-integration.md`

- [ ] **Step 1: Write the failing tests**

```python
async def test_agent_merge_journey_has_no_dead_ends(client):
    chat = await client.get("/api/v1/agent/sessions")
    ticker = await client.get("/api/v1/tokens/ticker")
    memory = await client.get("/api/v1/memory")
    assert chat.status == 200
    assert ticker.status == 200
    assert memory.status == 200
```

```tsx
it("keeps Discover, Agent Chat, Agent Swap, and Portfolio navigable", () => {
  render(<AppShell><div>content</div></AppShell>);
  expectLinkPath("Discover", "/");
  expectLinkPath("Chat", "/agent/chat");
  expectLinkPath("Swap", "/agent/swap");
  expectLinkPath("Portfolio", "/portfolio");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/e2e/test_primary_user_journeys.py -v && npm --prefix web run test -- --run web/tests/e2e/platform-overhaul.smoke.test.tsx`
Expected: FAIL until all merged routes and shell-level destinations are live

- [ ] **Step 3: Write minimal implementation**

```python
# tests/e2e/test_primary_user_journeys.py target state
assert workflows.get("agent") == [
    "POST /api/v1/agent",
    "GET /api/v1/agent/sessions",
    "GET /api/v1/memory",
]
```

```md
# docs/ARCHITECTURE.md
- `web/` is the only full product UI.
- `extension/` is the browser companion surface.
- `IlyonAi-Wallet-assistant-main/` is reference-only after merge parity.
```

- [ ] **Step 4: Run full verification to verify it passes**

Run: `python -m pytest tests/agent tests/api tests/storage tests/e2e -v`
Expected: PASS

Run: `npm --prefix web run test -- --run web/tests/app web/tests/agent web/tests/e2e/platform-overhaul.smoke.test.tsx`
Expected: PASS

Run: `npm --prefix web run type-check && npm --prefix web run build`
Expected: PASS

Run: `npm --prefix extension run build`
Expected: PASS

Run: `forge test --root contracts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/tests/e2e/platform-overhaul.smoke.test.tsx tests/e2e/test_primary_user_journeys.py extension/manifest.json docs/ARCHITECTURE.md docs/ai-agent-integration.md
git commit -m "chore: finalize assistant merge parity and docs"
```

## Plan Self-Review Notes

- Spec coverage: all approved domains are covered by a task track: backend unification, web chrome absorption, chat/swap/portfolio merge, extension productization, Greenfield memory, affiliate integration, and final parity verification.
- Placeholder scan: completed. Each task names exact files, tests, commands, and representative code instead of soft directives.
- Type consistency: the plan consistently uses `ToolEnvelope`, `SentinelBlock`, `AgentWalletContext`, `SimulationPreview`, and `web_user_wallets` as the shared nouns across backend and frontend tasks.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-22-ilyon-assistant-full-merge-implementation.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
