# Agent Platform Merge — Design

**Date:** 2026-04-21
**Status:** Draft → review
**North star:** A single unified Ilyon platform where every feature of the IlyonAi Wallet Assistant runs through Ilyon Sentinel's scoring engines. The existing `/agent/chat` and `/agent/swap` mockups are the visual contract the live product must match.

---

## 1. Architecture

### 1.1 Topology

One backend (aiohttp, `src/`), one frontend (Next.js, `web/`), one PostgreSQL, one users table, one auth system, one config. The `IlyonAi-Wallet-assistant-main/` tree is source material — none of its runtime (FastAPI, SQLite, uvicorn, separate user table) survives.

```
web/ (Next.js)                     src/ (aiohttp)                    External
─────────────                      ──────────────                    ────────
/agent/chat   ─┐                   /api/v1/agent/*  ─┐               Enso, Jupiter,
/agent/swap   ─┤                    ├─ LangChain ReAct                deBridge DLN,
/agent/*      ─┼─► HTTP/SSE ──►     │   wraps src/ai/router           DefiLlama, DexScreener,
tokens bar    ─┤                    ├─ 14 tools → Ilyon services      Moralis, Helius,
chrome ext    ─┘                    ├─ Sentinel decorator             Binance/CoinGecko,
                                    ├─ Shield cross-check             on-chain RPCs,
                                    └─ ChatSession persistence        BNB Greenfield
```

### 1.2 Parallel workstreams

| # | Workstream | Owns |
|---|---|---|
| W1 | Backend agent core | LangChain wrap of `src/ai/router`, ReAct loop, memory, SSE streaming |
| W2 | Tool layer | 14 tools bound to Ilyon services (per-tool mapping §3.2) |
| W3 | Sentinel/Shield decorator | Post-tool enrichment: every pool/token response gets scores + verdict |
| W4 | Auth | Ilyon challenge/verify + MetaMask ECDSA + email/password on one `users` table |
| W5 | Chat persistence | `chats` and `chat_messages` tables in Ilyon's async PG |
| W6 | Frontend agent surface | Port `MainApp.tsx` → `web/components/agent/*`, wire to live API |
| W7 | Structured cards | Server-driven card schema replaces mock cards in `/agent/chat` |
| W8 | Tokens top bar | Price ticker component wired to Ilyon price service |
| W9 | Swap page live | `/agent/swap` hits real quote/build endpoints |
| W10 | Chrome extension | Port popup + sidepanel, point at Ilyon backend |
| W11 | AffiliateHook + Greenfield | Solidity hook contract + BNB Greenfield memory store |

### 1.3 Integration seams (contracts frozen before parallel work starts)

1. **Tool response envelope** — every tool returns `{data, sentinel?, shield?, card_type, card_payload}`. W2/W3/W7 depend on this.
2. **Card schema** — discriminated union keyed on `card_type`: `"allocation" | "swap_quote" | "pool" | "token" | "position" | "plan" | "balance" | "bridge" | "stake"`.
3. **Sentinel decorator interface** — `decorate(tool_name: str, raw: dict) -> dict` invoked post-tool in the ReAct loop.
4. **Agent session contract** — `POST /api/v1/agent` with body `{session_id, message, wallet?}`; response is SSE frames `{type: "thought"|"tool"|"observation"|"card"|"final", payload}`.
5. **Auth token** — unified JWT: `sub=user_id`, `scopes: string[]`, `wallet_address?`, `email?`, `exp`.

Contracts 1–5 ship as empty type stubs in a single day-0 PR; everything else forks from there.

---

## 2. Backend component breakdown

### 2.1 Module layout (new files under `src/`)

```
src/
├── agent/
│   ├── __init__.py
│   ├── runtime.py            # LangChain AgentExecutor, session memory
│   ├── llm.py                # LangChain BaseChatModel wrapping src/ai/router
│   ├── session.py            # ChatSession persistence + window memory
│   ├── streaming.py          # SSE frame encoder, thought/tool/observation/card/final
│   ├── decorator.py          # Sentinel + Shield post-tool enrichment
│   ├── cards.py              # Card envelope builders (discriminated union)
│   └── tools/
│       ├── __init__.py       # register_all_tools(services)
│       ├── balance.py        # get_wallet_balance  → PortfolioService
│       ├── price.py          # get_token_price     → PriceService
│       ├── swap_simulate.py  # simulate_swap       → RouterService
│       ├── swap_build.py     # build_swap_tx       → EnsoClient
│       ├── solana_swap.py    # build_solana_swap   → JupiterClient
│       ├── market_overview.py# get_defi_market_overview → DefiLlamaClient
│       ├── analytics.py      # get_defi_analytics  → tiered dispatch
│       ├── staking.py        # get_staking_options → OpportunityEngine + metadata
│       ├── dex_search.py     # search_dexscreener_pairs → DexScreenerClient
│       ├── pool_find.py      # find_liquidity_pool → Ilyon + DexScreener fallback
│       ├── stake_build.py    # build_stake_tx
│       ├── lp_build.py       # build_deposit_lp_tx
│       ├── bridge_build.py   # build_bridge_tx     → deBridge DLN
│       └── transfer_build.py # build_transfer_tx
├── api/routes/
│   ├── agent.py              # POST /api/v1/agent, GET /sessions, GET /sessions/{id}
│   └── tokens_bar.py         # GET /api/v1/tokens/ticker (already partial; extend)
├── storage/
│   └── chat.py               # ChatSession, ChatMessage CRUD (async SQLAlchemy)
└── models/
    └── chat.py               # ORM: Chat, ChatMessage (FK to existing users)
```

### 2.2 Agent runtime

- `AgentExecutor` built from LangChain `create_react_agent` with Ilyon's LLM wrapper.
- `ConversationBufferWindowMemory(k=10)` per `session_id`, hydrated from PG on first message of a session, persisted after each turn.
- System prompt forked from assistant's `CryptoAgent.system_prompt`, edited to describe Ilyon's scoring vocabulary (Sentinel 0–100, Safety, Durability, Exit, Confidence, risk_level, strategy_fit, Shield verdict).
- Rate limit: 0.5s min gap per user (ported from `endpoints.py`), + per-IP fallback using Ilyon's existing middleware.
- Output sanitizer: port `_clean_agent_output` to strip leaked `Thought:`/`Action:` scaffolding from `final` frames.
- Query normalizer: port `_normalize_short_swap_query` for shorthand like `🔄 Swap BNB → USDT`.

### 2.3 LLM wrapper (`src/agent/llm.py`)

```python
class IlyonChatModel(BaseChatModel):
    """LangChain BaseChatModel backed by src/ai/router.RouterClient.

    Supports OpenAI-compatible chat completions, streams tokens, forwards
    tool_calls. Uses Ilyon's existing provider fallback chain.
    """
    router: RouterClient
    model: str
    temperature: float = 0.2

    def _generate(self, messages, stop=None, **kwargs) -> ChatResult: ...
    async def _astream(self, messages, stop=None, **kwargs): ...
```

Dispatches through `RouterClient.complete(...)` so the existing model-routing, retries, and cost accounting in Ilyon apply to the agent.

### 2.4 SSE framing (`src/agent/streaming.py`)

```
event: thought       data: {"content": "I should check the top staking APYs..."}
event: tool          data: {"name": "get_staking_options", "args": {...}}
event: observation   data: {"name": "get_staking_options", "ok": true}
event: card          data: {"card_type": "allocation", "payload": {...}}
event: final         data: {"content": "Here's the allocation...", "cards": ["id1"]}
event: done          data: {}
```

The AgentExecutor is wrapped in a custom callback handler that emits these frames on `on_llm_start`, `on_tool_start`, `on_tool_end`, and a post-tool decorator hook that emits `card` when the Sentinel decorator returns a `card_payload`.

### 2.5 Sentinel + Shield decorator (`src/agent/decorator.py`)

```python
async def decorate(tool_name: str, raw: dict, ctx: ToolCtx) -> DecoratedResult:
    """Enrich any tool output with Sentinel scores + Shield verdict.

    - pool-shaped: OpportunityEngine.summarize(pool) → sentinel block
    - token-shaped: ShieldService.verdict(mint) → shield block
    - portfolio-shaped: run each position through both
    - swap_quote: Shield both legs + flash-risk heuristic
    Emits a card_payload matching the frontend discriminated union.
    """
```

A static `DECORATION_MAP` routes each of the 14 tools to one or more enrichers and a card builder; tools with no relevant decorator pass through untouched but still get a typed `card_payload`.

### 2.6 Existing Ilyon services the tools bind to

| Tool | Primary service | Fallback |
|---|---|---|
| `get_wallet_balance` | `PortfolioService` (Ilyon) | — |
| `get_token_price` | `PriceService` (Binance + CoinGecko) | DexScreener |
| `simulate_swap` | `RouterService.quote` | — |
| `build_swap_tx` | `EnsoClient.build` | — |
| `build_solana_swap` | `JupiterClient.build` | — |
| `get_defi_market_overview` | `DefiLlamaClient.protocols` | — |
| `get_defi_analytics` | **Tiered**: `MarketScanPipeline` (list queries), `OpportunityEngine.deep(pool)` (specific) | DefiLlama raw |
| `get_staking_options` | `OpportunityEngine` (filter `category='liquid-staking'|'staking'`) + `StakingMetadataService` overlay | — |
| `search_dexscreener_pairs` | `DexScreenerClient.search` | — |
| `find_liquidity_pool` | `OpportunityEngine.find_pool` (primary) → `DexScreenerClient` (fallback for uncovered meme/long-tail) | — |
| `build_stake_tx` | `StakeBuilder` (per-protocol adapters: Lido, Rocket Pool, Jito, Marinade, etc.) | — |
| `build_deposit_lp_tx` | `LpBuilder` (Uniswap v3, PancakeSwap, Raydium) | — |
| `build_bridge_tx` | `DeBridgeClient.dln_build` | — |
| `build_transfer_tx` | Chain-native tx builder (ethers / solana-py) | — |

---

## 3. Frontend component breakdown

### 3.1 Module layout

```
web/
├── app/agent/
│   ├── chat/page.tsx          # becomes live; replaces current mockup
│   ├── swap/page.tsx          # becomes live; replaces current mockup
│   ├── portfolio/page.tsx     # new: live portfolio view
│   ├── staking/page.tsx       # new: live staking discovery
│   └── sessions/page.tsx      # new: session history
├── components/agent/
│   ├── ChatShell.tsx          # layout: sidebar + main + sidepanel
│   ├── MessageList.tsx
│   ├── AssistantBubble.tsx    # ported from current mockup
│   ├── UserBubble.tsx
│   ├── ReasoningAccordion.tsx # ported from current mockup (SSE-driven)
│   ├── Composer.tsx           # input with quick chips + wallet context
│   ├── Sidebar.tsx            # session list
│   ├── SidePanel.tsx          # context: wallet, chain, settings
│   └── cards/
│       ├── AllocationCard.tsx       # ported from current mockup
│       ├── SwapQuoteCard.tsx        # ported, live quote
│       ├── PoolCard.tsx             # Sentinel matrix + flags
│       ├── TokenCard.tsx            # Shield verdict + price
│       ├── PositionCard.tsx
│       ├── PlanCard.tsx             # multi-step execution plan
│       ├── BalanceCard.tsx
│       ├── BridgeCard.tsx
│       └── StakeCard.tsx
├── components/tokens-bar/
│   ├── TokensTicker.tsx       # top bar; ported from assistant MainApp.tsx
│   └── TickerItem.tsx
├── hooks/
│   ├── useAgentStream.ts      # SSE consumer with reconnect
│   ├── useSession.ts
│   └── useSessions.ts
└── lib/
    └── agent-client.ts        # typed SSE POST + JSON GET helpers
```

### 3.2 Card discriminated union (shared schema)

```ts
export type AgentCard =
  | { card_type: 'allocation';  payload: AllocationPayload }
  | { card_type: 'swap_quote';  payload: SwapQuotePayload }
  | { card_type: 'pool';        payload: PoolPayload }
  | { card_type: 'token';       payload: TokenPayload }
  | { card_type: 'position';    payload: PositionPayload }
  | { card_type: 'plan';        payload: PlanPayload }
  | { card_type: 'balance';     payload: BalancePayload }
  | { card_type: 'bridge';      payload: BridgePayload }
  | { card_type: 'stake';       payload: StakePayload };
```

Every payload carries the Sentinel block `{sentinel: number, safety, durability, exit, confidence, risk_level, strategy_fit, flags[]}` when the decorator attached it, plus `shield: {verdict, grade, reasons[]}` where relevant. Types live in `web/types/agent.ts` and mirror Pydantic models in `src/api/schemas/agent.py` (generated via existing type-gen pipeline).

### 3.3 Tokens top bar

- Ported 1:1 from `IlyonAi-Wallet-assistant-main/.../MainApp.tsx` ticker.
- Mounts in root layout above the nav.
- Driven by `GET /api/v1/tokens/ticker` returning top N tokens with live price, 24h %, and Sentinel-lite badge.
- Respects hide-on-scroll + reduce-motion.

### 3.4 Porting policy

- Strip any assistant-specific branding (there is none in practice — the assistant's CSS already uses Ilyon emerald).
- Replace `fetch('http://localhost:8000/api/v1/agent')` with `agent-client.ts` pointing at Ilyon backend.
- Replace assistant's JWT storage (`localStorage['token']`) with Ilyon's existing `useAuth` session mechanism.

---

## 4. Auth

### 4.1 Strategy

Keep Ilyon's challenge/verify/session-store flow (`src/api/routes/auth.py`). Extend it with two capabilities ported from the assistant:

1. **MetaMask ECDSA verifier** — `verify_ethereum_signature(address, message, signature)` using `eth_account.messages.encode_defunct` + `Account.recover_message`. New file `src/auth/ethereum.py`.
2. **Email + password fallback** — new endpoints `POST /api/v1/auth/register` and `POST /api/v1/auth/login` on the existing users table; argon2 via `passlib`.

### 4.2 Unified users table

Existing Ilyon `users` table extended (Alembic migration):

```sql
ALTER TABLE users
    ADD COLUMN email          VARCHAR(255) UNIQUE,
    ADD COLUMN password_hash  VARCHAR(255),
    ADD COLUMN display_name   VARCHAR(100);
CREATE INDEX ix_users_email ON users (email);
```

`wallet_address` already exists. No data loss; both auth paths resolve to the same row.

### 4.3 Endpoints

```
POST /api/v1/auth/challenge     (existing)  → {challenge, ttl}
POST /api/v1/auth/verify        (existing)  → {token, user}    # Solana Ed25519
POST /api/v1/auth/verify-evm    (new)       → {token, user}    # MetaMask ECDSA
POST /api/v1/auth/register      (new)       → {token, user}    # email+password
POST /api/v1/auth/login         (new)       → {token, user}    # email+password
POST /api/v1/auth/refresh       (existing)
POST /api/v1/auth/logout        (existing)
GET  /api/v1/auth/me            (existing)
```

### 4.4 Token

Single JWT issued by `create_token(user_id, scopes, wallet_address?, email?)` — already present in Ilyon. Assistant's `app/core/security.py` is discarded.

---

## 5. Data model

### 5.1 New tables (Alembic migration)

```sql
CREATE TABLE chats (
    id            VARCHAR(36)  PRIMARY KEY,     -- uuid4
    user_id       INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title         VARCHAR(200) NOT NULL DEFAULT 'New Chat',
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX ix_chats_user_id ON chats (user_id);

CREATE TABLE chat_messages (
    id         BIGSERIAL    PRIMARY KEY,
    chat_id    VARCHAR(36)  NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role       VARCHAR(20)  NOT NULL,            -- 'user' | 'assistant' | 'tool'
    content    TEXT         NOT NULL,
    cards      JSONB,                            -- array of AgentCard
    tool_trace JSONB,                            -- thought/action/observation frames
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX ix_chat_messages_chat_id ON chat_messages (chat_id, created_at);
```

### 5.2 Persistence rules

- One row per message; assistant messages store the final content + cards + full tool trace.
- Window memory rehydrates the last k=10 messages on session resume.
- `DELETE /api/v1/agent/sessions/{id}` cascades.

---

## 6. Data flow (single turn)

```
User types "Allocate $10k across best stETH/SOL staking"
   │
   ▼
POST /api/v1/agent  {session_id, message, wallet}
   │
   ▼
agent/runtime.py
   ├─ load ChatSession, hydrate window memory
   ├─ AgentExecutor.astream(input)
   │    ├─ LLM → Thought + Action(get_staking_options, args)
   │    │    → SSE frame: thought, tool
   │    ├─ tools.staking → OpportunityEngine.scan(cat='staking')
   │    ├─ decorator.decorate('get_staking_options', raw)
   │    │    → Sentinel scores per pool, Shield per token
   │    │    → card_payload: AllocationPayload
   │    │    → SSE frame: observation, card
   │    ├─ LLM → Action(build_stake_tx, args) for top-N picks
   │    │    → SSE frame: tool, observation, card (plan)
   │    └─ LLM → Final Answer
   │         → SSE frame: final, done
   ├─ persist ChatMessage (user + assistant rows, cards + trace)
   └─ close SSE
```

---

## 7. Error handling

| Failure | Behavior |
|---|---|
| LLM provider down | `RouterClient` fallback chain; if all fail, emit `final` frame with graceful message + `error` metadata. |
| Tool raises | `on_tool_error` callback emits `observation` frame with `{ok:false, error}`; decorator skipped; agent sees error and either retries or apologizes. |
| Tool timeout (15s default, 45s for `build_*`) | `asyncio.wait_for`; same as raise. |
| Sentinel/Shield decorator fails | Log, attach `sentinel: null`, continue; card still renders without score block. |
| SSE client disconnect | Task cancelled; partial trace persisted with `status='cancelled'`. |
| Rate limit hit | 429 with `Retry-After`; frontend shows inline banner. |
| Auth expired mid-stream | 401 emitted as SSE `final` frame with `error: 'auth_expired'`; frontend triggers refresh. |
| DB write fails after successful turn | Best-effort retry 3x; on total failure, log and return response anyway (message shown, not persisted — user notified inline). |
| Moralis/DefiLlama upstream 5xx | Circuit breaker (existing in Ilyon) opens; tool returns degraded payload with `stale: true`. |

---

## 8. Testing strategy

### 8.1 Unit

- Each tool in `src/agent/tools/*` gets a unit test with a mocked service.
- Decorator mapping table: one test per tool confirming correct enricher + card_type.
- LLM wrapper: streaming, tool-call forwarding, stop tokens.
- Auth verifiers: MetaMask signature round-trip (known fixture), Phantom Ed25519 (existing), email hash + verify.
- Card schema: round-trip Pydantic ↔ TS via fixture corpus.

### 8.2 Integration

- Agent runtime with real LLM disabled (deterministic stub) + real Ilyon services (against seeded test DB + recorded VCR cassettes for external APIs).
- SSE end-to-end: spawn runtime, collect frames, assert sequence + card payloads.
- Session persistence: create → message → rehydrate → message → assert memory contains previous turn.
- Migration: run Alembic up/down on a scratch DB, confirm `users` extension + `chats`/`chat_messages` shape.

### 8.3 Surface

- Playwright: `/agent/chat` golden path (login → ask → stream → card renders → persist → refresh page → history shows).
- Playwright: `/agent/swap` (type → quote → build → signature prompt mocked).
- Playwright: Chrome extension popup loads, sidepanel opens, same agent stream renders.

### 8.4 Contract

- Generated TS types from Pydantic build-time; CI fails if `web/types/agent.ts` drifts.
- Fixture corpus of every `AgentCard` variant in `tests/fixtures/cards/`; both backend serializer and frontend renderer must accept the same fixtures.

---

## 9. Chrome extension (W10)

- Ported from `IlyonAi-Wallet-assistant-main/extension/`.
- `popup.html` and `sidepanel.html` both mount the same React shell as `web/app/agent/chat` (shared component library).
- Backend URL is build-time env (`ILYON_API_BASE`).
- Auth: extension stores JWT in `chrome.storage.local`; refresh flow identical to web.
- Content script injects a floating launcher only on host allowlist; respects user toggle in options page.

---

## 10. Contracts + Greenfield (W11)

### 10.1 AffiliateHook.sol

- Ported verbatim from `IlyonAi-Wallet-assistant-main/contracts/AffiliateHook.sol`.
- Foundry project lives at `contracts/` in repo root (new).
- Deploy script targets PancakeSwap Infinity on BSC mainnet + testnet.
- Backend reads fees via existing `OnChainReader`; no new RPC client needed.

### 10.2 Greenfield memory store

- `GreenfieldService.ts` ported to backend as `src/storage/greenfield.py` (python-bnb-greenfield or direct HTTP to Greenfield SP).
- Stores long-term agent memory (distilled summaries beyond window memory k=10).
- Per-user bucket; object key = `{user_id}/{session_id}.json`.
- Read on session resume after warm DB hydration; write on session end or every N turns.
- Feature-flagged (`FEATURE_GREENFIELD_MEMORY`) so local dev works without BNB Greenfield creds.

---

## 11. Config + secrets

All assistant keys move into `src/config.py` as pydantic-settings fields and `.env`:

```
# LLM + router (existing)
# Data providers (existing + new)
MORALIS_API_KEY=                  # ROTATED — old JWT in crypto_agent.py:38 burned
DEXSCREENER_API_KEY=
# Bridges + routers
DEBRIDGE_API_BASE=
ENSO_API_KEY=
JUPITER_API_BASE=
# Chains
HELIUS_API_KEY=
BSC_RPC_URL=
# Greenfield
BNB_GREENFIELD_SP=
BNB_GREENFIELD_ACCOUNT=
BNB_GREENFIELD_PRIVATE_KEY=
# Feature flags
FEATURE_GREENFIELD_MEMORY=false
FEATURE_AFFILIATE_HOOK=false
```

Every hardcoded key in the assistant tree is deleted before first run. A pre-merge audit script (`scripts/audit_secrets.py`) greps for known key prefixes and fails CI if any slip through.

---

## 12. Rollout

1. **Day 0:** merge type stubs (contracts §1.3) + Alembic migration + empty route handlers → single PR, no behavior change.
2. **Parallel phase:** W1–W11 open in parallel. Each workstream ships behind a feature flag (`FEATURE_AGENT_V2`, `FEATURE_TOKENS_BAR`, `FEATURE_AFFILIATE_HOOK`, `FEATURE_GREENFIELD_MEMORY`, `FEATURE_CHROME_EXT`).
3. **Integration phase:** flags flipped on staging; Playwright surface tests gate promotion.
4. **Cutover:** `/agent/chat` and `/agent/swap` mockups replaced with live components; old mock components deleted from `web/app/agent/**`.
5. **Post-cutover:** `IlyonAi-Wallet-assistant-main/` tree deleted from repo (it was source material, not a runtime).

---

## 13. Out of scope (explicit)

- No support for the assistant's FastAPI, SQLite, or uvicorn runtime at any point — Ilyon's aiohttp + async PG is the only runtime.
- No dual-write between old and new user tables — one table, one migration.
- No preservation of the assistant's hardcoded Moralis JWT — it is burned and rotated before first run.
- No new branding — emerald everywhere (assistant already uses emerald).
- No partial rollout of "features but not scoring" — every tool response flows through the Sentinel decorator from day 1.
