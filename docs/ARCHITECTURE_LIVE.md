# Ilyon AI Sentinel — Live Architecture (May 2026 build)

> Public testing build. Report bugs to Telegram **@griffiniskid**.

This document supersedes the older `ARCHITECTURE.md` (which describes the
research roadmap). It captures the system actually deployed at
`staging.ilyonai.com` after the May 3–5 2026 fix train: typed agent cards,
Solana yield builder, full Sentinel chat surface, deterministic intent
routing, and rate-limit-aware data clients.

---

## 1. Conceptual model

Ilyon Sentinel is a single chat surface that lets a user do four things
without leaving the conversation:

1. **Understand any token, pool, wallet, or entity** with a Sentinel-grade
   risk read (rugcheck + holder distribution + liquidity + AI synthesis).
2. **Plan capital allocation** across yield protocols at a target risk and
   APY band, with constraint matching (chain, TVL, asset, slippage cap).
3. **Execute** that plan — same-chain swaps, cross-chain bridges, yield
   deposits, stakes — by signing real unsigned transactions in the user's
   wallet (Phantom for Solana, MetaMask for EVM).
4. **Track** smart-money flows, whale activity, entity tags, and shield
   risks (token approvals, drain exposure).

The orchestration layer is an agent. The agent picks tools deterministically
where it can (regex-based intent routing for clarity-critical asks like
"execute pool X") and drops to an LLM-driven ReAct flow for open-ended
research. Every tool returns a typed `ToolEnvelope` whose card payload is
rendered by the front-end as a structured component, not free-text.

### 1.1 Why a typed agent

Free-text answers about money are dangerous. A model that hallucinates a
DefiLlama pool ID, an APY, or a deposit address can move a user's funds
into a real loss. The Sentinel agent only ever returns:

- A `card_payload` whose schema is enforced by Pydantic (`ExecutionPlanV3`,
  `AllocationCard`, `SentinelMatrixCard`, `DefiOpportunitiesPayload`,
  `BalanceCard`).
- A textual `final.content` summarising the same data.

If a card cannot be built (missing data, blocked by Sentinel Shield, or
adapter doesn't cover the requested chain/protocol), an explicit
`ExecutionBlocker` is attached so the front-end never shows a fake "Sign
in wallet" button.

### 1.2 Trust boundaries

| Boundary | Untrusted | Trusted | Mitigation |
|---|---|---|---|
| User input | Free text | — | Deterministic regex pre-route, then schema-validated tool args |
| External data (Helius, Moralis, DefiLlama, RugCheck) | Provider response | — | `parse_assistant_json` + per-field defaults, rate-limit aware key rotators, Sentinel Shield checks before execution |
| Tool output | Tool return | Pydantic schema | All cards validated through `ToolEnvelope` before emit |
| Wallet signing | Front-end | User's wallet | All `UnsignedStepTransaction` payloads exposed for review before signature |

---

## 2. Service topology

The deployable unit on the staging VPS (`staging.ilyonai.com`) is a single
Docker Compose project named `ilyonai-staging`. Six containers:

```
                     ┌──────────────────────┐
                     │      Caddy           │
                     │ staging.ilyonai.com  │
                     └──────────┬───────────┘
                                │
                     ┌──────────┴───────────┐
                     │     web (Next.js)    │   :13000 → :3000
                     │  /agent/chat /api/*  │
                     └────┬─────┬─────┬─────┘
        rewrites          │     │     │
             ┌────────────┘     │     └─────────────┐
             ▼                  ▼                   ▼
      ┌───────────────┐  ┌──────────────────┐  ┌──────────────┐
      │  api (Sentinel│  │ assistant-api    │  │   redis      │
      │  aiohttp)     │  │ (FastAPI)        │  │ :6379        │
      │  :18080→:8080 │  │ chats / portfolio│  └──────────────┘
      └───────┬───────┘  └────────┬─────────┘
              │                   │
              ▼                   ▼
      ┌─────────────────────────────────┐
      │   postgres (shared)             │
      └─────────────────────────────────┘

      ┌─────────────────────────────────┐
      │ solana-yield-builder (sidecar)  │  internal :8090
      │ Node.js — Jupiter, Raydium,     │
      │ Orca, Meteora, Kamino,          │
      │ Marinade, Jito, Sanctum         │
      └─────────────────────────────────┘
```

| Service | Image / build context | Port | Responsibility |
|---|---|---|---|
| `web` | `web/` (Next.js 14) | 3000 → 13000 | UI, SSE consumer, wallet adapter, rewrites |
| `api` | repo root (Dockerfile) | 8080 → 18080 | Sentinel agent, analyzer, blinks, smart-money/whale/shield/entity routes |
| `assistant-api` | `IlyonAi-Wallet-assistant-main/` | 8000 (internal) | Persistent chat history, agent_chats DB, portfolio cache, RPC proxy |
| `solana-yield-builder` | `services/solana-yield-builder/` | 8090 (internal) | Per-protocol Solana adapters that emit signed-ready VersionedTransactions |
| `postgres` | `postgres:15-alpine` | 5432 (internal) | Persistent state (chats, blinks, entities, agent_preferences) |
| `redis` | `redis:7-alpine` | 6379 (internal) | Rate-limit & cache buckets |

`web/next.config.js` rewrites split traffic by path:

- `/api/v1/agent`, `/api/v1/agent-health` → `api`
- `/api/v1/chats/*`, `/api/v1/auth/*`, `/api/v1/rpc-proxy`, `/api/portfolio/*` → `assistant-api`
- All other `/api/*` → `api`

---

## 3. Sentinel API (`src/`)

### 3.1 Entry & lifespan

`src/main.py` boots the aiohttp app via `src/api/app.py`. Lifespan hooks
include `init_analyzer()` (constructs the singleton `TokenAnalyzer`),
`init_blink_service()`, and `init_rotators()` for Moralis keys.

### 3.2 Routes

| Route | File | Notes |
|---|---|---|
| `POST /api/v1/agent` | `src/api/routes/agent.py` | Streams SSE frames from `simple_runtime.run_simple_turn` (guest) or `runtime.run_turn` (auth) |
| `GET /api/v1/agent-health` | `src/api/app.py` | Liveness + feature flags |
| `POST /api/v1/blinks/create` | `src/api/routes/blinks.py` | Triggers full token analysis, persists Solana Action metadata |
| `GET /api/v1/blinks/{id}` | same | Returns Solana Actions metadata for Twitter unfurl |
| `GET /api/v1/blinks/{id}/icon.png` | same | Renders dynamic score icon |
| `GET /api/v1/whales` | `src/api/routes/whale.py` | Recent whale txs across chains |
| `GET /api/v1/smart-money/overview` | `src/api/routes/smart_money.py` | Top wallets, accumulations, conviction |
| `GET /api/v1/shield/{addr}` | `src/api/routes/shield.py` | Approvals + drain risk |
| `GET /api/v1/entities/{id}` | `src/api/routes/entity.py` | Entity profile |

### 3.3 Agent runtime — two paths

| Mode | Function | When | Persistence |
|---|---|---|---|
| Guest | `simple_runtime.run_simple_turn` | No wallet / no auth | None — single SSE stream |
| Authenticated | `runtime.run_turn` | wallet + auth cookie | `agent_chats` schema |

Both paths share the same tool registry from
`src.agent.tools.register_all_tools()` and emit identical SSE frames:

```
event: thought       — narrated reasoning step
event: tool          — tool call with args
event: observation   — tool result (ok/error)
event: card          — typed card payload (rendered as a component)
event: final         — text answer + linked card_ids + elapsed_ms
event: done          — terminator
```

### 3.4 Intent routing

`simple_runtime.detect_intent()` runs deterministic detectors **before**
any LLM call. First match wins:

1. `_detect_bridge_then_stake` (multi-step bridge → stake)
2. `_detect_aave_supply` / `_detect_swap_then_lp` /
   `_detect_stake_amount_plan` / `_detect_malicious_swap_plan` /
   `_detect_transfer_plan`
3. `_detect_sentinel_chat_tools` (analyze_token, analyze_pool,
   whale_track, smart_money_hub, shield_check, lookup_entity)
4. `_detect_pool_execute` (`execute_pool_position` when concrete pool ref
   present in message)
5. `_defi_intent_to_tool` (search/allocate)
6. `INTENT_PATTERNS` regex fallback

If nothing matches the runtime drops to "contextual reasoning mode"
(LLM-only) with a Sentinel-style risk-aware system prompt.

### 3.5 Tool registry

| Tool | File | Returns |
|---|---|---|
| `get_wallet_balance` | `tools/wallet_balance.py` | `BalanceCard` with flat `tokens[]` + `by_chain{}` |
| `get_token_price` | `tools/price.py` | `PriceCard` |
| `simulate_swap` / `build_swap_tx` | `tools/swap_*.py` | `ExecutionPlanV3` (EVM via Enso) |
| `build_solana_swap` | `tools/solana_swap.py` | `ExecutionPlanV3` (Solana via Jupiter) |
| `build_bridge_tx` | `tools/bridge_build.py` | `ExecutionPlanV3` (deBridge) |
| `build_stake_tx` / `build_deposit_lp_tx` | `tools/stake_build.py`, `tools/lp_build.py` | `ExecutionPlanV3` |
| `build_transfer_tx` | `tools/transfer_build.py` | `ExecutionPlanV3` |
| `allocate_plan` | `tools/allocate_plan.py` | `AllocationCard` + `SentinelMatrixCard` + `ExecutionPlanV3` |
| `compose_plan` | `tools/compose_plan.py` | `ExecutionPlanV2` |
| `rebalance_portfolio` | `tools/rebalance_portfolio.py` | `ExecutionPlanV2` |
| `build_yield_execution_plan` | `tools/build_yield_execution_plan.py` | `ExecutionPlanV3` |
| `build_yield_strategy_plan` | `tools/build_yield_strategy_plan.py` | `ExecutionPlanV3` (multi-step) |
| **`execute_pool_position`** (new) | `tools/execute_pool_position.py` | `ExecutionPlanV3` from a DefiLlama pool ref |
| `search_defi_opportunities` | `tools/search_defi_opportunities.py` | `DefiOpportunitiesPayload` |
| `get_defi_market_overview` / `get_defi_analytics` / `get_staking_options` / `find_liquidity_pool` / `search_dexscreener_pairs` | `tools/*` | Domain-specific cards |
| `analyze_token_full_sentinel` | `tools/sentinel_features.py` | Token analyzer report |
| `analyze_pool_full_sentinel` | same | DefiLlama pool report |
| `track_whales` | same | Whale feed |
| `get_smart_money_hub` | same | Hub overview |
| `get_shield_check` | same | Shield report |
| `lookup_entity` | same | Entity profile |
| `update_preference` | `tools/update_preference.py` | `agent_preferences` row |

### 3.6 Adapter registry (yield execution)

`src/defi/execution/capabilities.py::build_default_registry()` priority:

1. **`AaveV3Adapter`** — `chain×asset` matrix for ETH/Polygon/Arbitrum/Base
2. **`CompoundV3Adapter`** — Comet markets with usd_human handling
3. **`Erc4626Adapter`** — generic vault action
4. **`EnsoShortcutAdapter`** — universal EVM yield catch-all (Yearn,
   Beefy, Curve, Convex, Pendle, Lido, RocketPool, Stargate, EtherFi,
   Stader, Morpho, Ondo, Sky, USDe, Frax, Mantle)
5. **`SolanaYieldBuilderAdapter`** — HTTP client to Node sidecar for
   Kamino / Orca / Meteora / Raydium / Marinade / Jito / Sanctum / Drift
6. **`WalletAssistantAdapter`** — fallback to legacy
   `IlyonAi-Wallet-assistant-main` swap/stake builders

`registry.find()` returns `CapabilityResult`. If unsupported the calling
tool emits an `ExecutionBlocker` instead of silently failing.

### 3.7 Sentinel scoring & shielding

- `src/core/scorer.py` blends rug-prob, LP-lock, contract-renounce,
  liquidity, and the AI router verdict into a 0–100 score.
- `src/agent/tools/sentinel_wrap.py::enrich_tool_envelope` attaches a
  `ShieldBlock` to every tool envelope. Critical Shield findings short-
  circuit the runtime (`PlanBlockedFrame` instead of a final).

### 3.8 Data sources

| Source | Client | Key handling |
|---|---|---|
| Helius (Solana RPC + holders) | `src/data/solana.py::SolanaClient` | Single key (env `HELIUS_API_KEY`); falls back to **no** public RPC when configured (avoids 429 storms on huge mints like WSOL) |
| Moralis (EVM balances, token meta) | `src/data/moralis.py::MoralisClient` | `MoralisKeyRotator` — round-robin pool, 60s exponential cooldown on 429, permanent invalidation on 401 |
| DefiLlama (pools, protocols) | inline `aiohttp` | Public, no key |
| RugCheck | `src/data/rugcheck.py` | Public, defensive None handling for `markets`/`risks`/`lockerOwners` |
| DexScreener | `src/data/dexscreener.py` | Public |
| Jupiter | sidecar `jupiter.js` | Public |
| Enso | `src/routing/enso_client.py` | `ENSO_API_KEY` |

#### 3.8.1 Moralis key rotator

`src/data/moralis_rotator.py::MoralisKeyRotator` — thread-safe round-robin
pool. On 429 → `mark_rate_limited` (exponential backoff 60s × 2^n cap
600s). On 401/403 → `mark_invalid` (permanent quarantine). Loaded from
`MORALIS_API_KEYS` (comma-separated) with legacy fallback to
`MORALIS_API_KEY`. Validated under load: bad-key + good-key pool returned
1727 tokens after the bad key was marked invalid on first 401.

### 3.9 Solana yield-builder sidecar

Node service exposes `POST /quote`, `POST /build`, `POST /verify`. Each
adapter under `services/solana-yield-builder/src/adapters/` returns a
base64 `VersionedTransaction` ready for
`phantom.signAndSendTransaction()`.

The Raydium adapter refuses to build a no-op USDC→USDC swap when no
`extra.lpMint` is provided — it raises explicitly so the caller surfaces
"this pool needs an LP mint" instead of relaying a Jupiter `Same mint`
400.

---

## 4. Web UI (`web/`)

Next.js 14 app router. Single primary surface at `/agent/chat` rendered
by `web/components/agent-app/MainApp.tsx`. The component:

- Maintains `messages[]` with role, ts, optional `agentCards`,
  `universalCards`, `reasoning`, `liveSteps`.
- Pushes a streamed SSE response from the `/api/v1/agent` rewrite.
- Decodes events into `ParsedAgentSseResponse` and dispatches:
  - **Cards** → `CardRenderer` switches on `card_type` and picks a
    component (`AllocationCard`, `SentinelMatrixCard`,
    `ExecutionPlanV3Card`, `DefiOpportunitiesCard`, etc.).
  - **Reasoning steps** → `LiveReasoningStep` strip with streamed thoughts.
  - **Final** → message bubble + links to card payloads.

### 4.1 Wallet adapter

`MainApp` calls `phantom.signAndSendTransaction` (Solana) or
`metamask.sendTransaction` (EVM) when the user clicks **Start signing**
on an `ExecutionPlanV3Card`. Each step's `UnsignedStepTransaction` is the
source of truth — base64 for Solana, `{to, data, value, chainKind:"evm"}`
for EVM.

### 4.2 Card → chat bridge

`DefiOpportunitiesCard` rows render a per-row **Execute** button. The
button dispatches `CustomEvent("ilyon:execute-pool", { detail: {pool, item, message} })`.
`MainApp` mounts a window listener that calls `send(message)` —
re-entering the same agent pipeline with a deterministic
`execute_pool_position pool="…" amount=100` message. Avoids prop drilling
through the card hierarchy.

### 4.3 Public-testing banner

A persistent strip above the `LIVE NOW` chip:

> ⚠️ Public testing — report bugs to Telegram **@griffiniskid**

Lives in `MainApp.tsx` as `.public-testing-banner`.

---

## 5. Wallet assistant (`IlyonAi-Wallet-assistant-main/`)

FastAPI service that owns:

- **Chat persistence** (`/api/v1/chats/*`) — agent_chats schema with
  message history, card snapshots, plan_completions.
- **Auth** (`/api/v1/auth/*`) — wallet-signature login.
- **Portfolio** (`/api/portfolio/{addr}`) — multi-chain balance aggregation
  using Moralis (EVM) and Helius (Solana).
- **RPC proxy** (`/api/v1/rpc-proxy`) — front-end-safe RPC fan-out.
- **Bridge status** (`/api/v1/bridge-status/*`) — deBridge tx monitoring.

The Sentinel `wallet_balance` tool calls
`crypto_agent.get_smart_wallet_balance` from this service and flattens
the provider's `balance_report` shape into the strict `BalanceCard`
payload the chat surface expects (`tokens[]` flat with chain/symbol/
amount/usd, `by_chain{}` map per chain).

---

## 6. Feature catalogue

### 6.1 Token analysis
- **Trigger**: "analyze token X", "is this contract safe", paste mint/0x.
- **Path**: `analyze_token_full_sentinel` → `TokenAnalyzer.analyze` →
  DexScreener + Helius + RugCheck + scraper + AI router → score + grade
  + risk flags.

### 6.2 Pool analysis
- **Trigger**: "analyze pool X", "stats for raydium-amm SPACEX-WSOL".
- **Path**: `analyze_pool_full_sentinel` → DefiLlama `/pools` → APY/TVL/
  IL-risk, predicted-class, underlying tokens.

### 6.3 Pool execution (one-click)
- **Trigger**: "execute pool X", "deposit into raydium-amm SPACEX-WSOL",
  Execute button on a row in `DefiOpportunitiesCard`.
- **Path**: deterministic regex → `execute_pool_position` →
  `_fetch_pool_meta` (DefiLlama) → adapter registry → unsigned tx →
  `ExecutionPlanV3Card` with **Sign in Phantom** / **Sign in MetaMask**.
- **Validated end-to-end**: returns base64 VersionedTransaction for
  Raydium AMM; `ExecutionPlanV3` card with `chain_kind:"solana"`,
  `wallet:"Phantom"`, action `deposit_lp`.

### 6.4 Allocation planner
- **Trigger**: "Allocate $1000 across balanced yield strategies".
- **Path**: `allocate_plan` → top-5 ranked positions, weighted Sentinel
  score, blended APY, 5-tx execution plan with approvals + supplies.
- **Cards**: `AllocationCard` + `SentinelMatrixCard` +
  `ExecutionPlanV3Card`.

### 6.5 Bridge
- **Trigger**: "Bridge 50 USDC from Base to Solana".
- **Path**: `build_bridge_tx` → deBridge unsigned tx →
  `ExecutionPlanV3Card`.

### 6.6 Same-chain swap
- **Trigger**: "swap 0.2 SOL → USDC".
- **Path**: `simulate_swap` → `build_swap_tx` (EVM via Enso) /
  `build_solana_swap` (Solana via Jupiter) → `ExecutionPlanV3Card`.

### 6.7 Whale tracker / smart-money hub / entity / shield
- **Triggers**: "whale activity in last 6h", "Solana smart-money hub",
  "who is X", "shield this address …".
- **Path**: deterministic detectors in `_detect_sentinel_chat_tools` →
  respective tools.

### 6.8 Blinks
- **Trigger**: `POST /api/v1/blinks/create` with a token address.
- **Path**: full `TokenAnalyzer.analyze(mode="quick")` → `BlinkService`
  persists a row + builds Solana Actions metadata + dynamic icon.
- **Output**: `https://staging.ilyonai.com/blinks/{id}` for Twitter
  unfurling, `/api/v1/blinks/{id}` for the Action JSON, `/icon.png` for
  the score icon.

### 6.9 Preferences
- **Trigger**: "set my slippage to 30 bps", "low-risk only".
- **Path**: `update_preference` writes the `agent_preferences` row used
  by `allocate_plan`, `rebalance_portfolio`, and
  `search_defi_opportunities` to bound their outputs.

---

## 7. Single-turn data flow

```
1. User types in <textarea>; presses Enter.
2. MainApp.send(text) POSTs to /api/v1/agent (rewritten to api:8080).
3. SSE stream opens. Frames stream live.
4. detect_intent(message) runs deterministic detectors first.
5. If a tool matches:
   a. Tool is invoked with structured args.
   b. Tool returns ToolEnvelope (or ExecutionPlanV3 / blocker).
   c. enrich_tool_envelope attaches Sentinel + Shield blocks.
   d. CardFrame yielded; FinalFrame yielded; DoneFrame yielded.
6. Else: LLM ReAct loop with the tool list as descriptors.
7. Front-end accumulates frames, materialises typed cards, and the
   message bubble shows the final.
```

---

## 8. Local development

```bash
# Boot the merged stack (api :8080, assistant-api :8000, web :3030)
cd /home/griffiniskid/Documents/ai-sentinel-restore-d364b1a
./run-merged.sh
```

Required env (loaded from `.env` at repo root or `deploy/staging/app.env`
on the VPS):

- `OPENROUTER_API_KEY`, `GEMINI_API_KEY`, `GROK_API_KEY`
- `HELIUS_API_KEY` (current: `2c3e923c-21f0-4e75-8017-6e45ecf6863a`)
- `MORALIS_API_KEYS` (comma-separated for the rotator)
- `JUPITER_API_KEY`, `ENSO_API_KEY`
- `DATABASE_URL`, `REDIS_URL`

---

## 9. Deployment

Staging: `staging.ilyonai.com`, served by Caddy reverse-proxying to the
`web` container on port 13000.

```bash
# 1) Push to staging branch
git push origin staging

# 2) On VPS aisentinel@173.249.5.167
cd ~/ai-sentinel-staging
git fetch && git reset --hard origin/staging
docker compose up -d --build --force-recreate api web assistant-api

# 3) Sidecar (separate compose project, build manually)
cd services/solana-yield-builder
docker build -t ilyonai-staging-solana-yield-builder .
docker restart ilyonai-staging-solana-yield-builder-1
```

Health probes:

- `https://staging.ilyonai.com/api/v1/agent-health` → `{status:"healthy"}`
- `docker exec ilyonai-staging-solana-yield-builder-1 wget -qO- http://localhost:8090/health`

---

## 10. Known limits & rough edges

- **Cold blink creation** takes ~2 minutes (full analyzer pipeline). Caddy
  default proxy timeout (60s) returns 502 on the first call, but the
  back-end completes; second call hits the cache and returns instantly.
  Fix pending: bump `transport http { read_timeout 240s }` in the staging
  Caddyfile (requires VPS sudo).
- **Bridge → pool combo** in a single utterance ("bridge X to Solana then
  deposit raydium-amm Y") is not deterministically routed yet; the LLM
  composes the plan, which can be slow. A dedicated detector is on the
  roadmap.
- **Solana RPC fallback** for token holder fetches on huge mints (WSOL)
  returns `[]` instead of going to the public RPC (which 429s within
  seconds). Deliberate trade-off — empty holders ≠ failure.
- **Entity directory** is sparse. Looking up a name (e.g. "binance") that
  isn't in the curated address book returns a graceful empty-state, not
  an error.
