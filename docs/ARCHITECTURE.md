# Ilyon AI — System Architecture

> **Status:** Living document. Reflects the codebase as of commit `a5b5d19` (whale-feed zero-credit pipeline) and integrates the direction set by `defi-intelligence-roadmap.md`, `ai-agent-integration.md`, and the staged Helius webhook upgrade.

This document is the canonical, advanced view of Ilyon AI. It is organized so a new engineer can understand:

1. **What the product is** — the conception, the core domain objects, and the value surface
2. **How the system is built today** — runtime topology, module layout, request/data flows
3. **Where it is going** — the concrete, merged roadmap for the DeFi intelligence surface, the Agent Platform merge, and real-time streaming upgrades
4. **The invariants** — the cross-cutting rules (singletons, CORS, auth, scoring) that keep the system coherent

The `README.md` remains the public-facing product description. This document is the internal architectural reference.

---

## 1. Product Conception

### 1.1 What Ilyon AI is

Ilyon AI is an **AI-powered multi-chain DeFi intelligence platform** centered on Solana with coverage across the major EVM chains (Ethereum, Base, BSC, Arbitrum, Polygon, Optimism, Avalanche).

It is organized around three user outcomes:

| Outcome | What the user gets | Primary surfaces |
|---|---|---|
| **Pre-trade intelligence** | Risk assessment before buying a token | `/token/[address]`, `/contract`, `/pool/[id]`, Blinks |
| **Capital allocation intelligence** | Rank, compare, and stress-test DeFi opportunities | `/defi`, `/defi/opportunity/[id]`, `/defi/protocol/[slug]`, `/defi/compare`, `/defi/lending` |
| **Flow & counterparty intelligence** | See what smart money, whales, and deployers are doing | `/smart-money`, `/whales`, entity/wallet forensics |

### 1.2 Core domain objects

These are the primary entities the system is built to reason about:

- **`token`** — an asset on a chain. Always keyed by `(chain, address)`. Carries market data, on-chain data, holder distribution, authorities, LP status, and an AI-assessed safety score.
- **`protocol`** — a DeFi protocol (Jupiter, Raydium, Aave, etc.). Carries quality, incident history, audits, deployment breadth, governance posture, operational confidence.
- **`opportunity`** — a deployable action tied to a protocol: a pool, a farm, or a lending setup. Has explicit score breakdowns and a scenario profile.
- **`wallet` / `entity`** — an address or a cluster of addresses. Carries deployer history, serial-scammer flags, smart-money classification, and flow direction.
- **`scenario`** — a thesis-breaking state for an opportunity or token: what must be monitored, what changes the allocation.
- **`event`** — a significant on-chain occurrence: whale swap, incident, authority change, LP unlock. Events power feeds and future alerting.

### 1.3 Design principles

1. **AI score is the primary metric, evidence is the receipts.** The safety score is composite-AI-led but every contributing signal must be retrievable.
2. **Graceful degradation beats feature flags.** When Helius is down, we fall back to raw RPC; when AI is down, we emit deterministic scores with a confidence marker.
3. **The user's wallet is their identity.** No email, no password. Auth is signature-based for Solana wallets and will extend to MetaMask/Phantom-EVM.
4. **Never hold user keys.** All transaction builders produce unsigned payloads; the client signs.
5. **Parallelize data collection, serialize decisions.** Data providers fan out in parallel; scoring and AI judgment sit at a deterministic merge point.
6. **Cache has a TTL, truth has a timestamp.** Every cached blob carries a `fetched_at`; anything older than TTL is re-fetched before it informs a decision.

---

## 2. Runtime Topology

### 2.1 The three processes

```
┌──────────────────────────────┐       ┌──────────────────────────────┐
│  Next.js 15 Frontend (web/)  │──────▶│  Python aiohttp API (src/)   │
│  - App Router                │  HTTP │  - Analysis engine           │
│  - Solana wallet adapter     │  WS   │  - DeFi intelligence engine  │
│  - React Query / Toast       │       │  - Whale stream + stream hub │
└──────────────────────────────┘       │  - Public API / auth         │
                                       │  - Sentinel agent loop       │
                                       └──────────────────────────────┘
                                                    │
                                       ┌────────────┴─────────────┐
                                       ▼                          ▼
                               ┌──────────────┐          ┌─────────────────┐
                               │  PostgreSQL  │          │  External data  │
                               │ (SQLAlchemy  │          │  Helius / RPC   │
                               │   async)     │          │  DexScreener    │
                               │              │          │  Jupiter        │
                               │  + Redis     │          │  RugCheck       │
                               │  (optional   │          │  DefiLlama      │
                               │   cache)     │          │  Moralis        │
                               └──────────────┘          │  CoinGecko      │
                                                         │  OpenAI / Grok  │
                                                         │    via router   │
                                                         └─────────────────┘
```

Entry points:

- **Backend:** `src/main.py` → `create_api_app()` (`src/api/app.py`) → aiohttp on port `settings.web_api_port`.
- **Frontend:** `web/app/layout.tsx` wrapped by `web/components/providers.tsx` (QueryClient, Solana wallet adapter, ToastProvider).
- **Bot / chat surfaces:** Telegram bot, documented separately in `docs/BOT_API_REFERENCE.md` and `docs/BOT_INTEGRATION_GUIDE.md`.

### 2.2 Lifecycle

`src/main.py` registers two lifecycle hooks on the aiohttp app:

- **`on_startup`:**
  1. `init_database()` — opens the SQLAlchemy async engine and schema-checks.
  2. `init_cache()` — connects Redis if configured; falls back to in-process caches otherwise.
  3. **Whale feed** — honors `settings.whale_feed_mode`:
     - `"stream"` → `WhaleTransactionStream` over `logsSubscribe` (default, zero-credit pipeline)
     - otherwise → `WhaleTransactionPoller` (legacy safety net)
  4. Sentinel agent (`src/agents/sentinel.py`) is started per configuration.
  5. Analyzer is lazily initialized via `init_analyzer()` on first `/analyze` request and cached on `app['analyzer']`.

- **`on_cleanup`:** Cancels the whale feed task, closes the DB engine.

### 2.3 Middleware chain

In order (see `src/api/app.py`):

1. **`cors_middleware`** (`src/api/middleware/cors.py`) — the **only** place CORS headers are added. Route handlers never emit CORS headers directly.
2. **`rate_limit_middleware`** — per-IP token bucket.
3. **`auth_middleware`** — optional wallet-signature verification for authenticated routes.
4. **Route handlers** — grouped by concern.

> **Invariant:** CORS must include every public path prefix. A prior bug limited permissive `*` origin to `/actions/` and `/blinks/` while real API routes sit at `/api/v1/*`. If you add a new public prefix, update `cors_middleware`.

---

## 3. Backend Module Map

All backend code lives under `src/`. Each subpackage has a single responsibility; cross-package dependencies flow *downward* (routes → core → data/chains/ai → storage).

### 3.1 Entry and orchestration

| Path | Role |
|---|---|
| `src/main.py` | Process entry, lifecycle hooks. |
| `src/config.py` | Pydantic settings loaded from `.env`. Single source of configuration. |
| `src/api/app.py` | aiohttp `Application` factory, route wiring, middleware order. |
| `src/agents/sentinel.py` | Long-lived background "sentinel" agent (monitoring, periodic work). |

### 3.2 HTTP surface (`src/api/`)

Routes are registered via `setup_*_routes(app)` functions. Current routes:

| Path prefix | File | Purpose |
|---|---|---|
| `/health`, `/api/v1` | `api/app.py` | Liveness + API metadata |
| `/api/v1/analyze` | `routes/analysis.py` | Token analysis orchestration |
| `/api/v1/blinks`, `/actions`, `/blinks` | `routes/blinks.py`, `routes/actions.py` | Solana Actions / Blinks spec |
| `/api/v1/trending` | `routes/trending.py` | Trending feeds |
| `/api/v1/portfolio` | `routes/portfolio.py` | Multi-wallet portfolio |
| `/api/v1/transactions`, `/api/v1/whale`, `/api/v1/whales/leaderboard` | `routes/transactions.py`, `routes/whale.py`, `routes/whale_leaderboard.py` | Whale flow + leaderboard |
| `/api/v1/smart-money` | `routes/smart_money.py` | Smart-money aggregation |
| `/api/v1/wallet-intel`, `/api/v1/entity` | `routes/wallet_intel.py`, `routes/entity.py` | Wallet forensics, entity clustering |
| `/api/v1/chains` | `routes/chains.py` | Chain metadata |
| `/api/v1/contracts` | `routes/contracts.py` | EVM contract scanner |
| `/api/v1/defi/*`, `/api/v2/defi/*` | `routes/defi.py` | DeFi intelligence (v2 is the advanced surface) |
| `/api/v1/opportunities` | `routes/opportunities.py` | Opportunity catalog |
| `/api/v1/intel` | `routes/intel.py` | REKT context, advisories |
| `/api/v1/shield` | `routes/shield.py` | Approval scanner |
| `/api/v1/alerts` | `routes/alerts.py` | Alert subscriptions |
| `/api/v1/stream` | `routes/stream.py` | SSE/WebSocket fan-out |
| `/api/v1/auth`, `/api/v1/stats` | `routes/auth.py`, `routes/stats.py` | Session + counters |
| `/api/v1/public/*` | `public_api/router.py` | Public API with API-key auth + webhooks |

**Service layer:** `src/api/services/` holds cross-route business logic — `blink_service.py`, `icon_generator.py` — exposed via singleton getters.

### 3.3 Analysis engine (`src/core/`)

The heart of token intelligence.

| File | Role |
|---|---|
| `core/analyzer.py` | Orchestrator. Fans out to data providers in parallel, hands aggregated evidence to the scorer and AI router, returns `TokenAnalysis`. |
| `core/scorer.py` | Risk-scoring logic. Converts raw signals into component scores and the final 0–100 grade with hard caps. |
| `core/models.py` | `TokenInfo`, `TokenAnalysis`, `Evidence`, and related Pydantic/dataclass models. |

The analyzer is lifecycle-initialized via `init_analyzer()` in `src/api/routes/analysis.py` and stored as `app['analyzer']` to avoid repeated construction.

### 3.4 Data providers (`src/data/`)

One module per external source. Each exposes an async client with caching, retry, and circuit-breaker hooks. Adding a new provider is a four-step operation:

1. Create `src/data/<provider>.py` implementing the client.
2. Add the provider to the parallel fan-out in `core/analyzer.py`.
3. Extend `TokenInfo` in `core/models.py` if new fields are needed.
4. Extend the AI prompt in `src/ai/prompts/` so the new evidence is considered.

Current providers: `dexscreener`, `jupiter`, `rugcheck`, `honeypot`, `solana`, `solana_log_parser`, `moralis`, `coingecko`, `defillama`, `goplus`, `scraper`, `token_filters`.

### 3.5 Chain clients (`src/chains/`)

Chain-aware utilities; today's primary surface is `chains/solana/` (Helius + raw RPC with graceful fallback) and `chains/address.py` (multi-chain address parsing / chain auto-detection).

### 3.6 AI layer (`src/ai/`)

| File | Role |
|---|---|
| `ai/router.py` | Multi-model routing (OpenAI, Grok via OpenRouter). Chooses a model based on task, cost, and availability. |
| `ai/base.py` | Common client interface. |
| `ai/openai_client.py`, `ai/grok_client.py` | Concrete model clients. |
| `ai/prompts/` | Prompt templates (token analysis, contract analysis, DeFi judgment). |
| `ai/chat/` | Chat-shaped interactions (used by the bot, and in the future by the Agent Chat surface). |

### 3.7 DeFi intelligence (`src/defi/`)

This is the most actively evolving backend subsystem. Built as a facade over several engines:

```
intelligence_engine.py       ← thin facade; stable public API
   └── opportunity_engine.py ← ranks opportunities with scenario + AI context
         ├── risk_engine.py
         ├── scenario_engine.py
         ├── evidence.py / history_store.py / docs_analyzer.py
         ├── ai_router.py / ai_explainer.py   ← AI judgments + fallback narratives
         ├── entities.py                      ← protocol/opportunity/scenario models
         └── opportunity_taxonomy.py
```

Supporting pipeline:

- `defi/pipeline/` — `scan`, `enrich`, `synthesize`, `coalescing`, `budgets` (credit/cost caps).
- `defi/scoring/` — `deterministic.py` (pure-Python scoring), `ai_judgment.py` (AI-graded signals), `final_ranker.py`, `archetypes/`, `factors/`.
- `defi/assemblers/` — payload builders for the v2 routes.
- `defi/stores/` — `analysis_store.py`, `evidence_store.py` (currently in-memory, slated for persistence).
- `defi/pool_analyzer.py`, `farm_analyzer.py`, `lending_analyzer.py` — domain-specific analyzers.
- `defi/observability.py` — timing and cost counters for the pipeline.

**Scoring model (opportunity):** 45 % safety · 30 % yield quality · 15 % exit quality · 10 % confidence. Protocol score inputs: contract safety, incident history, market maturity, governance/admin posture, confidence + evidence coverage.

### 3.8 Streaming & platform (`src/platform/`, `src/services/`)

A small internal platform layer used by feeds and the public API:

| File | Role |
|---|---|
| `platform/event_bus.py` | In-process pub/sub. |
| `platform/stream_hub.py` | Fan-out hub for WebSocket/SSE clients; shared between whale feed and alerts. |
| `platform/circuit_breaker.py`, `retry.py`, `dead_letter_queue.py` | Resilience primitives for provider calls. |
| `platform/precompute.py` | Scheduled precomputations (e.g. leaderboards). |
| `platform/contracts.py` | Shared DTOs on the platform boundary. |
| `services/whale_stream.py` | Helius `logsSubscribe`-based whale pipeline (default). |
| `services/whale_poller.py` | Legacy polling pipeline, kept as a safety-net backfill. |

### 3.9 Analytics & intel (`src/analytics/`, `src/intel/`, `src/smart_money/`, `src/shield/`, `src/quality/`)

| Subpackage | Role |
|---|---|
| `analytics/wallet_forensics.py` | Deployer and serial-scammer tracking. |
| `analytics/anomaly_detector.py`, `behavior_signals.py`, `behavior_adapters/`, `signal_models.py`, `time_series.py` | Behavioral anomaly detection. |
| `intel/rekt_database.py` | Hack/exploit incident lookup. |
| `smart_money/graph_store.py`, `profile_service.py`, `normalizer.py`, `models.py` | Smart-money graph and wallet profiling. |
| `shield/approval_scanner.py` | EVM approval-risk scanner. |
| `quality/feedback_store.py`, `replay_evaluator.py`, `heuristic_weights.py` | Quality/feedback loop used to tune heuristics. |

### 3.10 Storage (`src/storage/`)

| File | Role |
|---|---|
| `storage/database.py` | SQLAlchemy async engine + ORM models. Exposed via `get_database()` singleton. |
| `storage/cache.py` | Redis-backed cache; degrades to in-process dict when Redis is unconfigured. |

> **Invariant:** Database methods silently no-op and return `None` when `_initialized=False`. Any caller relying on persisted state must check initialization explicitly.

### 3.11 Public API (`src/public_api/`)

| File | Role |
|---|---|
| `public_api/router.py` | `/api/v1/public/*` routes with API-key auth. |
| `public_api/auth.py` | API-key issuance and validation. |
| `public_api/webhooks.py` | Outbound webhook dispatcher (upcoming: inbound Helius webhook handler). |

### 3.12 Monetization & growth

- `src/monetization/affiliates.py` — affiliate-fee hooks; will pair with the Agent Platform's Foundry contracts for PancakeSwap Infinity after merge.
- `src/growth/` — growth-loop scaffolding (referrals, etc.).

---

## 4. Frontend Architecture

### 4.1 Framework

Next.js 15 App Router, TypeScript, React Query for server state, Tailwind for styling, Solana wallet adapter for identity. Dev server runs on `http://localhost:3000` and proxies to the backend at `NEXT_PUBLIC_API_URL`.

### 4.2 Route map

```
web/app/
├── page.tsx            — landing / overview
├── layout.tsx          — providers wrap
├── dashboard/          — market + ecosystem overview
├── trending/           — trending / gainers / losers / new pairs
├── token/[address]/    — token analysis deep-dive
├── contract/           — EVM contract scanner
├── pool/[id]/          — pool analysis
├── smart-money/        — smart money hub
├── whales/             — whale tracker (leaderboard + feed)
├── portfolio/          — multi-wallet portfolio
├── defi/               — DeFi discover (advanced)
│   ├── opportunity/[id]/
│   ├── protocol/[slug]/
│   ├── compare/
│   └── lending/        — lending + stress simulation
├── shield/             — approval scanner (EVM)
├── entity/             — entity / wallet intel
├── agent/
│   ├── chat/           — AI Chat (preview plug → Phase 2)
│   └── swap/           — AI Swap (preview plug → Phase 4)
├── docs/               — in-app docs
└── settings/           — wallet + session settings
```

### 4.3 Providers (`web/components/providers.tsx`)

Wraps the app in, in order:

1. **QueryClient** — React Query.
2. **ConnectionProvider / WalletProvider / WalletModalProvider** — `@solana/wallet-adapter`.
3. **ToastProvider** — in-tree toast registry.

> **Invariants:**
> - `useToast()` only works inside `ToastProvider`; without it the hook falls back to `console.log`. The `<Toaster />` component is a no-op; actual rendering is done by `ToastProvider`.
> - Global singletons are accessed via named getters (`get_blink_service()`, `get_database()`, `get_icon_generator()`) — never instantiate directly.

### 4.4 Feature flags

`web/lib/feature-flags.ts` reads `NEXT_PUBLIC_COMING_SOON`. When `true`, Shield, Audits, REKT Database, Alerts, Entity Explorer, and Agent preview pages show "Coming Soon" placeholders instead of live functionality.

The Agent Chat and Agent Swap pages are **always** in preview today (static mockups). They ship with a `Preview · Coming Soon` banner and will be replaced per the Agent Platform roadmap (§6).

---

## 5. Request & Data Flows

### 5.1 Token analysis (`GET /api/v1/analyze/{address}`)

```
Client
  │
  ▼  HTTP GET
api/routes/analysis.py
  │
  ▼  uses app['analyzer']
core/analyzer.py
  │
  ├─► Parallel fan-out
  │     ├── data/dexscreener.py         (price, liquidity, volume, pair age)
  │     ├── chains/solana + Helius      (authorities, holders, on-chain meta)
  │     ├── data/rugcheck.py            (LP lock, bundled launch)
  │     ├── data/jupiter.py             (swap simulation, effective sell tax)
  │     ├── data/scraper.py             (website: domain age, SSL, socials)
  │     ├── analytics/wallet_forensics  (deployer history)
  │     ├── analytics/anomaly_detector  (volume/price divergence)
  │     └── data/honeypot.py            (EVM honeypot check)
  │
  ├─► core/scorer.py                    (component scores, hard caps)
  ├─► ai/router.py → ai/openai_client.py + ai/grok_client.py
  └─► Cache (storage/cache.py) with TTL
       │
       ▼
   TokenAnalysis → JSON response
```

The AI score is the headline. Component scores are exposed for transparency. Hard caps override the score for known scammers and confirmed honeypots.

### 5.2 DeFi opportunity discovery (`GET /api/v2/defi/discover`)

```
Client
  │
  ▼
api/routes/defi.py
  │
  ▼
defi/intelligence_engine.py  (facade)
  │
  ▼
defi/opportunity_engine.py
  │
  ├─► defi/pipeline/scan.py         (candidate pools/farms/lending)
  ├─► defi/pipeline/enrich.py       (per-opportunity evidence fetch)
  │     ├── data/defillama.py
  │     ├── defi/pool_analyzer.py / farm_analyzer.py / lending_analyzer.py
  │     └── defi/docs_analyzer.py
  ├─► defi/risk_engine.py + scenario_engine.py
  ├─► defi/scoring/deterministic.py + ai_judgment.py → final_ranker.py
  ├─► defi/ai_router.py + ai_explainer.py   (AI brief + per-opportunity narrative)
  └─► defi/stores/*                 (analysis + evidence, in-memory today)
       │
       ▼
   Ranked opportunities + scorecards + market brief → JSON
```

Simulation routes (`POST /api/v2/defi/simulate/lp`, `.../simulate/lending`, `.../positions/analyze`) reuse the same engines against user-supplied parameters instead of the scan output.

### 5.3 Whale flow (real-time)

**Today (zero-credit pipeline, default):**

```
Helius RPC WebSocket (logsSubscribe on DEX programs)
  │
  ▼
services/whale_stream.py
  │
  ├─► data/solana_log_parser.py        (decode swap events)
  ├─► data/token_filters.py            (alpha-token filter, noise drop)
  ├─► metadata enrichment (Helius DAS + RPC; zero credits)
  ├─► persist → storage/database.py    (whale_transactions table)
  └─► broadcast → platform/stream_hub.py
                  │
                  ▼
          SSE / WS clients on /api/v1/stream
          +  /whales, /smart-money React Query subscribers
```

Fallback: `services/whale_poller.py` activates when `settings.whale_feed_mode != "stream"` or the stream task crashes. Poller uses the same persist → broadcast interface, so downstream consumers are mode-agnostic.

**Stream status indicators in the UI:** `Live` (WS connected), `Reconnecting` (WS retrying), `Polling` (HTTP fallback).

### 5.4 Auth (wallet signature)

```
Client → GET  /api/v1/auth/challenge           → nonce
Client signs nonce with connected wallet
Client → POST /api/v1/auth/verify              → session token (HttpOnly cookie or bearer)
Authenticated routes → auth middleware validates session
```

Multi-wallet support (MetaMask, Phantom-EVM) is a Phase 1 merge item; unified challenge flow will treat each verifier as an alternative path, not a separate endpoint.

---

## 6. Roadmap — the system in motion

Three major initiatives are merging into the codebase. This section is the canonical source for how they land.

### 6.1 DeFi intelligence — advanced opportunity surface (**in progress**)

Source of truth: `docs/defi-intelligence-roadmap.md`.

**Landed:**
- Advanced backend domain layer in `src/defi/` (`entities`, `docs_analyzer`, `history_store`, `evidence`, `risk_engine`, `scenario_engine`, `ai_router`, `opportunity_engine`, `ai_explainer`).
- `intelligence_engine.py` is now a facade over `opportunity_engine.py`.
- Routes upgraded: v1 `analyze / opportunities / protocol/{slug}` plus a new v2 surface (`discover`, `protocols/{slug}`, `opportunities/{id}`, `compare`, `simulate/lp`, `simulate/lending`, `positions/analyze`).
- Frontend rebuilt: `/defi` is a ranked discover page with market brief, conservative/balanced/aggressive buckets, protocol spotlights. New routes `/defi/opportunity/[id]`, `/defi/protocol/[slug]`, `/defi/compare`, and the expanded `/defi/lending` with stress-simulation flows.

**Next enhancements (ordered):**
1. **Persist beyond memory** — back `defi/stores/analysis_store.py` and `evidence_store.py` with Postgres for historical snapshots, docs metadata, and token inheritance.
2. **Scenario-aware portfolio construction** — multi-opportunity allocation views rooted in scenario outcomes.
3. **Regression tests** — DeFi normalizers, route payload shapes, score-shape stability.
4. **Deeper on-chain due diligence** — per-deployment audits of protocol surfaces.
5. **Alert integration** — protocol incidents and score downgrades flow into `routes/alerts.py` and user-facing notifications.

### 6.2 Agent Platform merge — AI Chat + AI Swap

Source of truth: `docs/ai-agent-integration.md`.

The Agent Platform is a consumer-grade DeFi assistant being developed on a separate device. Its primary surface is a **chat that can both answer questions and build signed transaction proposals**. The user always signs on the client; the backend never touches keys.

**Integration shape:** only **two new routes** land in Ilyon (`/agent/chat`, `/agent/swap`). `/dashboard` and `/portfolio` already cover the other two tabs. All bridge / stake / transfer / LP-deposit / automation flows live *inside* the chat as structured cards (`BalanceCard`, `LiquidityPoolCard`, `UniversalCardList`, `SimulationPreview`) — **not** as navigable routes.

**Merge phases:**

| Phase | Scope | Status |
|---|---|---|
| 0 | Nav group + static preview plugs at `/agent/chat`, `/agent/swap` | **Done** |
| 1 | Port `crypto_agent.py` LangChain tool surface into the Python backend; unify auth verifiers (MetaMask / Phantom alongside existing Solana); persist chats in Postgres (`chats`, `chat_messages` tables in `storage/database.py`) | Next |
| 2 | Live AI Chat surface — composer, feed, reasoning accordions, quick-prompt chips, streaming `POST /api/v1/agent`, per-session memory keyed on `session_id`, structured card renderers | Follows Phase 1 |
| 3 | Structured execution via shared `SimulationPreview` card — EVM chain-switch → approval → main tx; Solana versioned-tx deserialization → Phantom sign-and-send; bridge status polling via `GET /bridge-status/{order_id}` | Follows Phase 2 |
| 4 | Live AI Swap composer that hands off to Chat for routing/simulation/signing | Follows Phase 3 |
| 5 | Portfolio multi-address scan merging Phantom-Solana + Phantom-EVM into one view | Follows Phase 4 |
| 6 | Browser popup / sidepanel surfaces (optional) | Deferred |

**Ported backend surface (target):**

| Endpoint | Role |
|---|---|
| `POST /api/v1/agent` | Main chat/action orchestration (streaming) |
| `POST /api/v1/rpc-proxy` | JSON-RPC relay |
| `GET /api/v1/bridge-status/{order_id}` | deBridge polling for `SimulationPreview` |
| `POST /api/v1/auth/{metamask,phantom}` | Wallet-signature login (unified verifier) |
| `GET /api/v1/auth/me` | Profile |
| `GET/POST/PATCH/DELETE /api/v1/chats[/id]` | Chat persistence |
| `GET /api/portfolio/{wallet_address}` | Multi-address, multi-chain scan |

**LangChain tools (anti-hallucination):** `get_wallet_balance`, `simulate_swap`, `get_token_price`, `build_swap_tx`, `get_defi_market_overview`, `get_defi_analytics`, `get_staking_options`, `search_dexscreener_pairs`, `find_liquidity_pool`, `build_solana_swap`, `build_stake_tx`, `build_deposit_lp_tx`, `build_bridge_tx`, `build_transfer_tx`. Deterministic fast paths short-circuit common intents to avoid LLM drift.

**Third-party integrations (new to Ilyon):** Enso (EVM routing), deBridge DLN (bridge), Moralis (wallet inventory) — layered alongside existing Jupiter / DexScreener / DefiLlama / CoinGecko.

**Explicit day-one exclusions:** unstaking, removing liquidity, claiming rewards, arbitrary contract interaction, contract deployment. Staking narrowed to ETH / BNB / MATIC and whitelisted protocols. LP deposits require a resolvable EVM pool. Transfer builder is EVM-first.

**Open decisions:**
- Backend framework — port FastAPI handlers to aiohttp, or run FastAPI as a sidecar?
- Brand color — Agent Platform uses gold, Ilyon uses emerald. Preview plugs use emerald for coherence.
- Chat persistence migration path — SQLite → Postgres if any Agent Platform users exist.
- Global ticker bar adoption in `AppShell`.

### 6.3 Helius webhook upgrade — real-time whale pipeline

Once deployed to a public URL, the whale stream upgrades from `logsSubscribe` + polling to push-based webhooks.

- Register a Helius webhook covering the 9 DEX programs (Jupiter, Raydium v4, Raydium CLMM, Raydium CP, Pump.fun, Orca, Meteora, Phoenix, Lifinity) on `SWAP` transaction type.
- Point the webhook at `POST /api/v1/webhooks/helius`.
- Handler reuses the existing `persist → broadcast` pipeline (same code path as stream and poller).
- Signature verification already exists at `src/api/middleware/webhook_signature.py`.
- Keep the 60s poller as a safety-net backfill (hybrid Approach C).
- Disable `logsSubscribe` once webhook delivery is confirmed.

**Why:** sub-second latency, zero incremental API credits, simpler resilience story.

### 6.4 Cross-cutting future work

- **Alerts** — wire `routes/alerts.py` into the event bus so DeFi incidents, score downgrades, and whale thresholds become user-facing notifications.
- **Public API hardening** — expand `public_api/router.py` surface, add outbound webhooks for paying customers (`public_api/webhooks.py`).
- **Quality loop** — use `quality/feedback_store.py` and `replay_evaluator.py` to tune `heuristic_weights.py` from real user feedback.
- **Precompute** — move expensive aggregations (leaderboards, dashboard widgets) fully into `platform/precompute.py` scheduled jobs.

---

## 7. Cross-cutting Invariants

These rules appear throughout the codebase and are easy to accidentally violate:

1. **Singletons via getters.** Services are accessed as `get_blink_service()`, `get_database()`, `get_icon_generator()`, `get_stream_hub()`. Do not construct new instances.
2. **CORS lives in one place.** All CORS headers come from `src/api/middleware/cors.py`. Route handlers never set CORS headers. If you add a public path prefix, update the middleware.
3. **ToastProvider is required.** `useToast()` only works inside `ToastProvider`; `<Toaster />` alone renders nothing.
4. **DB is silent-pre-init.** `storage/database.py` methods return `None` when `_initialized=False`. Check initialization before relying on persisted state.
5. **Analyzer is lifecycle-bound.** Initialized via `init_analyzer()` in `src/api/routes/analysis.py`, cached at `app['analyzer']`. Don't construct per-request.
6. **The client signs.** No transaction builder persists or transmits private keys. Backends return unsigned payloads; signing happens in the wallet.
7. **Graceful degradation is the default.** Helius failure → raw RPC. AI failure → deterministic scores with a confidence marker. Redis failure → in-process cache. Stream failure → poller fallback.
8. **Cache entries carry a `fetched_at`.** Any value older than its TTL must be re-fetched before it enters a scoring or AI decision.
9. **Parallelize fetches, serialize decisions.** Data providers are `asyncio.gather`-ed; scoring + AI judgment sit at a single merge point. Never let AI call out to another provider mid-prompt.
10. **`NEXT_PUBLIC_COMING_SOON` gates visibility, not code.** Features behind the flag still build; only surfaces are replaced. Don't introduce code paths that exist only when the flag is off.

---

## 8. Local Development — quick reference

```bash
# Backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add OPENROUTER_API_KEY at minimum
python -m src.main          # aiohttp on :8080

# Frontend
cd web
npm install
cp .env.local.example .env.local
npm run dev                 # Next.js on :3000

# Tests
pytest tests/
cd web && npm test

# Style
black src/ && ruff check src/
cd web && npm run lint
```

See `README.md` §Configuration for the full environment-variable matrix and API-key sources.

---

## 9. Related Documents

| Document | Scope |
|---|---|
| `README.md` | Public product description, feature catalog, setup |
| `docs/defi-intelligence-roadmap.md` | DeFi intelligence surface — shipped + next |
| `docs/ai-agent-integration.md` | Agent Platform merge plan — tabs, APIs, phases |
| `docs/BOT_API_REFERENCE.md` | Telegram bot endpoints |
| `docs/BOT_INTEGRATION_GUIDE.md` | Telegram bot integration walkthrough |
| `docs/ilyonai-design-reference.md` | Visual language and design tokens |

When the information in this document disagrees with one of the above, the more-specific document wins for its domain; this document is updated on merge.
