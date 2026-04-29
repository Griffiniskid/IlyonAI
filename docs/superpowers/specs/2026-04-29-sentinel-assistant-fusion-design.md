# Sentinel ⇄ Assistant Fusion — Design Spec

**Date:** 2026-04-29
**Status:** Approved
**Reversibility checkpoint:** `checkpoint/pre-scoring-merge-brainstorm-20260429-133016` (commit `bf1891e`)
**Rollback:** `git reset --hard checkpoint/pre-scoring-merge-brainstorm-20260429-133016`

## 0. Problem statement

Two agent systems exist in the repo and neither does what we want:

1. **Sentinel agent** (`src/agent/*`, port 8080) — has the demo-quality scoring
   pipeline (`allocate_plan`), 4-dimension Sentinel rubric, Shield flags, SSE
   streaming with cards. No real wallet operations.
2. **Wallet assistant** (`IlyonAi-Wallet-assistant-main/server/...`, port 8000) —
   has 14 wallet-ops tools (build_swap, build_bridge, build_stake, build_transfer,
   build_deposit_lp). No scoring. Cannot execute multi-step intents.

The Next.js `/agent/*` chat surface today routes to the wallet assistant, so
users get wallet ops without scoring, and "bridge USDC and stake it" returns
only the bridge step (regex fast-paths in `endpoints.py:728–880` match on first
verb; `return_direct=True` on tx-builder tools in `crypto_agent.py:4471–4685`
halts the LangChain executor after one tool call).

## 1. Goal

Fuse the two so that:

- The chat surface uses the Sentinel agent as the brain.
- Every recommendation (yield, pool, staking, swap, bridge) carries the same
  Sentinel scoring envelope as the demo allocate flow.
- Multi-step intents like "bridge X then stake on protocol Y" decompose into a
  validated plan, scored end-to-end, executed step-by-step with on-chain receipt
  watching.
- An opt-in cross-chain yield optimizer daemon proposes (never executes)
  rebalance plans that share 100% of code paths with the manual chat command.
- The wallet assistant codebase is **never modified** — additive only,
  enforced by CI.

## 2. Architecture

```
┌──────────────────────────────────────────────┐
│  Next.js /agent/* chat UI  (port 3000)       │
│  + new ExecutionPlanV2Card · StepStatusCard  │
│  + SentinelBadge · ShieldBadge               │
└────────────────┬─────────────────────────────┘
                 │ SSE: /api/v1/agent
                 ▼
┌─────────────────────────────────────────────────────┐
│  src/agent/runtime.py  (Sentinel ReAct, port 8080)  │
│  ┌─ NEW: planner.py ───────────────────────────┐    │
│  │  Decomposes intent → ordered Step DAG       │    │
│  │  Emits ExecutionPlanV2 envelope BEFORE      │    │
│  │  any tx is built. User confirms once.       │    │
│  └─────────────────────┬───────────────────────┘    │
│  ┌─ tools/ ───────────────────────────────────┐     │
│  │ existing: allocate_plan, balance, swap...  │     │
│  │ NEW wrappers (call assistant funcs only):  │     │
│  │   wallet_swap.py    → _build_swap_tx       │     │
│  │   wallet_bridge.py  → _build_bridge_tx     │     │
│  │   wallet_stake.py   → _build_stake_tx      │     │
│  │   wallet_transfer.py → _build_transfer_tx  │     │
│  │   wallet_lp.py      → _build_deposit_lp_tx │     │
│  │ NEW @sentinel_decorator wraps everything   │     │
│  └────────────────────────────────────────────┘     │
│  ┌─ NEW: step_executor.py ─────────────────────┐    │
│  │  Watches signed-tx receipts via rpc-proxy,  │    │
│  │  resolves step N+1 params, emits step_status│    │
│  └─────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────┘
                 │  read-only function imports
                 ▼
┌─────────────────────────────────────────────────────┐
│  IlyonAi-Wallet-assistant-main/  (FROZEN)           │
│  CI guard: scripts/check_assistant_immutable.sh     │
└─────────────────────────────────────────────────────┘

┌─ NEW: src/optimizer/ (Phase 3) ─────────────────────┐
│  rebalance_daemon.py — opt-in, EIP-712 attested     │
│  Proposes plans, never signs, shares planner path   │
└─────────────────────────────────────────────────────┘
```

## 3. Sentinel rubric (unchanged from demo)

Per pool, scored 0–100 in four dimensions:

- **Safety** = audit + TVL tier + single-asset exposure + no-IL
- **Durability** = days-live tenure + sane APY + stablecoin
- **Exit** = TVL tier + stablecoin denom + single exposure
- **Confidence** = audit + tenure (≥720d / ≥365d / ≥180d)

**Weighted blend:** `sentinel = 0.40·safety + 0.25·durability + 0.20·exit + 0.15·confidence`.

**Risk bucket:** `≥82 → low`, `≥65 → medium`, else `high`.

The current implementation in `src/allocator/composer.py` is the canonical
source. This spec extracts it into `src/scoring/rubric.py` without behavioral
change, then exposes it to all tools.

## 4. Plan & Score data types

Added to `src/api/schemas/agent.py` (no breaking changes to existing fields):

```python
class SentinelScore(BaseModel):
    safety: int
    durability: int
    exit: int
    confidence: int
    weighted: int
    risk_level: Literal["low", "medium", "high"]
    strategy_fit: Literal["conservative", "balanced", "aggressive"]
    flags: list[str]
    breakdown_explainer: str

class ShieldVerdict(BaseModel):
    severity: Literal["clear", "info", "warn", "critical"]
    flags: list[str]
    blocked_reasons: list[str]
    last_checked_at: datetime
    sources: list[str]

class PlanStep(BaseModel):
    step_id: str
    order: int
    action: Literal["swap", "bridge", "stake", "unstake",
                    "deposit_lp", "withdraw_lp", "transfer",
                    "approve", "wait_receipt"]
    params: dict
    depends_on: list[str] = []
    resolves_from: dict = {}
    sentinel: SentinelScore | None = None
    shield_flags: list[str] = []
    estimated_gas_usd: float | None = None
    estimated_duration_s: int | None = None
    status: Literal["pending", "ready", "signing", "broadcast",
                    "confirmed", "failed", "skipped"] = "pending"
    tx_hash: str | None = None
    receipt: dict | None = None
    error: str | None = None

class ExecutionPlanV2Payload(BaseModel):
    plan_id: str
    title: str
    steps: list[PlanStep]
    total_steps: int
    total_gas_usd: float
    total_duration_estimate_s: int
    blended_sentinel: int | None
    requires_signature_count: int
    risk_warnings: list[str]
    risk_gate: Literal["clear", "soft_warn", "hard_block"] = "clear"
    requires_double_confirm: bool = False
    chains_touched: list[str] = []
    user_assets_required: dict[str, str] = {}

# Sidecar on existing ToolEnvelope:
class ToolEnvelope(BaseModel):
    # ...existing fields...
    sentinel: SentinelScore | None = None       # NEW
    shield: ShieldVerdict | None = None         # NEW
    scoring_inputs: dict | None = None          # NEW (transparency)
```

## 5. Multi-step planner (Phase 2)

`src/agent/planner.py` exports `build_plan(intent, ctx) -> ExecutionPlanV2Payload`.
Pure function; deterministic; no LLM in the execution path.

Pipeline:
1. **Topological sort** of steps by `depends_on`.
2. **Approve injection** for ERC20 swap/stake/deposit_lp on EVM.
3. **wait_receipt injection** between any cross-chain pair.
4. **Sentinel scoring** for stake/deposit_lp/swap-to-yield targets via
   `defi_intelligence.get_opportunity_profile` + `pool_scorer.score`.
5. **Shield gate** per step → flags + severity.
6. **Plan-level rollup**:
   - `total_gas_usd` = sum.
   - `blended_sentinel` = usd-weighted average.
   - `risk_gate`: `hard_block` if any critical; `soft_warn` if sentinel<65,
     notional>$10k, or cross-chain; else `clear`.
   - `requires_double_confirm` = `(risk_gate == "soft_warn")`.

LLM emits an intent JSON via a new `compose_plan` tool (not a build tool).
Execution begins only after the user clicks Confirm in the
`ExecutionPlanV2Card`.

### Step executor

`src/agent/step_executor.py` — state machine per active plan, persisted in
`agent_plans` table.

```
ready → signing → broadcast → confirmed → (next step ready)
                            ↘ failed → user choice (retry/abort/skip)
```

Receipt watching:
- EVM: `eth_getTransactionReceipt` via existing `/api/v1/rpc-proxy` with
  exponential backoff (1s → 5min cap).
- Solana: `getSignatureStatuses`, confirmation level = `confirmed`.
- Cross-chain destination: deBridge order_id polling (already exists in
  `endpoints.py:1114`).

Resolved values extracted from receipt logs (e.g., bridge `Transfer` event
gives `received_amount` for the next step).

### New SSE frames

- `execution_plan_v2` — emitted once when plan is composed.
- `step_status` — emitted on every state transition.
- `plan_complete` — emitted when last step confirms or plan aborts.

## 6. Universal scoring (Phase 1)

`src/scoring/` package centralizes:
- `rubric.py` — re-exports rubric primitives from `composer.py`.
- `pool_scorer.py`, `token_scorer.py`, `route_scorer.py`, `bridge_scorer.py`.
- `normalizer.py` — uniform Pool dict from any source.
- `cache.py` — 60s in-memory + 24h Redis (if configured).
- `shield_gate.py` — pre-tx risk verdict (heuristics + audit list +
  GoPlus heuristic + vendor allowlist + notional gate).

`src/agent/tools/sentinel_wrap.py` — `@sentinel_decorator(target=...)` mutates
tool envelopes post-call:
- `target="pool"` → `get_defi_analytics`, `find_liquidity_pool`.
- `target="staking_option"` → `get_staking_options`.
- `target="tx_pool"` → `build_stake_tx`, `build_deposit_lp_tx`.
- `target="route"` → `build_swap_tx`.
- `target="bridge"` → `build_bridge_tx`.

Wrappers in `src/agent/tools/wallet_*.py` import the untouched
`crypto_agent._build_*_tx` functions and apply the decorator. The
wallet-assistant codebase itself is never modified.

`src/agent/runtime.py` gains ~10 lines to drain new sidecar fields into SSE
frames and hard-block the agent loop on `ShieldVerdict.severity == "critical"`.

## 7. Cross-chain optimizer daemon (Phase 3)

`src/optimizer/` package. Opt-in only via three gates:

1. `agent_preferences.auto_rebalance_opt_in = 1`.
2. Explicit risk_budget + preferred_chains + gas_cap_usd set.
3. Signed EIP-712 attestation stored in `agent_preferences.rebalance_auth_signature`.

The signature does NOT authorize spending — it's an attestation. Every
transaction still requires per-step wallet signature.

### Components

- `snapshot.py` — `PortfolioSnapshot(user_id)`, 6h cache, reuses existing
  `src/portfolio/` and read-only wrapper for assistant balance functions.
- `target_builder.py` — calls existing `allocate_plan` logic with user's
  `risk_budget` + total_usd. Same scoring pipeline as the demo.
- `delta.py` — diffs current vs target. Emits `Move` only if **all three**:
  - `apy_delta >= +2.0%`
  - `sentinel_delta >= 0`
  - `apy_delta * usd_value > 4 * estimated_gas_usd` (3-month gas-adjusted breakeven)
- `plan_synth.py` — translates moves into `PlanIntent`, calls existing
  `planner.build_plan(intent, ctx)`. Returns standard `ExecutionPlanV2Payload`.
- `daemon.py` — APScheduler, two jobs:
  - `snapshot_job` every 6h jittered.
  - `propose_job` every 24h at 04:00 UTC jittered.
- `notifier.py` — SSE push if user has active session, email fallback.
- `safety.py` — 7-day cooldown, 1 proposal/day cap, 48h plan TTL, kill-switch.

### Manual rebalance via chat

`rebalance_portfolio` tool calls the same snapshot → target → diff → plan_synth
chain synchronously. Daemon and chat share 100% of code paths.

### Daemon never signs

Daemon only proposes; persists plan in `agent_plans` with `status="proposed"`;
emits notification. User signs each step in their wallet.

## 8. New tables

```sql
-- Phase 1
CREATE TABLE agent_preferences (
  user_id INTEGER PRIMARY KEY,
  risk_budget TEXT DEFAULT 'balanced',
  preferred_chains TEXT,
  blocked_protocols TEXT,
  gas_cap_usd REAL,
  slippage_cap_bps INTEGER DEFAULT 50,
  notional_double_confirm_usd REAL DEFAULT 10000,
  auto_rebalance_opt_in INTEGER DEFAULT 0,
  rebalance_auth_signature TEXT,
  rebalance_auth_nonce INTEGER,
  updated_at TIMESTAMP
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

## 9. Routing

`web/next.config.js` introduces `AGENT_BACKEND` env var (`sentinel` | `wallet`).
- During Phase 1 development: default = `wallet` (current behavior).
- After Phase 1 staging green: flip to `sentinel`.
- Rollback: flip env var; no code change.

```js
const assistantTarget = process.env.AGENT_BACKEND === "sentinel"
  ? (process.env.API_REWRITE_TARGET || "http://localhost:8080")
  : (process.env.ASSISTANT_API_TARGET || "http://localhost:8000");
```

## 10. Phasing

| Phase | Ships when |
|---|---|
| **Phase 1** — Sentinel-everywhere + routing flip | A1–A12 pass on staging |
| **Phase 2** — Multi-step planner + executor | B1–B10 pass on staging |
| **Phase 3** — Optimizer daemon | C1–C8 pass on staging |

Order is forced: planner needs sentinel_wrap; daemon needs planner.

## 11. Real-request validation cases

### Phase 1 — A series (12 cases)

| # | Prompt | Asserts |
|---|---|---|
| A1 | `"allocate $10k USDC"` | 3 cards (allocation, sentinel_matrix, execution_plan); 5 positions; weighted sentinel ≥ 70 — demo parity unchanged |
| A2 | `"highest APR for USDC on Polygon"` | universal_cards + sidecar sentinel field on each pool; risk_level present; flags[] non-empty for unaudited entries |
| A3 | `"where can I stake BNB"` | universal_cards; each card has Sentinel score + Shield verdict |
| A4 | `"what's my balance"` | balance_report unchanged + Sentinel on yield-bearing positions |
| A5 | `"explain your scoring methodology"` | text answer mentioning all four dimensions and 0.40/0.25/0.20/0.15 blend |
| A6 | `"swap 1 ETH to USDC"` | swap proposal + sidecar shield severity ≥ info; route lists Enso/Jupiter |
| A7 | `"swap 1 ETH to RANDOMSCAMTOKEN"` | shield severity ≥ warn; flags include "Unaudited" or "Honeypot pattern" |
| A8 | `"bridge 100 USDC to Arbitrum"` | bridge proposal + shield verdict + Sentinel-scored destination |
| A9 | `"low-risk only"` chip | risk_budget=conservative; min sentinel ≥ 82 |
| A10 | `"maximize APY"` chip | risk_budget=aggressive; weighted sentinel ≥ 55 floor |
| A11 | `"set my slippage cap to 30 bps"` | agent_preferences row updated; future swaps carry slippage=30bps |
| A12 | `"set my preferred chains to Arbitrum and Base"` | preference saved; allocate filters to those chains |

### Phase 2 — B series (10 cases)

| # | Prompt | Asserts |
|---|---|---|
| B1 | `"bridge 1000 USDC from Ethereum to Arbitrum and stake it on Aave"` | 4 steps (approve, bridge, wait_receipt, stake); blended_sentinel ≥ 65; risk_gate=soft_warn |
| B2 | `"swap 0.5 ETH to USDC then provide liquidity to USDC/USDT on Curve"` | 3 steps (swap, approve, deposit_lp); LP target Sentinel ≥ 65 |
| B3 | Sign step 1 of B1; observe step 2 timing | step_status frames in order; step 2 stays pending until step 1 confirmed |
| B4 | Reject signing step 2 of B1 | plan aborted; idle funds remain on dest chain (no orphan state) |
| B5 | `"stake 50 ETH on Lido"` | requires_double_confirm=true; UI gate present |
| B6 | `"swap 1 ETH to KNOWN-MALICIOUS-ADDRESS"` | risk_gate=hard_block; no signing button; explanation card |
| B7 | `"send 100 USDC to vitalik.eth"` | single-step plan; not flagged multi-step |
| B8 | `"stake all my idle ETH"` | get_balance resolution → stake step uses resolved amount |
| B9 | Close tab mid-execution, reopen | plan resumes from last confirmed step |
| B10 | `"do A then B then C then D"` | planner caps at 4 explicit steps; warning emitted |

### Phase 3 — C series (8 cases)

| # | Action | Asserts |
|---|---|---|
| C1 | Opt in, sign EIP-712 | auto_rebalance_opt_in=1, rebalance_auth_signature populated |
| C2 | propose_job on optimal portfolio | optimizer_runs.outcome='no_change'; no plan |
| C3 | propose_job on portfolio with idle USDC > $1k | proposal generated; APY delta ≥ +2%; sentinel delta ≥ 0; gas-breakeven < 90d |
| C4 | `"rebalance my portfolio"` in chat | same ExecutionPlanV2Card shape as daemon |
| C5 | Daemon proposal with no active session | email sent; plan TTL=48h |
| C6 | APY drifts during 48h TTL | plan auto-expires; new run schedules |
| C7 | Opt out (flag=0) | running plans complete; no new proposals queued |
| C8 | "force rebalance" within 7d cooldown | cooldown bypassed; logged in optimizer_runs |

Each phase ends with `scripts/validate_phase_N.sh` that hits the live system
with these prompts and asserts response shape, frame sequence, and Sentinel/Shield
content. **No phase ships without 100% pass.**

## 12. Reversibility

1. Per-phase tag: `git tag pre-phase-{1,2,3}` before each phase merges.
2. `AGENT_BACKEND` env var kill-switch on routing.
3. DB migrations are forward-only and additive; rollback = drop new tables.
4. `OPTIMIZER_ENABLED=1` gates the daemon; unset = daemon dormant.
5. CI guard `scripts/check_assistant_immutable.sh` blocks any commit that
   modifies `IlyonAi-Wallet-assistant-main/`.
6. Master rollback: `git reset --hard checkpoint/pre-scoring-merge-brainstorm-20260429-133016`.

## 13. File inventory

### NEW (~40 files)

```
src/scoring/
  __init__.py
  rubric.py
  pool_scorer.py
  token_scorer.py
  route_scorer.py
  bridge_scorer.py
  normalizer.py
  cache.py
  shield_gate.py

src/agent/
  planner.py                   # Phase 2
  step_executor.py             # Phase 2
  receipt_watcher.py           # Phase 2

src/agent/tools/
  sentinel_wrap.py             # Phase 1
  wallet_swap.py               # Phase 1
  wallet_bridge.py
  wallet_stake.py
  wallet_transfer.py
  wallet_lp.py
  wallet_balance.py
  rebalance_portfolio.py       # Phase 3
  compose_plan.py              # Phase 2
  update_preference.py         # Phase 1

src/optimizer/                 # Phase 3
  __init__.py
  daemon.py
  snapshot.py
  target_builder.py
  delta.py
  plan_synth.py
  notifier.py
  safety.py

migrations/versions/
  YYYYMMDD_agent_preferences.py    # Phase 1
  YYYYMMDD_agent_plans.py          # Phase 2
  YYYYMMDD_optimizer_runs.py       # Phase 3

scripts/
  validate_phase_1.sh
  validate_phase_2.sh
  validate_phase_3.sh
  check_assistant_immutable.sh
  run_optimizer.py                 # Phase 3 entrypoint

web/components/agent/cards/
  ExecutionPlanV2Card.tsx          # Phase 2
  StepStatusCard.tsx               # Phase 2
  SentinelBadge.tsx                # Phase 1
  ShieldBadge.tsx                  # Phase 1

web/hooks/
  useExecutionPlan.ts              # Phase 2

tests/
  scoring/test_pool_scorer.py
  scoring/test_shield_gate.py
  scoring/test_rubric.py
  agent/test_planner.py
  agent/test_step_executor.py
  agent/test_sentinel_wrap.py
  optimizer/test_delta_hysteresis.py
  optimizer/test_daemon.py
  optimizer/test_snapshot.py
  integration/test_phase_1_end_to_end.py
  integration/test_phase_2_multi_step.py
  integration/test_phase_3_rebalance.py
```

### EDITED (~6 files, all small additive diffs)

```
src/api/schemas/agent.py                       # +SentinelScore, +ShieldVerdict, +PlanStep, +ExecutionPlanV2Payload, +ToolEnvelope sidecar fields
src/agent/runtime.py                           # +10 lines: emit sentinel/shield SSE frames, hard-block on critical
src/agent/streaming.py                         # +3 SSE event names (execution_plan_v2, step_status, plan_complete, sentinel, shield, plan_blocked)
src/agent/tools/__init__.py                    # register new tools
web/components/agent/cards/CardRenderer.tsx    # +badges, +2 new card types (execution_plan_v2, step_status)
web/next.config.js                             # AGENT_BACKEND env-driven rewrite
```

### FROZEN (CI-guarded zero modifications)

```
IlyonAi-Wallet-assistant-main/    entire tree, including:
  server/app/agents/crypto_agent.py     (4703 lines)
  server/app/api/endpoints.py           (1129 lines)
  server/app/api/chats.py
  client/
```

## 14. Risks documented for the spec

1. **DefiLlama rate limits** — daemon × all opted-in users × 6h could hit limits.
   Mitigation: per-chain caches in `src/scoring/cache.py` (60s hot, 24h cold).
2. **Receipt watcher latency** — slow chains can leave step 1 in `broadcast` for
   10+ minutes. Mitigation: visible timer + "speed up" option in StepStatusCard.
3. **Solana finality tradeoff** — using `confirmed` (not `finalized`) for UX speed.
4. **Cross-chain destination ambiguity** — planner asks LLM for explicit
   destination; if ambiguous, UI shows clarification step before plan finalizes.
5. **EIP-712 signature scope** — bound to nonce + version; re-sign required if
   daemon's privilege scope changes.
6. **Schema migration ordering** — Phase 2 depends on Phase 1's
   `agent_preferences` schema for double-confirm thresholds; phases must merge
   in order.

## 15. Out of scope (explicit YAGNI)

- 4337 / smart-wallet bundling.
- Auto-execute by daemon (proposes only).
- ML/RL portfolio optimization.
- Tax-lot optimization.
- Live audit-NFT verification.
- Per-token reputation graph.
- User-tunable Sentinel rubric weights.
- Off-chain TWAP execution.
- Multi-user pooled rebalancing.
- DAG branching plans (linear only in v1).
- Auto-retry on hard failure (always user-confirmed).
- Gas-token auto-funding.
