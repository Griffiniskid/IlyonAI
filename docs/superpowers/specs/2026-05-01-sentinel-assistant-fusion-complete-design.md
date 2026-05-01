# Sentinel ⇄ Assistant Fusion — Complete Design Spec

**Date:** 2026-05-01
**Status:** Approved
**Supersedes:** `docs/superpowers/specs/2026-04-29-sentinel-assistant-fusion-design.md`
**Reversibility checkpoint:** `pre-fusion-rewrite-20260501` at commit `1fbbff5`
**Rollback:** `git reset --hard pre-fusion-rewrite-20260501`

## 0. Why this spec exists

The 2026-04-29 spec described the right architecture but the implementation
plan that followed it shipped only a foundation slice. As of `1fbbff5` we have:

- `src/scoring/*` (rubric, normalizer, shield gate, pool/route/bridge scorers)
- `src/agent/planner.py` and `src/agent/step_executor.py` (in-memory only)
- `src/agent/tools/sentinel_wrap.py` with `enrich_tool_envelope`
- `src/api/schemas/agent.py` extended with `ExecutionPlanV2Payload`,
  `PlanStepV2`, `SentinelBlock`, `ShieldBlock`, status / complete frames
- Frontend `SentinelBadge`, `ShieldBadge`, `StepStatusCard`, `useExecutionPlan`
- `simple_runtime.py` regex fast-paths for ~5 multi-step shapes

But none of that is reachable from real users today, because:

1. **Routing dead-end.** `web/app/api/v1/agent/route.ts` is hardcoded to
   `ASSISTANT_API_TARGET` (port 8000, wallet assistant). The `AGENT_BACKEND`
   switch in `next.config.js` is unused by this proxy. The Sentinel SSE
   endpoint at `:8080/api/v1/agent` is therefore never invoked from the only
   user-facing chat surface (`MainApp` at `/agent/*`).
2. **Wallet wrappers are stubs.** `src/agent/tools/{swap_build,bridge_build,
   stake_build,lp_build,transfer_build}.py` return `{"unsigned_tx": {}}` and
   never import the real builders from
   `IlyonAi-Wallet-assistant-main/server/app/agents/crypto_agent.py`.
3. **Multi-step coverage is narrow.** Five hand-written regex shapes catch
   bridge→stake, swap→LP, stake-idle, transfer, malicious-swap. Anything else
   (`swap then bridge`, `claim then swap then stake`, `consolidate dust`,
   `rebalance my portfolio`, conditional intents) falls through to the
   single-tool runtime which cannot compose plans.
4. **Plan execution is in-memory only.** `step_executor.py` has no SQLite
   persistence, no real receipt polling, no resume-on-reload. Step state
   transitions are unobserved.
5. **No optimizer.** `src/optimizer/*` files exist but no daemon runs and no
   chat tool maps to it.
6. **Demo surface unmounted.** `web/components/agent/DemoChatFrame.tsx`
   exists but no page imports it. The "demo from main" the user references
   is dormant.

This spec describes the complete fusion: how every chat — landing demo or
authenticated `/agent/*` — receives Sentinel-scored recommendations, how
multi-step intents decompose into validated plans with real signing payloads,
how plans execute step-by-step with receipt watching, and how an opt-in
optimizer daemon proposes (never executes) cross-chain rebalances.

## 1. Goal

Fuse the two systems so that:

- The Next.js chat surface uses the Sentinel agent as the brain (default
  `AGENT_BACKEND=sentinel`).
- Every recommendation (yield, pool, staking, swap, bridge, transfer, LP,
  Solana swap) carries a four-dimension Sentinel envelope and a Shield
  verdict — same scoring as the demo `allocate_plan` flow.
- Multi-step intents like
  `"bridge 1000 USDC from Ethereum to Arbitrum and stake it on Aave"`,
  `"swap 0.5 ETH to USDC then provide liquidity to USDC/USDT on Curve"`,
  `"claim my Pendle yield, swap to USDC, stake on Lido"`, or
  `"rebalance my portfolio to maximize APY"` decompose into a validated
  step DAG, score end-to-end, execute step-by-step with on-chain receipt
  watching, and resume after a tab reload.
- An opt-in cross-chain rebalance daemon proposes (never signs) plans that
  share 100 % of the planner code path with the manual chat command.
- The wallet assistant codebase is **never modified** — additive only,
  enforced by CI. The assistant is treated as an importable Python library.

## 2. Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Browser                                                                  │
│  ┌─ /agent/* (MainApp) ──┐  ┌─ / (DemoChatFrame mount) ─────────────────┐ │
│  │ chat + cards          │  │ same hooks, same SSE frames                │ │
│  └─────────┬─────────────┘  └─────────┬───────────────────────────────-─┘ │
│            └────── useAgentStream ────┘                                   │
└───────────────────────────┬──────────────────────────────────────────────┘
                            │ POST /api/v1/agent (SSE)
                            ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Next.js   web/app/api/v1/agent/route.ts                                  │
│  reads process.env.AGENT_BACKEND                                          │
│   sentinel  → http://sentinel:8080  (default after Phase 1)               │
│   wallet    → http://wallet:8000    (rollback path)                       │
└───────────────────────────┬──────────────────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ src/api/routes/agent.py  (port 8080, aiohttp SSE)                         │
│   ↓                                                                       │
│ src/agent/simple_runtime.py  (regex fast-paths kept for low-latency wins) │
│   ↓ on miss → src/agent/runtime.py (ReAct, LLM-driven)                    │
│   ↓                                                                       │
│ Tools (registered in src/agent/tools/__init__.py):                        │
│  • compose_plan      NEW: LLM emits plan DAG → planner.build_plan        │
│  • update_preference NEW: persists agent_preferences row                  │
│  • rebalance_portfolio NEW Phase 3: snapshot→target→delta→plan_synth      │
│  • Wallet wrappers (NEW, in-process Python imports — see §5):             │
│      wallet_swap, wallet_bridge, wallet_stake, wallet_lp,                 │
│      wallet_transfer, wallet_solana_swap, wallet_balance                  │
│  • Existing tools kept unchanged: allocate_plan, staking, analytics,      │
│    market_overview, dex_search, pool_find, price                          │
│  • Every tool result post-processed by enrich_tool_envelope               │
│    → adds .sentinel and .shield sidecars                                  │
│   ↓                                                                       │
│ src/agent/planner.py        builds ExecutionPlanV2Payload                 │
│ src/agent/step_executor.py  drives state machine, persists to SQLite      │
│ src/agent/receipt_watcher.py polls EVM/Solana/deBridge via rpc-proxy      │
│   ↓ emits SSE: execution_plan_v2 · step_status · plan_complete ·          │
│                plan_blocked · sentinel · shield                           │
└───────────────────────────┬──────────────────────────────────────────────┘
                            │ in-process import (read-only library use)
                            ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ IlyonAi-Wallet-assistant-main/   FROZEN, CI-guarded                       │
│   server/app/agents/crypto_agent.py   (treated as a library)              │
│     _build_swap_tx, _build_bridge_tx, _build_stake_tx,                    │
│     _build_deposit_lp_tx, _build_transfer_transaction,                    │
│     build_solana_swap, get_smart_wallet_balance,                          │
│     _resolve_token_metadata, get_staking_options                          │
└──────────────────────────────────────────────────────────────────────────┘

┌─ src/optimizer/  (Phase 3 — additive, off by default) ───────────────────┐
│   daemon.py       APScheduler · 6 h snapshot · 24 h propose                │
│   snapshot.py     calls get_smart_wallet_balance + portfolio.normalizer    │
│   target_builder  reuses allocate_plan path                                │
│   delta.py        +2 % APY · ≥0 sentinel · 4× gas breakeven                │
│   plan_synth.py   feeds planner.build_plan (same code path as chat)        │
│   safety.py       7 d cooldown · 1/day cap · 48 h plan TTL · kill-switch   │
│   notifier.py     SSE push or email fallback                               │
└──────────────────────────────────────────────────────────────────────────┘
```

**Key invariants**

1. **Single chat path.** Every user message hits the same Next.js proxy
   route, which routes via `AGENT_BACKEND` to one backend. There is no
   parallel chat path.
2. **Wallet assistant is a library.** No HTTP hop in the new flow; wrappers
   import builder functions directly. The assistant tree is never edited.
3. **Every tool envelope carries Sentinel + Shield sidecars** — true today
   for `get_defi_analytics`, `get_staking_options`, `find_liquidity_pool`;
   extended to swap / bridge / stake / lp / transfer / solana-swap in
   Phase 1.
4. **Multi-step is plan-first.** LLM emits a JSON DAG via `compose_plan`;
   planner validates and normalises (topological sort, approve injection,
   wait_receipt injection); executor signs step-by-step with receipt
   watching. Never `return_direct=True` semantics.
5. **Same code paths for daemon and chat.** "Rebalance my portfolio" in chat
   and the 04:00 UTC daemon both call
   `target_builder → delta → plan_synth → planner → step_executor`.

## 3. Sentinel rubric (unchanged from demo)

Per pool, 0–100 in four dimensions:

- **Safety** = audit + TVL tier + single-asset exposure + no-IL
- **Durability** = days-live tenure + sane APY + stablecoin
- **Exit** = TVL tier + stablecoin denom + single exposure
- **Confidence** = audit + tenure (≥720 d / ≥365 d / ≥180 d)

**Weighted blend:**
`sentinel = 0.40·safety + 0.25·durability + 0.20·exit + 0.15·confidence`

**Risk bucket:** `≥82 → low`, `≥65 → medium`, else `high`.

The canonical implementation is in `src/allocator/composer.py`; `src/scoring/
rubric.py` re-exports without behaviour change. `src/scoring/normalizer.py`
maps DefiLlama / DexScreener / wallet-assistant dicts into `PoolCandidate`.

## 4. Schemas

Already present in `src/api/schemas/agent.py`:

- `SentinelBlock` (sentinel/safety/durability/exit/confidence/risk_level/
  strategy_fit/flags)
- `ShieldBlock` (verdict/grade/reasons)
- `PlanStepV2` (step_id, order, action, params, depends_on, resolves_from,
  sentinel, shield_flags, gas/duration estimates, status, tx_hash, receipt,
  error)
- `ExecutionPlanV2Payload` (plan_id, title, steps, totals, blended_sentinel,
  requires_signature_count, risk_warnings, risk_gate, requires_double_confirm,
  chains_touched, user_assets_required)
- `StepStatusFrame`, `PlanCompleteFrame`
- Sidecar `sentinel` / `shield` / `scoring_inputs` on `ToolEnvelope`

**Added in Phase 0:**

```python
class PlanBlockedFrame(_Strict):
    """Emitted when risk_gate == 'hard_block' on a freshly composed plan."""
    plan_id: str
    reasons: list[str]
    severity: Literal["critical"]
```

## 5. Wallet wrapper boundary (decision: direct Python import)

Each wrapper imports the corresponding builder lazily (inside the function
body, never at module top), parses its return JSON, normalises into a
`ToolEnvelope`, and applies `@sentinel_decorator` so Phase 1's universal
scoring kicks in.

```python
# src/agent/tools/wallet_swap.py  (illustrative)
async def build_swap_tx(ctx, *, chain_id, token_in, token_out, amount_in,
                        from_addr):
    from IlyonAi_Wallet_assistant_main.server.app.agents.crypto_agent import (
        _build_swap_tx,
    )
    raw = _build_swap_tx(
        f"{amount_in} {token_in} to {token_out}",
        user_address=from_addr,
        chain_id=chain_id,
    )
    parsed = _parse_assistant_json(raw)  # local helper handles errors
    return ok_envelope(
        data=parsed,
        card_type="swap_quote",
        card_payload={
            "pay": parsed.get("pay", {}),
            "receive": parsed.get("receive", {}),
            "rate": parsed.get("rate"),
            "router": parsed.get("router"),
            "price_impact_pct": parsed.get("price_impact_pct"),
        },
    )
```

Real assistant function names verified at `1fbbff5`:

| Wrapper | Imports |
|---|---|
| `wallet_swap.py`         | `_build_swap_tx`              (line 1804) |
| `wallet_bridge.py`       | `_build_bridge_tx`            (line 2590) |
| `wallet_stake.py`        | `_build_stake_tx`             (line 2417) |
| `wallet_lp.py`           | `_build_deposit_lp_tx`        (line 2539) |
| `wallet_transfer.py`     | `_build_transfer_transaction` (line 1840) |
| `wallet_solana_swap.py`  | `build_solana_swap`           (line 3926) |
| `wallet_balance.py`      | `get_smart_wallet_balance`    (line  954) |

`pyproject.toml` adds `IlyonAi-Wallet-assistant-main/server` to `sys.path` so
imports resolve in development; production Docker images COPY the directory
so the same paths work.

## 6. Multi-step planner & executor (Phase 2)

### `compose_plan` LLM tool

LLM-as-planner. Tool input schema:

```json
{
  "title": "Bridge 1000 USDC then stake on Aave Arbitrum",
  "steps": [
    {"action": "bridge",
     "params": {"token_in": "USDC", "amount": "1000", "src_chain_id": 1,
                "dst_chain_id": 42161}},
    {"action": "stake",
     "params": {"token": "USDC", "protocol": "aave-v3",
                "chain_id": 42161},
     "resolves_from": {"amount": "step-1.received_amount"}}
  ]
}
```

Validation rules (Pydantic + `planner.build_plan`):

1. `action` ∈ {swap, bridge, stake, unstake, deposit_lp, withdraw_lp,
   transfer, approve, wait_receipt, get_balance}.
2. Topological sort over `depends_on`; reject cycles.
3. ≤ 4 explicit steps (excluding auto-injected approve / wait_receipt).
4. `resolves_from` keys must exist on the referenced step's expected output.
5. EVM ERC-20 actions auto-prefix an `approve` step; bridge auto-suffixes a
   `wait_receipt` if any later step depends on it.

### Planner pipeline

`src/agent/planner.py::build_plan(intent, ctx) -> ExecutionPlanV2Payload`

1. Topological sort.
2. Approve injection for ERC-20 swap / stake / deposit_lp / bridge on EVM.
3. Wait_receipt injection between any cross-chain pair.
4. Sentinel scoring for stake / deposit_lp / swap-to-yield targets via
   `defi_intelligence.get_opportunity_profile` + `pool_scorer.score`.
5. Shield gate per step → flags + severity.
6. Plan rollup: `total_gas_usd` = sum, `blended_sentinel` = USD-weighted
   average, `risk_gate` = `hard_block` if any step is critical, else
   `soft_warn` if blended_sentinel < 65 or notional > $10 k or cross-chain,
   else `clear`. `requires_double_confirm = (risk_gate == "soft_warn")`.

### Step executor

`src/agent/step_executor.py` — state machine per active plan, persisted in
the `agent_plans` SQLite table:

```
ready → signing → broadcast → confirmed → (next step ready)
                            ↘ failed → user choice (retry / abort / skip)
```

Receipt watcher (`src/agent/receipt_watcher.py`):

- EVM: `eth_getTransactionReceipt` via `/api/v1/rpc-proxy`, exponential
  backoff 1 s → 5 min cap, 30 min hard timeout.
- Solana: `getSignatureStatuses`, confirmation level `confirmed`.
- Cross-chain destination: deBridge order_id polling (already exists at
  `endpoints.py:1114` — read-only call, no edits to assistant).

Resolved values are extracted from receipt logs (e.g. bridge `Transfer`
event yields `received_amount`).

### SSE frames

`execution_plan_v2`, `step_status`, `plan_complete`, `plan_blocked`,
`sentinel`, `shield` — all already declared as event names in
`streaming.py`; Phase 0 adds the `plan_blocked` payload schema.

### Resume-on-reload

`agent_plans` row stores the full `ExecutionPlanV2Payload` JSON plus
per-step status. On SSE reconnect, runtime replays `execution_plan_v2`
followed by `step_status` for every step that has progressed beyond
`pending`, then resumes the watcher loop on the active step.

## 7. Universal Sentinel scoring (Phase 1)

`src/scoring/` is already in place. The Phase 1 work is making sure every
tool envelope is enriched. `enrich_tool_envelope` already covers
`get_defi_analytics`, `find_liquidity_pool`, `get_staking_options`,
`simulate_swap`, `build_swap_tx`, `build_solana_swap`, `build_bridge_tx`,
`build_stake_tx`, `build_deposit_lp_tx`, `build_transfer_tx`. After Phase 1
the wrappers from §5 hand it real builder JSON (today they return mocks),
so the scoring becomes meaningful for actual signing payloads.

`src/agent/runtime.py` already drains `.sentinel` / `.shield` into card
payloads. Phase 1 adds:

- Hard-block: if any step's Shield severity is `critical`, runtime emits a
  `plan_blocked` frame and skips the signing button on the frontend.
- Sentinel breakdown card: clicking the badge expands a panel showing the
  four sub-scores, the inputs (TVL, audit list, days_live, IL flag,
  exposure), and the formula.

## 8. Cross-chain optimizer daemon (Phase 3)

`src/optimizer/*` files already exist as scaffolds. Phase 3 wires:

- `agent_preferences.auto_rebalance_opt_in = 1` gate.
- Explicit `risk_budget` + `preferred_chains` + `gas_cap_usd` set by user.
- Signed EIP-712 attestation stored in
  `agent_preferences.rebalance_auth_signature`. **Attestation only — never
  authorises spending**; per-step wallet sig still required.

### Components

- `snapshot.py` — `PortfolioSnapshot(user_id)`, 6 h cache, reuses
  `src/portfolio/` and a read-only wrapper for
  `get_smart_wallet_balance`.
- `target_builder.py` — calls existing `allocate_plan` logic with the user's
  `risk_budget` + `total_usd`. Same scoring as the demo.
- `delta.py` — diffs current vs target. Emits `Move` only if **all three**:
  - `apy_delta ≥ +2.0 %`
  - `sentinel_delta ≥ 0`
  - `apy_delta · usd_value > 4 × estimated_gas_usd` (3-month gas-adjusted
    breakeven)
- `plan_synth.py` — translates moves into the same intent shape that
  `compose_plan` emits, then calls `planner.build_plan(intent, ctx)`.
- `daemon.py` — APScheduler. `snapshot_job` every 6 h jittered;
  `propose_job` every 24 h at 04:00 UTC jittered.
- `notifier.py` — SSE push if user has an active session, email fallback.
- `safety.py` — 7-day cooldown, 1 proposal/day, 48 h plan TTL, kill-switch
  via `OPTIMIZER_ENABLED=0`.

### Manual rebalance via chat

`rebalance_portfolio` tool calls the same snapshot → target → delta →
plan_synth chain synchronously. Daemon and chat share 100 % of code paths.

### Daemon never signs

Daemon only proposes; persists plan in `agent_plans` with
`status="proposed"`; emits notification. User signs each step.

## 9. Owner-improvements (added scope)

1. **Sentinel-aware chip presets** (Conservative / Balanced / Aggressive /
   Maximize APY) on every chat surface — saves user from typing
   `"low risk only"`, persists in `agent_preferences`.
2. **Plan-level Shield gate** — if any step has `severity == critical`,
   `risk_gate=hard_block`, no signing button, explanation card shown.
3. **Persistent `agent_preferences`** — slippage cap, preferred chains,
   blocked protocols, double-confirm threshold, risk_budget, rebalance opt-in.
   Read on every plan composition.
4. **Receipt resume-on-reload** — `agent_plans` SQLite table persists
   in-flight plans; SSE reconnect replays state.
5. **Sentinel breakdown explainer card** — one-tap expansion of the
   four-dim score, inputs, and formula.
6. **Chat-history parity** — Sentinel-side `chats` / `messages` endpoints
   read-compatible with the assistant schema, so flipping `AGENT_BACKEND`
   does not orphan past conversations.
7. **DemoChatFrame mounted** on `/demo` route so the prompt's "demo from
   main" is visible and identical to the production chat.
8. **Sentinel matrix card** rendered for every multi-position recommendation
   (today only `allocate_plan` emits it) — one tap to see all four scores
   per pool.

## 10. Database tables

```sql
-- Phase 0
CREATE TABLE agent_preferences (
  user_id INTEGER PRIMARY KEY,
  risk_budget TEXT DEFAULT 'balanced',
  preferred_chains TEXT,         -- JSON array
  blocked_protocols TEXT,        -- JSON array
  gas_cap_usd REAL,
  slippage_cap_bps INTEGER DEFAULT 50,
  notional_double_confirm_usd REAL DEFAULT 10000,
  auto_rebalance_opt_in INTEGER DEFAULT 0,
  rebalance_auth_signature TEXT,
  rebalance_auth_nonce INTEGER,
  updated_at TIMESTAMP
);

-- Phase 0 (chat history parity, schema-compatible with assistant)
CREATE TABLE agent_chats (
  id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  title TEXT,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
);
CREATE TABLE agent_chat_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chat_id TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  cards_json TEXT,
  created_at TIMESTAMP NOT NULL
);

-- Phase 2
CREATE TABLE agent_plans (
  plan_id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL,
  expires_at TIMESTAMP
);

-- Phase 3
CREATE TABLE optimizer_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  ran_at TIMESTAMP NOT NULL,
  snapshot_id TEXT,
  plan_id TEXT,
  proposed_apy_delta REAL,
  proposed_sentinel_delta INTEGER,
  outcome TEXT
);

CREATE TABLE portfolio_snapshots (
  id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  captured_at TIMESTAMP NOT NULL,
  total_usd REAL,
  blended_apy REAL,
  blended_sentinel INTEGER,
  positions_json TEXT
);
```

All migrations are forward-only and additive; rollback is `DROP TABLE`.

## 11. Routing

`web/app/api/v1/agent/route.ts` reads `process.env.AGENT_BACKEND`:

```ts
const target = process.env.AGENT_BACKEND === "wallet"
  ? (process.env.ASSISTANT_API_TARGET || "http://localhost:8000")
  : (process.env.SENTINEL_API_TARGET || "http://localhost:8080");
```

- Phase 0 default: `AGENT_BACKEND=wallet` (current behaviour).
- After Phase 1 validation passes: flip default to `sentinel` in
  `docker-compose.yml` + Vercel env.
- Rollback: flip env var; no code change.

## 12. Phasing

| Phase | Ships when |
|---|---|
| **Phase 0 — Foundations cleanup** | `pytest tests/agent tests/scoring tests/storage` green; routing test green; `npm run type-check` green; CI guard passes |
| **Phase 1 — Universal Sentinel + flip** | A1–A12 pass on live `docker compose` |
| **Phase 2 — Multi-step planner + executor** | B1–B10 pass on live |
| **Phase 3 — Optimizer daemon** | C1–C8 pass on live |

Order is forced: Phase 1 needs Phase 0 schemas + routing; Phase 2 needs
Phase 1 wrappers; Phase 3 needs Phase 2 planner.

## 13. Real-request validation cases

Each phase ends with `scripts/validate_phase_N.sh` that hits the live
running stack with these prompts and asserts response shape, frame
sequence, Sentinel + Shield content, and CI guard cleanliness.
**No phase ships without 100 % pass.**

### Phase 0 — Z series (foundation smokes, 4 cases)

| # | Action | Asserts |
|---|---|---|
| Z1 | `GET /api/v1/agent-health` against Sentinel | 200, version, `feature_agent_v2: true` |
| Z2 | Set `AGENT_BACKEND=wallet`, send any prompt | response served by wallet (no SSE frames with Sentinel sidecars) |
| Z3 | Set `AGENT_BACKEND=sentinel`, send `"hi"` | SSE stream from Sentinel; `done` frame; persisted message in `agent_chat_messages` |
| Z4 | Run CI guard | `bash scripts/check_assistant_immutable.sh` exits 0 |

### Phase 1 — A series (12 cases)

| # | Prompt | Asserts |
|---|---|---|
| A1  | `"allocate $10k USDC"` | 3 cards (allocation, sentinel_matrix, execution_plan); 5 positions; weighted sentinel ≥ 70 — demo parity unchanged |
| A2  | `"highest APR for USDC on Polygon"` | universal_cards + sidecar sentinel field on each pool; risk_level present; flags non-empty for unaudited entries |
| A3  | `"where can I stake BNB"` | universal_cards; each card has Sentinel score + Shield verdict |
| A4  | `"what's my balance"` | balance_report unchanged + Sentinel on yield-bearing positions |
| A5  | `"explain your scoring methodology"` | text answer mentioning all four dimensions and 0.40/0.25/0.20/0.15 blend |
| A6  | `"swap 1 ETH to USDC"` | swap proposal + Shield severity ≥ info; route lists Enso/Jupiter; Sentinel sidecar present |
| A7  | `"swap 1 ETH to RANDOMSCAMTOKEN"` | Shield severity ≥ warn; flags include "Unaudited" or "Honeypot pattern" |
| A8  | `"bridge 100 USDC to Arbitrum"` | bridge proposal + Shield verdict + Sentinel-scored destination |
| A9  | `"low-risk only"` chip | `risk_budget=conservative`; min sentinel ≥ 82 |
| A10 | `"maximize APY"` chip | `risk_budget=aggressive`; weighted sentinel ≥ 55 floor |
| A11 | `"set my slippage cap to 30 bps"` | `agent_preferences` row updated; future swaps carry slippage=30bps |
| A12 | `"set my preferred chains to Arbitrum and Base"` | preference saved; allocate filters to those chains |

### Phase 2 — B series (10 cases)

| # | Prompt | Asserts |
|---|---|---|
| B1  | `"bridge 1000 USDC from Ethereum to Arbitrum and stake it on Aave"` | 4 steps (approve, bridge, wait_receipt, stake); blended_sentinel ≥ 65; risk_gate=soft_warn |
| B2  | `"swap 0.5 ETH to USDC then provide liquidity to USDC/USDT on Curve"` | 3 steps (swap, approve, deposit_lp); LP target Sentinel ≥ 65 |
| B3  | Sign step 1 of B1; observe step 2 timing | step_status frames in order; step 2 stays pending until step 1 confirmed |
| B4  | Reject signing step 2 of B1 | plan aborted; idle funds remain on dest chain (no orphan state) |
| B5  | `"stake 50 ETH on Lido"` | `requires_double_confirm=true`; UI gate present |
| B6  | `"swap 1 ETH to KNOWN-MALICIOUS-ADDRESS"` | `risk_gate=hard_block`; no signing button; explanation card |
| B7  | `"send 100 USDC to vitalik.eth"` | single-step plan; not flagged multi-step |
| B8  | `"stake all my idle ETH"` | get_balance resolution → stake step uses resolved amount |
| B9  | Close tab mid-execution, reopen | plan resumes from last confirmed step |
| B10 | `"do A then B then C then D"` (4-action chain) | planner accepts up to 4 explicit steps; warning emitted at limit |

### Phase 3 — C series (8 cases)

| # | Action | Asserts |
|---|---|---|
| C1 | Opt in, sign EIP-712 | `auto_rebalance_opt_in=1`, `rebalance_auth_signature` populated |
| C2 | `propose_job` on optimal portfolio | `optimizer_runs.outcome='no_change'`; no plan |
| C3 | `propose_job` on portfolio with idle USDC > $1 k | proposal generated; APY delta ≥ +2 %; sentinel delta ≥ 0; gas-breakeven < 90 d |
| C4 | `"rebalance my portfolio"` in chat | same `ExecutionPlanV2Card` shape as daemon |
| C5 | Daemon proposal with no active session | email sent; plan TTL=48 h |
| C6 | APY drifts during 48 h TTL | plan auto-expires; new run schedules |
| C7 | Opt out (flag=0) | running plans complete; no new proposals queued |
| C8 | `"force rebalance"` within 7 d cooldown | cooldown bypassed; logged in `optimizer_runs` |

## 14. Reversibility

1. Master rollback: `git reset --hard pre-fusion-rewrite-20260501`.
2. Per-phase tag: `git tag pre-phase-{0,1,2,3}` before each phase merges.
3. `AGENT_BACKEND` env var kill-switch on routing.
4. DB migrations are forward-only and additive; rollback = drop new tables.
5. `OPTIMIZER_ENABLED=0` gates the daemon.
6. CI guard `scripts/check_assistant_immutable.sh` blocks any commit that
   modifies `IlyonAi-Wallet-assistant-main/`.

## 15. File inventory (delta from `1fbbff5`)

### NEW

```
src/agent/tools/
  wallet_swap.py
  wallet_bridge.py
  wallet_stake.py
  wallet_lp.py
  wallet_transfer.py
  wallet_solana_swap.py
  wallet_balance.py
  compose_plan.py
  update_preference.py
  rebalance_portfolio.py            # Phase 3

src/storage/
  agent_plans.py                    # Phase 0 SQLite store
  agent_preferences.py              # Phase 0
  agent_chats.py                    # Phase 0 (history parity)

src/api/routes/
  agent_chats.py                    # Phase 0 read-only chat history endpoints
  agent_preferences.py              # Phase 0

migrations/versions/
  20260502_agent_preferences.py     # Phase 0
  20260502_agent_chats.py           # Phase 0
  20260601_agent_plans.py           # Phase 2
  20260701_optimizer_runs.py        # Phase 3

scripts/
  validate_phase_0.sh
  validate_phase_1.sh               # rewritten; current placeholder is a smoke test
  validate_phase_2.sh
  validate_phase_3.sh
  run_optimizer.py                  # Phase 3 entrypoint

web/app/demo/
  page.tsx                          # Phase 1 mounts DemoChatFrame

web/components/agent/cards/
  SentinelBreakdownCard.tsx         # Phase 1 explainer
  PlanBlockedCard.tsx               # Phase 2 hard-block card

web/components/agent/
  ChipPresets.tsx                   # Phase 1

tests/agent/
  test_wallet_swap.py
  test_wallet_bridge.py
  test_wallet_stake.py
  test_wallet_lp.py
  test_wallet_transfer.py
  test_wallet_solana_swap.py
  test_compose_plan.py
  test_update_preference.py
  test_step_executor_persistence.py
  test_receipt_watcher.py
  test_runtime_hard_block.py

tests/storage/
  test_agent_plans.py
  test_agent_preferences.py
  test_agent_chats.py

tests/optimizer/
  test_target_builder.py
  test_plan_synth.py
  test_daemon_safety.py
  test_notifier.py

tests/web/
  test_route_backend_switch.test.cjs
  test_demo_page.test.tsx
  test_chip_presets.test.tsx

tests/integration/
  test_phase_0_smoke.py
  test_phase_1_universal_scoring.py
  test_phase_2_multi_step.py
  test_phase_3_rebalance.py
```

### EDITED (small additive diffs only)

```
src/agent/tools/__init__.py              # register wallet_*, compose_plan,
                                         #   update_preference, rebalance_portfolio
src/agent/tools/swap_build.py            # delegates to wallet_swap
src/agent/tools/bridge_build.py          # delegates to wallet_bridge
src/agent/tools/stake_build.py           # delegates to wallet_stake
src/agent/tools/lp_build.py              # delegates to wallet_lp
src/agent/tools/transfer_build.py        # delegates to wallet_transfer
src/agent/tools/solana_swap.py           # delegates to wallet_solana_swap
src/agent/tools/balance.py               # delegates to wallet_balance
src/agent/runtime.py                     # plan_blocked emission, history persist
src/agent/simple_runtime.py              # plan_blocked emission; persist messages
src/agent/streaming.py                   # plan_blocked event name
src/agent/step_executor.py               # SQLite-backed PlanExecutionStore
src/api/schemas/agent.py                 # PlanBlockedFrame
src/api/routes/agent.py                  # mounts agent_chats + preferences
src/config.py                            # AGENT_BACKEND, OPTIMIZER_ENABLED, SENTINEL_API_TARGET
pyproject.toml                           # add IlyonAi-Wallet-assistant-main/server to sys.path

web/app/api/v1/agent/route.ts            # AGENT_BACKEND switch
web/app/page.tsx                         # link to /demo
web/components/agent/cards/CardRenderer  # render SentinelBreakdownCard, PlanBlockedCard
web/components/agent/MessageList.tsx     # ChipPresets
web/hooks/useAgentStream.ts              # plan_blocked handling, resume support
web/next.config.js                       # AGENT_BACKEND test parity
docker-compose.yml                       # AGENT_BACKEND=sentinel after Phase 1
```

### FROZEN (CI-guarded, zero modifications)

```
IlyonAi-Wallet-assistant-main/   entire tree, including:
  server/app/agents/crypto_agent.py     (4703 lines)
  server/app/api/endpoints.py           (1129 lines)
  server/app/api/chats.py
  client/
```

## 16. Risk register

| # | Risk | Mitigation |
|---|---|---|
| 1 | Importing `crypto_agent.py` triggers heavy module init | Lazy imports inside wrapper bodies; `functools.cache` for shared clients |
| 2 | Builder JSON shape varies per chain | Per-wrapper adapter; covered by unit tests with golden fixtures |
| 3 | LLM emits invalid plan DAG | Strict Pydantic in `compose_plan`; on fail return clarification frame |
| 4 | Routing flip orphans chat history | Phase 0 ports `chats` / `messages` endpoints to Sentinel side, schema-compatible |
| 5 | Receipt watcher hangs on slow chains | Backoff 1 s → 5 min; 30 min hard timeout; user retry/abort/skip |
| 6 | DefiLlama rate limits | `src/scoring/cache.py` 60 s hot + 24 h cold; daemon jitter |
| 7 | EIP-712 misread as spending authorisation | UI copy clearly states "attestation only"; nonce-bound; per-step sig still required |
| 8 | Schema migration ordering | Phase 1 cannot merge before Phase 0; migrations numbered by date |

## 17. Out of scope (explicit YAGNI)

- 4337 / smart-wallet bundling
- Auto-execute by daemon (proposes only)
- ML/RL portfolio optimisation
- Tax-lot optimisation
- Live audit-NFT verification
- Per-token reputation graph
- User-tunable Sentinel rubric weights
- Off-chain TWAP execution
- Multi-user pooled rebalancing
- DAG branching plans (linear only in v1)
- Auto-retry on hard failure (always user-confirmed)
- Gas-token auto-funding
