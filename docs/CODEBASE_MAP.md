# IlyonAI Architecture Map

> Definitive developer reference for the IlyonAI (a.k.a. Ilyon Sentinel) codebase — an AI-native, non-custodial, multi-chain DeFi copilot. Synthesized from 19 subsystem digests produced by agents reading the real source. The single product invariant: **the agent never broadcasts and never fabricates money-affecting facts** — it returns only typed, structurally-validated, pre-simulated cards plus sanitized prose, and refuses rather than guesses.
>
> _Provenance: generated 2026-06-21 by a 21-agent parallel deep-read of the full tree (Sentinel API `src/`, both sidecars, `web/`, contracts, tests, docs) followed by an adversarial completeness pass. The verifier found **no hallucinations** — every load-bearing claim traces to a subsystem digest. This is the public architecture/development reference; the internal risk register, security hotspots, and raw per-subsystem digests are maintained privately and intentionally omitted here._

---

## 1. System Overview

### 1.1 What it is
A chat-driven DeFi copilot. A user types a natural-language request ("swap 1 SOL to USDC", "deposit $5k into the best stable pool", "bridge then stake"). The system detects intent, scores opportunities and transactions with the **Sentinel** risk engine, builds **unsigned** transaction calldata pre-checked by simulation, and streams typed UI "cards" back over SSE. The user signs in their own wallet (MetaMask / Phantom). The backend is non-custodial: it only ever returns unsigned tx payloads.

### 1.2 The four services + datastores

| Service | Tech | Port | Role |
|---|---|---|---|
| **Sentinel API** (`src/`) | Python aiohttp | 8080 | The primary backend: agent runtime, intent routing, tool registry, scoring, DeFi execution planning, market/intel data, auth, SSE. |
| **EVM Wallet-Assistant sidecar** (`IlyonAi-Wallet-assistant-main/server`) | Python FastAPI + LangChain | 8000 | Standalone wallet assistant. Builds EVM (Enso) / Solana (Jupiter) / bridge (deBridge) tx calldata. Consumed BOTH over HTTP and **in-process** (Sentinel imports its `crypto_agent.py` builders via `importlib`). |
| **Solana Yield Builder sidecar** (`services/solana-yield-builder`) | Node 20 / Express | 8090 | Builds simulation-gated Solana deposit/withdraw/close txs for ~12 protocols (Kamino/Orca/Meteora/Raydium/Marinade/Jito/Sanctum/JLP + Jupiter fallback). Stateless, internal-only. |
| **Web** (`web/`) | Next.js 14 App Router | 3000 | The UI. Mostly client components + React Query; the agent chat surface (`MainApp.tsx`) opens an SSE stream and renders cards; drives wallet signing. Also reused inside a Chrome MV3 extension. |
| **Postgres** | postgres:15 (db `ilyon_ai`) | 5432 | ~25 ORM tables + Alembic migrations (agent_001..013). Silent SQLite fallback in dev. |
| **Redis** | redis:7 | 6379 | Cache + sessions; degrades to in-memory if absent. |

Plus a **wallet-assistant-api** FastAPI service (the sidecar above) and the **AffiliateHook** PancakeSwap-V4 monetization contract (`contracts/`).

### 1.3 Interconnect

- The web client never calls backends directly; `next.config.js rewrites()` proxy same-origin `/api/*` to either the Sentinel backend (`API_REWRITE_TARGET`, default :8080) or the wallet-assistant (`ASSISTANT_API_TARGET`, default :8000). `AGENT_BACKEND` selects the `/api/v1/agent` target. App Router route handlers (`web/app/api/v1/agent/route.ts`) intercept the agent path and pick a backend per-request by intent classification, with a per-session affinity map.
- Sentinel API → Wallet-Assistant: **in-process** (lazy `importlib.util.spec_from_file_location` of `crypto_agent.py`, cached as `sys.modules["wallet_assistant_crypto_agent"]`), NOT HTTP, for tx building.
- Sentinel API → Solana Yield Builder: **HTTP** (`SOLANA_YIELD_BUILDER_URL=http://solana-yield-builder:8090`).
- Sentinel API ↔ Postgres/Redis: SQLAlchemy async / redis.asyncio.

### 1.4 Data-flow diagram: a "deposit/swap" request from chat to signed tx

```
┌─────────┐   POST /api/v1/agent (JSON)        ┌──────────────────────────────┐
│ Browser │ ─────────────────────────────────▶ │ Next rewrite / route.ts      │
│ MainApp │   text/event-stream (SSE)          │ _selectBackendTarget()       │
└────┬────┘ ◀───────────────────────────────── │ wallet(:8000) | sentinel(:8080)│
     │                                          └──────────────┬───────────────┘
     │                                                         ▼
     │                                   ┌───────────────────────────────────────┐
     │                                   │ Sentinel API  src/api/routes/agent.py │
     │                                   │   agent_turn (FEATURE_AGENT_V2,       │
     │                                   │   agent_gap 0.5s, register_all_tools) │
     │                                   │  guest→run_simple_turn / auth→run_turn│
     │                                   └──────────────┬────────────────────────┘
     │                                                  ▼
     │                       ┌──────────────────────────────────────────────────┐
     │                       │ simple_runtime.run_ephemeral_turn (THE engine)   │
     │                       │  detect_intent → (tool_name, args)               │
     │                       │  ThoughtFrame… ToolFrame → tool.ainvoke          │
     │                       └───────────────┬──────────────────────────────────┘
     │                                        ▼ ToolEnvelope (+Sentinel/Shield)
     │              ┌─────────────────────────┴───────────────────────────────┐
     │              ▼                                                          ▼
     │   ┌─────────────────────┐   in-proc importlib       ┌──────────────────────────┐
     │   │ EVM/Solana builders │ ────────────────────────▶ │ Wallet-Assistant sidecar │
     │   │ wallet_swap/bridge  │   (Enso/Jupiter/deBridge) │ crypto_agent._build_*    │
     │   └─────────────────────┘                           └──────────────────────────┘
     │   ┌─────────────────────┐   HTTP POST /build         ┌──────────────────────────┐
     │   │ build_yield_exec…   │ ────────────────────────▶ │ Solana Yield Builder :8090│
     │   │ adapter registry    │   (Kamino/Orca/Meteora…)  │ simulateTransaction gate │
     │   └─────────────────────┘                           └──────────────────────────┘
     │                                        ▼
     │              ExecutionPlanV3 / swap_quote card, UnsignedStepTransaction
     │              (simulated_calldata_hash + simulated_at stamped)
     │  ◀──── SSE: card frame ────────────────────────────────────────────────┘
     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ CardRenderer → ExecutionPlanV3Card → user clicks "Sign step"            │
│  useWalletSigning: assertFresh (30s/1800s) + computeCalldataHash bind   │
│  → MetaMask/Phantom popup → eth_sendTransaction / signAndSendTransaction │
│  → auto-confirm chat with tx hash → receipt verify                      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Request Lifecycle (a chat turn, end to end)

| Hop | Module / function | What happens |
|---|---|---|
| 1. HTTP/SSE open | `src/api/routes/agent.py::agent_turn` (POST `/api/v1/agent`) | Gated by `settings.FEATURE_AGENT_V2` (503 else). Parses wallet/`solana_wallet`/`evm_wallet` (`_addr_from`). `agent_gap = PerSessionGap(0.5)` rate-gate (429). Opens `web.StreamResponse(text/event-stream)`, `prepare()`s. Builds `get_agent_services().to_namespace()` + `register_all_tools(...)`. Routes: guest (no wallet or `user_id==0`) → `run_simple_turn`; auth → `run_turn`. AIRouter is a process singleton (`_get_agent_router`). |
| 2. Persistence wrapper | `simple_runtime.run_simple_turn` | Loads prior turns + persisted card frames from SQLite (`list_messages`, `HISTORY_WINDOW=12`); prefers web `client_history`. Streams inner generator straight to socket, then RE-PARSES emitted SSE to persist final + cards via `append_message`. DB errors swallowed. |
| 3. Intent routing | `simple_runtime.run_ephemeral_turn` → `detect_intent(message)` | **The turn engine.** A long if/elif cascade (NOT a loop) dispatching ONE tool. Order: follow-up replay (`_maybe_replay_followup`), pivot/refine continuity, prior-pools allocation, `detect_intent`/`parse_defi_intent`, LP-envelope extraction, deterministic short-circuits, tool runner. `detect_intent` runs refuse/session-key/reasoning short-circuits FIRST, then ~40 `_detect_*` sub-detectors. Returns `(tool_name, args)` or `None` (→ LLM). |
| 4. Tool-use step | tool runner inside `run_ephemeral_turn`; `tools/__init__.register_all_tools` → `StructuredTool` | Emits `ThoughtFrame`×N → `ToolFrame` → `tool.ainvoke(tool_input)` under `asyncio.wait_for(_slo_for(name))` (TOOL_TIMEOUT err on breach) → `ObservationFrame(ok/err)`. Result is a `ToolEnvelope`. |
| 5. Resolver/scoring | `sentinel_wrap.enrich_tool_envelope` → `src/scoring/*` | Attaches Sentinel pool/route/bridge score + Shield block by tool name / card_type (`attach_pool_score`, `attach_route_score`, `attach_bridge_score`, `attach_transaction_shield`). |
| 6. Builder / sidecar | `build_yield_execution_plan`, `wallet_swap.build_swap_tx`, `SolanaYieldBuilderAdapter` | Single-chain: `build_default_registry().adapter_for(chain,protocol,action).build(YieldBuildRequest)` → `list[ExecutionStepV3]`. Cross-chain: `snapshot_bridge_quote` + `DeBridgeBridge.create_order_encoded` + `block_step_for_async_fill`. Solana: HTTP to `:8090`. EVM swap/bridge: in-proc `crypto_agent` via `importlib`. |
| 7. Simulation gating | `UnsignedStepTransaction.stamp_simulation()`; `broadcast.simulate_step_before_broadcast`; `simulator/tenderly_client`, `solana_simulator` | At serialization: `stamp_simulation` normalizes value/gas to 0x-hex and stamps `simulated_calldata_hash` (SHA-256 over `{to,data,value}`) + `simulated_at`. Sidecar adapters also `simulateTransaction` BEFORE returning (benign empty-wallet reverts pass). |
| 9. Sign | web `CardRenderer` → `ExecutionPlanV3Card.StepRow` → `hooks/useWalletSigning.sign()` | First `ready` step exposes Sign (gated by `planBlocked`, risk-ack checkbox). `assertFresh` (`SIM_FRESHNESS_SECONDS=1800`) + `computeCalldataHash == simulated_calldata_hash` BEFORE the wallet pops (`SimStaleError`/`CalldataMismatchError`). EVM: `ensureChain` + `eth_estimateGas`+25% + `eth_sendTransaction`. Solana: deserialize base64 → `signAndSendTransaction`. Permit2: `eth_signTypedData_v4` → POST `/api/v1/plans/{plan}/steps/{step}/permit2`. Post-sign auto-chat with tx hash for receipt verify. |

The **authenticated** path `runtime.run_turn` is a true LangChain ReAct loop (`create_react_agent` + `AgentExecutor(max_iterations=10)` + `astream_events(v2)`) with DB persistence, `PersistentWindowMemory(k=10)`, a `compose_plan` fast-path, and a Shield SCAM/grade-F short-circuit. **Open question across multiple digests: `run_turn` may be largely unreachable** — `agent_turn` reads `request.get("user_id", 0)` but no middleware sets it, so most traffic flows through `run_simple_turn`.

---

## 3. Per-Subsystem Reference

### 3.1 Core Agent Runtime (`agent-runtime`)
**Purpose:** Turn one chat message into a streamed sequence of typed SSE frames; enforce structural safety; sanitize LLM prose.
**Key files:** `src/agent/simple_runtime.py` (10,938 LOC — `run_ephemeral_turn`, `detect_intent` + ~40 `_detect_*`, ~20 `_UNBACKED_*` regexes, `_format_tool_result`), `streaming.py`, `runtime_invariants.py`, `runtime.py` (ReAct), `planner.py`, `step_executor.py`, `src/api/routes/agent.py`, `src/api/schemas/agent.py`.
**How it works:** TWO runtimes — `run_turn` (ReAct/authed) and `run_ephemeral_turn` (deterministic/guest, de-facto production). The guest engine dispatches exactly ONE tool per turn; multi-action requests use deterministic planners (`compose_plan`, `_bake_prior_pools_execution_plan`). Legacy-preview tools `{build_swap_tx, build_bridge_tx, build_solana_swap, get_wallet_balance}` SKIP the typed card and dump raw `env.data` JSON as `final_content` for the frontend `parseSwapPreview` flow.
**Key interfaces:** `run_ephemeral_turn(*, router, tools, message, wallet, history, history_cards)`, `detect_intent(message) -> (tool, dict)|None`, `_strip_unbacked_claims(content, *, has_real_card, conversational)`, `_is_critical_shield(env)`.

### 3.2 Agent Tool Layer (`agent-tools`)
**Purpose:** Every LLM-callable tool, uniform `ToolEnvelope`, per-tool SLO timeout, sidecar bridge.
**Key files:** `tools/__init__.py` (`_TOOL_REGISTRY` 28 tools, `_TOOL_SLO_SECONDS`, `register_all_tools`, `_late_bound`/`_run`), `_base.py` (`ok_envelope`/`err_envelope`, `_normalize_err_code`), `_assistant_bridge.py` (`parse_assistant_json`), `sentinel_wrap.py`, `wallet_swap.py`, `wallet_bridge.py`, `build_yield_execution_plan.py` (2,436 LOC), `execute_pool_position.py`, `search_defi_opportunities.py`, `allocate_plan.py`, `sentinel_features.py`.
**How it works:** `_run` re-resolves fn from registry each call (monkeypatch-safe; **RC16 fix:** SLO keys off registry NAME not `fn.__name__`), runs under `asyncio.wait_for`, NEVER fabricates a card from partial data on timeout. EVM/Solana builders lazy-load the wallet-assistant sidecar by file path. Planner tools call the in-process DeFi engine + `build_default_registry()`.
**Key tool→card map (selected):** `build_swap_tx`/`build_solana_swap`→`swap_quote`; `build_bridge_tx`→`bridge`; `build_stake_tx`→`stake`; `build_deposit_lp_tx`→`lp`; `search_defi_opportunities`→`defi_opportunities`; `allocate_plan`→`allocation` + extras `sentinel_matrix`,`execution_plan`; `build_yield_execution_plan`/`execute_pool_position`→`execution_plan_v3`|`pool_link`; `compose_plan`→`execution_plan_v2`; `analyze_token_full_sentinel`→`sentinel_token_report`; `track_whales`→`sentinel_whale_feed`; `get_shield_check`→`sentinel_shield_report`.

### 3.3 Intent / LLM / Render / Pool-Resolution (`agent-intent-llm-render`)
**Purpose:** NL → deterministic tool intent OR LLM path; LLM client config; resolve protocol/pool refs to exact addresses + deeplinks.
**Key files:** `intent/defi_intent.py` (`parse_defi_intent` → 4 intents: `execute_yield_strategy`/`allocate_strategy`/`search_defi_opportunities`/`explain_or_compare`), `intent/liquidity_intent.py`, `intent/lp_intent_extractor.py` (OpenRouter JSON-schema structured output), `intent/validation.py`, `src/ai/openai_client.py` (THE LLM client, 928 LOC), `src/ai/router.py`, `llm/__init__.py` (`IlyonChatModel`), `pool_address_authoritative.py`, `pool_address_resolver.py`, `pool_deeplinks.py`, `protocol_urls.py`, `pool_types.py`, `cross_chain.py`, `receipt_watcher.py`.
**How it works:** Deterministic-first. LLM invoked only 3 additive ways: slang normalization (`_llm_normalize_request`), schema-constrained LP extraction (`extract_lp_intent`, fail-soft), final conversational answer (`IlyonChatModel._agenerate`). `OpenAIClient` is dual-provider (`use_openrouter` flag); OpenRouter default model `nvidia/nemotron-3-super-120b-a12b:free` with `HTTP-Referer https://t.me/Ilyon_AI_Bot`. Pool resolution prefers on-chain truth: V3 via `factory.getPool` (selector `0x1698ee82`), V2 `getPair` (`0xe6a43905`), Curve MetaRegistry (`0xa87df06c`), Orca/Raydium REST.

### 3.4 DeFi Execution / Tx Assembly (`defi-execution`)
**Purpose:** Parsed intent → one signable `ExecutionPlanV3`; per-step adapter routing; simulation gating + calldata-hash binding; deBridge async-fill settlement.
**Key files:** `execution/models.py` (`ExecutionPlanV3`/`ExecutionStepV3`/`UnsignedStepTransaction`/`ExecutionBlocker`, `KNOWN_BLOCKER_CODES`, status recompute), `composed_plan.py` (snapshot→block→rebuild→promote, RC7a `assert_signable_composed_plan`), `composed_plan_orchestrator.py`, `capabilities.py` (`AdapterRegistry` + `build_default_registry`), `adapters/base.py`, `broadcast.py`, `preflight.py`, `pending_plans.py`, `state_machine.py` (V7-001 calldata hash), `src/routing/debridge_client.py`, `api/routes/debridge_webhook.py`, `bridge_confirmed.py`, `plan_permit2.py`.
**How it works:** Plan mutators self-recompute (`_recompute_totals` MAX-not-SUM per asset, `_recompute_step_statuses` first non-blocked = `ready`, `_refresh_plan_status` vs §5 `PipelineState`). Blocker codes normalize to UPPER_SNAKE at `add_blocker`. Cross-chain: 2-step composed plan (signable bridge leg + deposit step blocked on `PENDING_DST_FILL`, `transaction=None`). Two redundant resolvers feed the same primitives: webhook (`POST /api/v1/debridge/webhook` → `resolve_fill`) and polling (`ComposedPlanOrchestrator.watch` → `watch_for_fill`). Results stream over `stream_hub` topic `plan:{plan_id}`.
**Adapter precedence (order = routing):** UniswapV4 → UniswapV3NFT → UniswapV2DualToken → UniswapV2Zap → AaveV3 → CompoundV3 → Curve → Balancer → EvmLstDirectMint → ERC4626Vault → PendleV2 → EnsoShortcut (EVM catch-all) → SolanaYieldBuilder → WalletAssistant.

### 3.5 DeFi Discovery / Pool Resolution (`defi-discovery`)
**Purpose:** NL/constraint set → ranked universe of concrete on-chain pools.
**Key files:** `resolver/entity_resolver.py` (707 LOC), `data/v3_pool_resolver.py`, `tools/search_defi_opportunities.py`, `search/models.py`, `search/ranking.py`, `pool_address_authoritative.py`, `pool_index/store.py`/`refresher.py`/`rankings.py`/`schema.py`, `opportunity_taxonomy.py`, `pipeline/scan|enrich|synthesize.py`, `stores/analysis_store.py`/`evidence_store.py`, `aggregators/fallback_chain.py`.
**How it works:** Two resolution paths sharing data sources. Path A: `EntityResolver` canonicalizes token/protocol/chain/pool (native↔wrapped maps, alias maps, V2 getPair RPC, dispatch to `resolve_v3_pool`). Path B: `search_defi_opportunities` fetches the FULL DefiLlama universe (`get_all_pools_normalized`, 30s cache), badges executability, `rank_opportunities` (exclusion + `_ranking_score` + sanity penalty + per-tier quota + protocol diversification), `_enrich_pool_addresses` fills exact addresses. `pool_index` Postgres table (Alembic agent_005) is the DB-backed catalog refreshed from DefiLlama every 30 min.

### 3.6 DeFi Strategy / Math (`defi-strategy-math`)
**Purpose:** (chain,protocol,action) → verified, simulated, range-aware plan; APR/IL/capital-efficiency math; position monitoring; recovery; receipt verification; scoring.
**Key files:** `execution/capabilities.py`, `tools/build_yield_execution_plan.py`, `execution/reliable_set.py`, `math/v3_liquidity.py` (Q96 SDK math), `data/v3_tick_math.py`, `apr_curve/four_factor.py`/`empirical_cdf.py`/`il_grid.py`, `simulator/tenderly_client.py`/`solana_simulator.py`, `dlmm/bin_distribution.py`, `position_monitor/cron.py`/`detectors.py`/`position_health.py`, `recovery/stuck_balance.py`/`dust_accumulator.py`, `verification/receipt_table.py`/`receipt_reader.py`, `scoring/deterministic.py`/`final_ranker.py`, `strategy/memory.py`/`source_token_heuristic.py`.
**How it works:** Two-tier dispatch: `build_yield_execution_plan` (safety guards → `classify_pool_kind` → V3 short-circuits to `pool_link`, else `AdapterRegistry`). EVM LP on `_ENSO_LP_PROTOS` is force-overridden to `EnsoShortcutAdapter` (native dual-leg adapters revert on funded forks). APR-by-range = §6e four-factor `P_in(width)·CE(width)·fee_yield_full − IL_drag`. Position monitoring is an APScheduler 5-min sweep (`PositionHealth` 12-field, import-time assert). Recovery `decide_recovery` is a §6f decision tree (slippage→AUTO_REBUILD, pool paused→ASK_USER, refund-swap-back forbidden via `guard_refund`). Receipt verification: 20-row `RECEIPT_TABLE`.

### 3.7 Core API Routes + Middleware (`api-routes-core`)
**Purpose:** aiohttp HTTP/SSE layer: token/DeFi/shield/portfolio analysis, Blinks, auth, agent SSE.
**Key files:** `api/app.py` (`create_api_app`, ~33 `setup_*_routes`), `response_envelope.py`, `middleware/cors.py`/`rate_limit.py`, `routes/auth.py` (soft `auth_middleware`, `require_auth`/`require_scope`), `routes/agent.py`, `schemas/agent.py`, `streaming.py`, `runtime.py`, `routes/defi.py`/`analysis.py`/`shield.py`/`portfolio.py`/`transactions.py`/`actions.py`/`blinks.py`, `services/blink_service.py`.
**How it works:** Middleware `[cors, auth, rate_limit]`. CORS is `*` for `/actions`,`/blinks/`,`/.well-known/`. Auth is SOFT (sets `request['user_wallet']` if Bearer resolves; never 401 itself). Rate limiter is in-memory sliding-window per-scope. Response envelope (`{status,data,meta,errors,trace_id,freshness}`) is applied INCONSISTENTLY (shield/transactions/defi-analyze/portfolio/search use it; analysis/blinks/actions/auth/agent return bare dicts). Solana Actions/Blinks lifecycle: `/.well-known/actions.json`, `/api/v1/blinks/{id}` (type:action metadata for Twitter unfurl), dynamic PNG score badge.

### 3.8 API Routes — Intel + Account-Abstraction (`api-routes-intel`)
**Purpose:** Read-only market/intel/whale endpoints + the write-side AA surface (EIP-7702, session keys, Permit2, deBridge settlement, HMAC audit) + auth.
**Key files:** `routes/eip7702_auth.py`, `session_keys.py`, `debridge_webhook.py`, `bridge_confirmed.py`, `plan_permit2.py`, `audit.py`, `auth/smart_account.py`, `biconomy_nexus.py`, `zerodev_kernel.py`, `solana_session.py`, `execution/pending_plans.py`, `routes/whale.py`/`stats.py`/`contracts.py`/`alerts.py`/`stream.py`/`prices.py`, `services/blink_service.py`/`icon_generator.py`, `public_api/router.py`.
**How it works:** EIP-7702: `prepare` (digest = `keccak(0x05 || rlp([chain_id,impl,nonce]))`) → `authorize` (65-byte sig → `Eip7702Authorization`) → install/uninstall ERC-7579 module calldata (Nexus install `0x9517e29f`, uninstall `0xa71763a8`). Session keys: `SessionKeyPolicy.can_authorise` (per-tx → 24h → total caps). Two session-key-mirror modules cross-check off-chain vs on-chain.

### 3.9 Core Config / Storage / Platform (`core-config-storage-platform`)
**Purpose:** Settings, async SQLAlchemy DB + Redis/memory cache, in-memory pub/sub, AI-primary token scorer, whale poller.
**Key files:** `config.py` (`Settings`), `storage/database.py` (2,229 LOC, ~25 tables + `Database`), `storage/cache.py` (`CacheLayer`), `platform/stream_hub.py`/`event_bus.py`, `services/whale_poller.py`, `core/scorer.py`/`analyzer.py`/`models.py`, `main.py`, `bootstrap_assistant_import.py`, `storage/sessions.py`/`state_store.py`, `api/routes/stream.py`.
**How it works:** `main.py on_startup`: `init_database` (Postgres→SQLite fallback) → `init_cache` → spawn `WhaleTransactionPoller` → wire `ComposedPlanOrchestrator` notifier to stream hub. `StreamHub` per-subscriber bounded `asyncio.Queue(100)` drop-oldest. `InMemoryEventBus` fan-out with per-(topic,subscriber) `CircuitBreaker` + `DeadLetterQueue`.

### 3.10 Data Providers (`data-providers`)
**Purpose:** ~20 async clients wrapping external crypto data/security/RPC APIs.
**Key files:** `data/solana.py` (1,769 LOC, Helius), `scraper.py` (Playwright/BeautifulSoup), `dexscreener.py`, `honeypot.py`, `jupiter.py`, `v3_pool_resolver.py`, `defillama.py`, `asset_registry.py`, `goplus.py`, `rugcheck.py`, `coingecko.py`, `merkl_client.py`, `helius_keys.py`, `price_oracle.py`, `moralis.py`/`moralis_rotator.py`, `v3_tick_math.py`, `v4_hooks_allowlist.py`.
**How it works:** No shared base class; each re-implements session/retry and FAILS SOFT (returns `[]`/None/defaults). Helius access goes through a process-wide rotating key pool (`HeliusKeyPool`) distinguishing cap-exhaustion 429 (1800s) from rate-limit 429 (12s). Moralis has its OWN rotator. Honeypot detection is behavioral (Jupiter sell-quote + simulation; "no route" → UNABLE_TO_VERIFY, never HONEYPOT).

### 3.11 Scoring / Sentinel (`scoring-sentinel`)
**Purpose:** The Sentinel risk engine + intelligence modules.
**Key files:** `allocator/composer.py` (the real pool math), `scoring/rubric.py`/`normalizer.py`/`pool_scorer.py`/`route_scorer.py`/`bridge_scorer.py`/`shield_gate.py`, `core/scorer.py` (token `overall_score`), `shield/approval_scanner.py`, `analytics/wallet_forensics.py`/`anomaly_detector.py`/`behavior_signals.py`, `intel/rekt_database.py`, `smart_money/graph_store.py`, `quality/*`, `agents/sentinel.py`, `decorator.py`, `defi/sentinel_lite.py`.
**How it works:** **TWO different "Sentinel scores"** (see §5). Pool score: `score_pool_mapping` → `weighted_sentinel = 0.40·safety + 0.25·durability + 0.20·exit + 0.15·confidence`. Token score: AI-primary `overall_score = ai_score + adjustments`, hard-capped (rugged→0, scammer→25, honeypot→15). Shield: `ApprovalScanner.scan_wallet` (Moralis→Etherscan, risk 0-100 where higher=worse), `encode_revoke_calldata` → `approve(spender,0)`.

### 3.12 Backend Misc Modules (`backend-misc-modules`)
**Purpose:** Chains abstraction, swap/bridge routing, allocation, optimizer/indexer, alerts, AI providers, AA auth, growth/monetization, logging.
**Key files:** `chains/base.py`/`registry.py`/`evm/client.py`/`gas_pricing.py`, `routing/quote_service.py`/`enso_client.py`/`debridge_client.py`/`lifi_client.py`/`socket_client.py`/`stake_builder.py`, `allocator/composer.py`, `optimizer/daemon.py`/`delta.py`/`safety.py`/`notifier.py`, `indexer/positions_watcher.py`, `agents/sentinel.py`, `alerts/orchestrator.py`/`db_store.py`, `ai/router.py`/`base.py`, `auth/session_keys.py`/`smart_account.py`/`biconomy_nexus.py`, `contracts/scanner.py`/`ai_auditor.py`, `logging/structured.py`/`context.py`/`filters.py`.
**How it works:** `QuoteService.quote` selects Enso (EVM) vs Jupiter (Solana). Cross-chain bridges implement a duck-typed `composed_plan.Bridge` protocol (deBridge/LiFi/Socket). `OptimizerDaemon` (APScheduler, gated `OPTIMIZER_ENABLED`, default off) runs snapshot+propose; `positions_watcher` detects drift. `AIRouter` picks OpenAI-direct vs OpenRouter + optional Grok.

### 3.13 EVM/Solana Wallet-Assistant Sidecar (`wallet-assistant-sidecar`)
**Purpose:** FastAPI service turning NL → pre-simulated ready-to-sign EVM/Solana tx calldata.
**Key files:** `app/main.py`, `api/endpoints.py` (1,937 LOC, `run_agent` + ~13 `_try_direct_*` fast paths), `agents/crypto_agent.py` (5,683 LOC — all builders), `api/portfolio.py`, `auth.py`, `chats.py`, `core/config.py`/`security.py`, `db/models.py`; bridges `src/agent/tools/wallet_swap.py`/`wallet_bridge.py`/`_assistant_bridge.py`, `src/bootstrap_assistant_import.py`, `web/app/api/v1/agent/route.ts`.
**How it works:** `run_agent` runs deterministic fast-path handlers FIRST (regex → builder, no LLM), gated by `_is_reasoning_question and not _is_unstake_command`. Only on no-match does it build a LangChain ReAct `AgentExecutor` (15 Tools, provider fallback OpenAI→OpenRouter→Groq, 90s timeout). EVM swaps→Enso (`_build_enso_swap_tx`, pre-sim via `_eth_call_simulate`, `evm_action_proposal`); Solana→Jupiter; bridges→deBridge DLN. Each builder returns JSON with a top-level `type` discriminator the frontend renders as a card.

### 3.14 Solana Yield Builder Sidecar (`solana-yield-builder-sidecar`)
**Purpose:** Node/Express service building simulation-gated Solana deposit/withdraw/close txs for ~12 protocols.
**Key files:** `src/index.js` (Express, adapter registry + ~70 aliases, `/quote`/`/build`/`/pool_state`/`/verify`), `adapters/jupiter.js`/`simulate.js`/`_token_safety.js`/`altSplit.js`/`pairAware.js`/`_legacyRaydiumPrep.js`/`raydium.js`/`orca.js`/`meteora.js`/`kamino.js`/`jlp.js`/`marinade.js`/`jito.js`/`sanctum.js`, Python client `src/defi/execution/adapters/solana_yield_builder.py`.
**How it works:** `/build` dispatches by action verb to lifecycle methods. Adapters return base64 v0/legacy txs, EVERY one pre-simulated via `simulateBase64Tx` (`sigVerify:false, replaceRecentBlockhash:true`; benign empty-wallet reverts pass). Native-SDK adapters compose real instructions; long-tail slugs route to a Jupiter prep-swap fallback. V7-031 transfer-hook allowlist, V7-032 WSOL sync/close, V7-041 pool-init checks. Python client maps `transactions[]` → chained `ExecutionStepV3`.

### 3.15 Next.js App Pages + Frontend API (`web-app-pages`)
**Purpose:** The UI pages + the thin `/api/v1/agent` route handler.
**Key files:** `app/layout.tsx`, `app/page.tsx`, `app/api/v1/agent/route.ts`, `components/agent-app/MainApp.tsx` (7,137 LOC), `MainAppLoader.tsx`, `app/agent/layout.tsx`, `lib/agent-client.ts`, `lib/api.ts` (1,790 LOC), `lib/hooks.ts`, `components/agent/cards/CardRenderer.tsx`, `next.config.js`, plus data pages (dashboard/token/pool/shield/contract).
**How it works:** Almost all pages are client components using React Query → `lib/api.ts` → `fetchAPI`. The agent chat is ONE `MainApp` instance mounted by `app/agent/layout.tsx`; `app/agent/{chat,portfolio,swap}/page.tsx` return `null`. TWO SSE clients: production `MainApp.send` (buffered — re-parses whole `rawBody` each chunk) and demo `streamAgent` generator (incremental). The route handler classifies intent (`_selectBackendTarget`) wallet-vs-sentinel with session affinity.

### 3.16 Agent Card Rendering (`web-components-cards`)
**Purpose:** SSE card frames → discriminated-union React renderers; interactive V3 range selectors.
**Key files:** `components/agent/cards/CardRenderer.tsx` (843 LOC switch), `types/agent.ts` (auto-generated, 792 LOC), `ExecutionPlanV3Card.tsx`, `PoolDepositV3Card.tsx`, `V3RangeBlock.tsx`, `AllocationCard.tsx`, `DefiOpportunitiesCard.tsx`, `Permit2SigButton.tsx`, `lib/agent-client.ts`, `hooks/useAgentStream.ts`/`usePlanStream.ts`/`useExecutionPlan.ts`, `components/agent/MessageList.tsx`.
**How it works:** `CardRenderer` runs one big `switch(card_type)`, casting untyped payload. ~16 simple renderers inline; rich ones delegated. `ExecutionPlanV3Card` renders `StepRow`s; only first `ready` step shows Sign (gated by `planBlocked` + risk-ack). `usePlanStream` opens EventSource on `plan:{plan_id}` only when a step has `PENDING_DST_FILL`. Two duplicated V3 range implementations (`PoolDepositV3Card` standalone vs `V3RangeBlock` embedded).

### 3.17 Web Lib/Hooks/Wallet + Extension (`web-lib-hooks-extension`)
**Purpose:** SSE transport, wallet adapters + hash-bound signing, Chrome extension.
**Key files:** `next.config.js`, `lib/agent-client.ts`, `hooks/useAgentStream.ts`, `lib/realtime.ts` (WS + polling fallback), `hooks/usePlanStream.ts`, `lib/api.ts`, `lib/wallets/metamask.ts`/`phantom.ts`, `lib/signer.ts` (V7-001 hash bind), `hooks/useWalletSigning.ts` (V7-045), `types/agent.ts`, `components/agent-app/MainApp.tsx`, `Permit2SigButton.tsx`, `extension/manifest.json`/`src/*`, the OTHER client `IlyonAi-Wallet-assistant-main/client`.
**How it works:** `getEvmProvider()` does EIP-5749 multi-provider resolution to avoid Phantom hijacking `window.ethereum`. `computeCalldataHash` hashes ONLY `{data,to,value}` sorted to byte-match the backend Python. `useWalletSigning.sign({mode})` modes: `evm_send`/`evm_typed_data`/`solana_send`. The Chrome MV3 extension aliases `@`→`../web` and reuses the web `ChatShell`.

### 3.18 Contracts / Deploy / Infra (`contracts-deploy-infra`)
**Purpose:** On-chain monetization + container topology + migrations.
**Key files:** `contracts/src/AffiliateHook.sol`, `script/DeployAffiliateHook.s.sol`, `docker-compose.yml`, root/web/sidecar `Dockerfile`s, `deploy/README.md`/`Caddyfile.example`, `alembic.ini`, `migrations/env.py` + versions, `start.sh`/`run-merged.sh`.
**How it works:** `AffiliateHook` is a **PancakeSwap V4 Infinity** CL hook (NOT Uniswap V4 — permissions in `PoolKey.parameters` bits, bitmap `0x0442`). Fees (scale 1e6): standard LP 3000 (0.30%), affiliate LP 2500 (0.25% — a user discount), distributor 500 (0.05%). `_beforeSwap` decodes `abi.encode(true)` to override the fee down and (exact-input only) take a 0.05% distributor cut as `BeforeSwapDelta`, accumulating `pendingFees`. `distributeFeesFor` is permissionless (vault.lock → `_settleDistribution` → `vault.take`). 6-container compose stack (api/solana-yield-builder/assistant-api/web/redis/postgres). Dual prod/staging VPS, Caddy TLS, Alembic agent_001..013 (linear chain by `down_revision`, NOT filenames).

### 3.19 Tests / Validation / Docs (`tests-scripts-docs`)
**Purpose:** Test suite, 8-gate validation pipeline, canonical docs.
**Key files:** `tests/defi/test_runtime_invariants.py`, `src/agent/runtime_invariants.py`, `streaming.py`, `schemas/agent.py`, `scripts/validation/post_deploy_smoke.py`/`static_sweep.py`/`regression_sweep.py`/`conversation_matrix.py`, `scripts/playwright_browser_smoke.py`, `anvil_fork_replay.py`, `tests/harness/v4_matrix.py`/`v4_runner.py`, `conftest.py`, `docs/SPEC_COVERAGE.md`, `V6_GAP_ANALYSIS.md`.
**How it works:** ~379 test files / ~2,529 functions. Dominant idiom is the "pin test" (assert a 4-byte selector per action; assert blocker in `KNOWN_BLOCKER_CODES`; structural `inspect.getsource` checks). 8 gates: G1 smoke, G2 matrix+sweeps, G3 invariants, G4 Playwright, G5 anvil fork, G6 re-audit, G7 docs, G8 conversation matrix + LLM judge. Validation scripts target live `staging.ilyonai.com`.

---

## 4. The Agent Runtime & Tool Protocol

### 4.1 SSE wire format
`encode_sse(event, data)` writes `event: <name>\ndata: <json>\n\n`. `frame_event_name` maps frame classes → event names.

| Event | Frame class | Carries |
|---|---|---|
| `thought` | ThoughtFrame | reasoning step text |
| `tool` | ToolFrame | tool name + input |
| `observation` | ObservationFrame | ok/err result |
| `card` | CardFrame | `{step_index, card_id, card_type, payload}` |
| `step_status` | StepStatusFrame | per-step status (`broadcast`/tx_hash/error) |
| `plan_complete` | PlanCompleteFrame | plan rollup |
| `plan_blocked` | PlanBlockedFrame | severity + reasons (critical Shield) |
| `final` | FinalFrame | `content`, `elapsed_ms`, `card_ids` |
| `done` | DoneFrame | terminator |

### 4.2 Card discriminated union
Backend source of truth: `src/api/schemas/agent.py` (`CardType` Literal + `_CardUnion` discriminator). Web mirror auto-generated to `web/types/agent.ts` (via `scripts/gen_agent_types.py`). `CardRenderer.tsx`'s `switch(card_type)` is the single dispatch point; `default → FallbackCard`.

**CardType strings:** `allocation`, `sentinel_matrix`, `execution_plan`, `execution_plan_v2`, `execution_plan_v3`, `swap_quote`, `pool`, `pool_link`, `pool_deposit_v3`, `token`, `position`, `plan`, `balance`, `balance_report`, `bridge`, `stake`, `market_overview`, `pair_list`, `defi_opportunities`, `sentinel`, `sentinel_token_report`, `sentinel_pool_report`, `sentinel_whale_feed`, `sentinel_smart_money_hub`, `sentinel_shield_report`, `sentinel_entity_card`, `compound_card`, `rebalance_card`, `migrate_card`, `invariant_violation`, `text`, `no_change`, `preferences`, `transfer`, `lp`.

> **Invariant gap:** The strict `_CardUnion` only covers ~17 of these; `sentinel_*_report`, `pool_link`, `transfer`/`lp`, etc. pass as loose dicts on `CardFrame.payload`.

### 4.3 Tool registry
`tools/__init__._TOOL_REGISTRY: dict[str, (fn, description)]` (28 entries). `register_all_tools(services, user_id, wallet, solana_wallet, evm_wallet)` wraps each in a `_late_bound(ctx)` `StructuredTool` with `_TOOL_SLO_SECONDS` timeout (default 45s → `TOOL_TIMEOUT` err). Every tool returns a `ToolEnvelope` `{ok, data, sentinel, shield, scoring_inputs, card_type, card_id, card_payload, extra_cards[], error}`. `ToolEnvelope(ok=False)` requires a non-null `error`. Error codes normalized to canonical UPPER_SNAKE (`quote_unavailable→NULL_ROUTE`, `missing_allowance→APPROVAL_MISSING`).

---

## 5. The Sentinel Scoring Model

> **There are TWO distinct "Sentinel scores."** Conflating them is the single biggest hazard.

### 5.1 Structured pool/route/bridge score (the explicit weighted composite)
`src/scoring/pool_scorer.py::score_pool_mapping` → `normalizer.pool_candidate_from_mapping` → `rubric.score_pool_candidate` → four pure scorers in `src/allocator/composer.py`:

| Dimension | Base | Bonuses | Weight |
|---|---|---|---|
| **Safety** | 40 | +25 audited, +20/+12/+6 TVL tier, +10 single-exposure, +5 no-IL | **0.40** |
| **Durability** | 30 | +25/+15 tenure, +25/+12/+4 APY band, +10 stable | **0.25** |
| **Exit** | 35 | +35/+25/+15 TVL, +12 stable, +10 single | **0.20** |
| **Confidence** | 40 | +20 audited, +25/+18/+8 tenure | **0.15** |

`weighted_sentinel = round(0.40·safety + 0.25·durability + 0.20·exit + 0.15·confidence)`. `bucket_risk` cutoffs 82/65 → low/medium/high; `bucket_fit` → conservative/balanced/aggressive. This is the **only** place a real linear weight vector exists; it lands in `SentinelBlock`. Route scorer derives from penalty deductions off 80; bridge scorer reuses the pool path and downgrades a SAFE shield to CAUTION/B.

### 5.2 Token-security composite (AI-primary)
`src/core/scorer.py::TokenScorer.calculate(token) -> AnalysisResult`. **`BASE_WEIGHTS` is vestigial/DEAD** — the final `overall_score = token.ai_score + adjustments` (hand-tuned bonus/penalty ladder: −20 mint authority, −15 unlocked LP, +5 renounced, −10 high whale concentration), clamped 0-100, with hard caps: already-rugged → 0/F, known-scammer deployer → ≤25, confirmed honeypot → ≤15. Deployer reputation (`analytics/wallet_forensics`), predictive rug (`anomaly_detector` `rug_probability` + `time_to_rug_estimate`), whale concentration (distribution sub-score) feed the adjustments.

### 5.3 Shield (approval surface)
`shield_gate.shield_for_transaction` accumulates severity 0-4 → `ShieldBlock` (verdict SAFE/CAUTION/RISKY/DANGEROUS/SCAM, grade A+..F). `shield/approval_scanner.ApprovalScanner.scan_wallet` scores each approval 0-100 (**higher = worse** — inverted vs Sentinel). `sentinel_lite` projects one ticker number = `min(shield_score, pool_sentinel)`.

---

## 6. Execution & Signing

### 6.1 Per-chain/protocol unsigned-tx building
- **EVM swap/stake/LP:** Enso shortcuts API (`api.enso.build`), via the wallet-assistant `crypto_agent._build_enso_swap_tx` (in-proc) or `EnsoShortcutAdapter`. **No 0x/1inch** — removed.
- **Solana swap/stake:** Jupiter (`api.jup.ag`, requires key since 2026-01-31).
- **Solana yield (LP/deposit):** Solana Yield Builder sidecar (`:8090`), native SDKs per protocol + Jupiter prep-swap fallback.
- **Cross-chain bridge:** deBridge DLN (`/dln/order/create-tx`); LiFi/Socket only for gas top-ups.
- **EVM yield:** `AdapterRegistry` (Aave/Compound/Curve/Balancer/LST/ERC4626/Pendle native + Enso catch-all).

### 6.2 Simulation gating
- **At serialization:** `UnsignedStepTransaction.stamp_simulation()` stamps `simulated_calldata_hash` (SHA-256 `{to,data,value}`) + `simulated_at`.
- **At broadcast:** `broadcast.broadcast_step` — 30s freshness re-sim (`SIM_FRESHNESS_THRESHOLD_SEC=30`), Tenderly bundle (EVM) / Solana `simulateTransaction`, MEV routing, then `mark_step_status('submitted')` enforcing the **V7-001 calldata bind** (`assert_calldata_match`) + §11 D.2 freshness + D.7 price-drift. Hard-raises only when `IL_STRICT_STATE=1`.
- **Sidecar:** every adapter pre-simulates before returning; benign empty-wallet reverts pass.
- **Execution double-gate:** `pool_exec_enabled()` (`POOL_EXEC_ENABLED`, default OFF) AND `PROVEN_EXEC` fork-proven combos. Sim-passing is explicitly NOT sufficient.

### 6.3 Account abstraction & signing
- **EIP-7702:** digest `keccak(0x05 || rlp([chain_id, impl, nonce]))`; Biconomy Nexus impl `0x000000aC74357BFEa72BBD0781833631F732cf19`, ZeroDev Kernel `0xd6CEDDe84be40893d153Be9d467CD6aD37875b28`. ERC-7579 `installModule` (`0x9517e29f`) / `uninstallModule` (`0xa71763a8`).
- **Session keys:** `SessionKeyPolicy.can_authorise` — per-tx cap checked BEFORE 24h/total caps (P1-C-005), + protocol/action/asset allowlists + expiry/revoke. Two mirror modules cross-check on-chain (`isModuleInstalled 0x112d3a7d`) — but `fetch_onchain_policy` is a stub.
- **Permit2:** EIP-712 `eth_signTypedData_v4` against `0x000000000022D473030F116dDEE9F6B43aC78BA3` → POST `/api/v1/plans/{plan}/steps/{step}/permit2` → runtime splices into V4 `modifyLiquidities` calldata.
- **Web signing gate:** `useWalletSigning` runs `assertFresh` + `computeCalldataHash` bind BEFORE the wallet pops.

### 6.4 deBridge webhook settlement

---

## 7. Data & Config

### 7.1 Providers
DefiLlama (TVL/yields/prices/stablecoins/bridges, no key), DexScreener (pairs/derived trending, no key), CoinGecko (free/Pro), GoPlus (EVM security), RugCheck (Solana LP-lock), Helius (Solana RPC/DAS/enhanced REST, rotating key pool), public Solana RPC, Jupiter (swap + price, key required), Moralis (EVM balances, own rotator), Enso, Merkl (reward APR), Orca/Raydium (Solana pool resolution), public EVM RPC fallback pools, Tenderly (EVM sim), Grok/xAI (narrative), OpenRouter/OpenAI (LLM). **Birdeye/GeckoTerminal NOT implemented.**

### 7.2 DB tables (Postgres, db `ilyon_ai`)
Auto-created (shared `Base`): `users`, `analyses`, `web_analyses`, `referrals`, `web_users`, `user_sessions`, `wallet_reputations`, `token_deployments`, `blinks`, `blink_analytics`, `alert_rules`, `alert_records`, `alert_audit_records`, `contract_scan_cache`, `tracked_wallets`, `whale_transactions`, `transaction_cache`, `agent_preferences`, `agent_chats`, `agent_chat_messages`, `agent_plans`, `chats`, `chat_messages`. Migration-managed (own bases): `pool_index` (agent_005), `user_positions`, `position_snapshots` (agent_006/011), `position_alerts` (agent_006/012), `intent_state` (agent_013), `user_smart_accounts`/`session_key_policies`/`session_key_audit_log` (agent_007), `debridge_events`/`biconomy_session_authorizations`.

### 7.3 Redis caches
Analysis (`analysis:<addr16>`), fast-lane snapshots (`opportunity:fast_lane:<id>`), rate-limit counters, sessions (`session:<token>`), DeFi analysis/evidence (`defi:analysis:*`/`defi:evidence:*`). In-process caches: DefiLlama pools (30s), price_oracle (60s), v3 pool resolver (5min), pool_address_authoritative (process-lifetime), strategy memory (session, cap 32).

### 7.4 Central settings (`src/config.py Settings`, instance `settings`)

---

## 8. Deploy & Infra

### 8.1 docker-compose service graph
6 services: `api` (Sentinel aiohttp :8080, python:3.11-slim + Playwright) → depends on redis+postgres+solana-yield-builder; `solana-yield-builder` (Node 20 :8090, internal); `assistant-api` (FastAPI :8000); `web` (Next.js standalone :3000, bakes `API_REWRITE_TARGET=http://api:8080`/`ASSISTANT_API_TARGET=http://assistant-api:8000`/`AGENT_BACKEND=hybrid` at BUILD time) → depends on api+assistant healthy; `redis` (7-alpine, appendonly, 100mb LRU); `postgres` (15-alpine, db `ilyon_ai`). Inter-service URLs are Docker DNS names. `api` bind-mounts the assistant server dir read-only (NOT baked into the image) + sets PYTHONPATH.

### 8.2 VPS topology
One VPS (173.249.5.167), two isolated stacks: `ai-sentinel`→ilyonai.com (api 8080/web 3000), `ilyonai-staging`→staging.ilyonai.com (api 18080/web 13000), each its own dir/branch/.env/volumes (staging via `git worktree`). Caddy terminates TLS: `@api` matcher (`/api/*`, `/health`, `/actions`, `/.well-known/*`, `/webhook`, `/blinks/*`) → aiohttp port, else → Next.js port. Cloudflare proxies DNS.

### 8.3 Migrations & CI
Alembic (async, `script_location=migrations`), 14 revisions agent_001..013 chained by `down_revision` (NOT filenames). **`alembic upgrade` is not invoked by any Dockerfile/compose entrypoint — run manually.** **No CI/CD** (.github has only PR template); deploy is manual `git pull --ff-only` + `docker compose up -d --build`.

### 8.4 AffiliateHook contract
PancakeSwap V4 Infinity CL hook (`contracts/src/AffiliateHook.sol`). Bitmap `0x0442` (afterInitialize|beforeSwap|beforeSwapReturnDelta) in `PoolKey.parameters`. Standard LP 0.30% / affiliate LP 0.25% (user discount) / distributor 0.05% (exact-input only, taken as `BeforeSwapDelta`). `distributeFeesFor` permissionless (`vault.lock` → `_settleDistribution` → `vault.take`). Test is a no-op stub; no foundry config in-tree.

---

## 9. Cross-Cutting Concerns & Invariants

### 9.1 Runtime invariants (the structural fail-safe)

### 9.2 Anti-hallucination spine

### 9.3 Sanitization
`sanitizer.sanitise_onchain_string` (homoglyph/control strip, injection-pattern redaction) + `sanitizer_entry.sanitize_for_planner` defend against prompt injection in on-chain token names/metadata.

### 9.5 Hard invariants
RC7a (`assert_signable_composed_plan`: every non-blocked step must have `transaction != None`). V7-001 (`assert_calldata_match`: calldata-hash bind). Recovery hard rule (no auto refund-swap-back, `guard_refund`). Session-key per-tx cap before 24h/total. The agent NEVER broadcasts.

## 10. Map for Future Development

| To add… | Touch these files |
|---|---|
| **A new agent tool** | implement `async fn(ctx, **kwargs) -> ToolEnvelope` in `tools/`; register in `tools/__init__._TOOL_REGISTRY` + `_TOOL_SLO_SECONDS`; add a `_detect_*` branch (or `INTENT_PATTERNS`) in `simple_runtime.detect_intent`; add a `_format_tool_result` branch |
| **A new card type** | add Literal to `CardType` + payload model + `*Card` to `_CardUnion` in `src/api/schemas/agent.py`; regen `web/types/agent.ts`; add a `case` in `CardRenderer.tsx`; add any P0 rule to `runtime_invariants` |
| **A new SSE frame** | define a `_Strict` model in `schemas/agent.py`; add to `frame_event_name` map + `SSEFrame` union in `streaming.py`; add a collector `emit_*` helper; handle in BOTH `parseAgentSseResponse` (MainApp) and `useAgentStream` |
| **A new chain** | `ChainType` enum + property maps + `EVM_CHAIN_CONFIGS` (`chains/base.py`); `chains/registry.py` rpc map; `AddressResolver` aliases; `settings` RPC field; `asset_registry.RPC_FALLBACKS`; CHAIN_IDS/CHAIN_PATTERNS/TOKEN_DECIMALS in `simple_runtime`; provider chain maps; AA chain sets |
| **A new EVM protocol adapter** | implement `YieldAdapter` (chains/protocols/actions frozensets + `supports`/`quote`/`build`/`verify`) in `src/defi/execution/adapters/`; register in `build_default_registry()` at correct precedence; add slug to `reliable_set` + `protocol_urls.PROTOCOL_APP_URL` + `pool_types.POOL_TYPE_REGISTRY` + (V3) `_V3_FACTORIES`; add to Python `supports()` allowlist |
| **A new Solana protocol** | create `services/solana-yield-builder/src/adapters/<name>.js` ({aliases,supportedActions,quote,build,verify}); `registerAdapter` in `index.js`; add slug to Python `SolanaYieldBuilderAdapter.protocols` |
| **A new bridge** | implement `composed_plan.Bridge` protocol (name/quote/status) like `DeBridgeBridge`; wire into `gas_topup_bundler` and/or the main bridge leg |
| **A new HTTP route** | `routes/<name>.py` with `setup_<name>_routes(app)`; register in BOTH `create_api_app()` and `setup_api_routes()` in `api/app.py`; add Caddy `@api` path if non-`/api` prefix; add `lib/api.ts` fn + `lib/hooks.ts` hook + `nav-config.ts` entry on the web side |
| **A runtime invariant** | `_iN(card_type,payload)->list[Violation]` appended to `_INVARIANTS` in `runtime_invariants.py` (P0 refuse vs P1 log/clamp) + 1 positive/1 violating pin test |
| **An anti-hallucination guard** | compiled `_UNBACKED_*` regex + `hits.append` branch in `_strip_unbacked_claims` |
| **A recovery posture** | extend `FailureKind`/`RecoveryAction` + `decide_recovery` tree in `recovery/stuck_balance.py` |
| **A receipt verifier** | row in `RECEIPT_TABLE` + reader in `receipt_reader.py` + `_RECEIPT_KIND_BY_PROTOCOL_ACTION` |
| **A scoring dimension** | `score_*` in `allocator/composer.py` + `weighted_sentinel` + `SentinelBlock` schema (strict, all consumers update) |
| **An LLM provider** | subclass `BaseAIClient` (`src/ai/base.py`); wire in `AIRouter.__init__` (no function-calling exists; tool routing is Python-side) |
| **A closed-bug probe / static anti-pattern / matrix chain** | `PROBES` in `post_deploy_smoke.py` / `PATTERNS` in `static_sweep.py` / `Chain(...)` in `v4_matrix.py` (+ `v4_gaps.EXPECTED_BLOCKED`) |

---
