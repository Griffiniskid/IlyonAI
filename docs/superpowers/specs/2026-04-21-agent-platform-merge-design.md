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
| W2 | Tool layer | 14 tools bound to Ilyon services (per-tool mapping §2.6) |
| W2a | Service adapters | Build any missing adapters the tools depend on (Enso, Jupiter, deBridge, Stake, LP) — see §2.7 |
| W3 | Sentinel/Shield decorator | Post-tool enrichment: every pool/token response gets scores + verdict |
| W4 | Auth | Ilyon challenge/verify + MetaMask ECDSA + email/password on extended `web_users` |
| W5 | Chat persistence | `chats` and `chat_messages` tables in Ilyon's async PG |
| W6 | Frontend agent surface | Port `MainApp.tsx` → `web/components/agent/*`, wire to live API |
| W7 | Structured cards + TS codegen | Server-driven card schema + Pydantic→TS generator |
| W8 | Tokens top bar | Price ticker component wired to Ilyon price service |
| W9 | Swap page live | `/agent/swap` hits real quote/build endpoints |
| W10 | Chrome extension (UI) | Port popup + sidepanel React shells, point at Ilyon backend |
| W11 | AffiliateHook + Greenfield | Solidity hook contract + BNB Greenfield memory store |
| W12 | Wallet adapters | MetaMask + Phantom connectors ported from assistant `client/src/wallets/*` |
| W13 | Extension background + content | Service worker, content-script launcher, options page |

### 1.3 Integration seams (contracts frozen before parallel work starts)

1. **Tool response envelope** — every tool returns:
   ```
   {
     ok: boolean,                         // false on tool failure
     data: object | null,                 // raw tool payload
     sentinel?: SentinelBlock,            // attached by §2.5 decorator when applicable
     shield?: ShieldBlock,                // attached by §2.5 decorator when applicable
     card_type: CardType | null,          // null for tools with no visual card (rare)
     card_id: string,                     // uuid, stable across persistence/re-render
     card_payload: object | null,         // matches discriminated union member for card_type
     error?: { code: string, message: string }
   }
   ```
   W2/W3/W7 all depend on this shape.

2. **Card schema** — discriminated union keyed on `card_type`:
   `"allocation" | "swap_quote" | "pool" | "token" | "position" | "plan" | "balance" | "bridge" | "stake" | "market_overview" | "pair_list"`. Generic list/aggregate tools (`get_defi_market_overview`, `search_dexscreener_pairs`) each get a dedicated variant so no tool ever has to fall back to an untyped renderer.

3. **Sentinel decorator interface** — `async decorate(tool_name: str, raw: dict, ctx: ToolCtx) -> DecoratedResult` invoked post-tool in the ReAct loop. Signature fixed at day 0.

4. **Agent session contract** — `POST /api/v1/agent` with body `{session_id, message, wallet?}`; response is SSE frames with typed `event:` lines and a JSON `data:` payload. Every step frame carries `step_index: int` (monotonic from 1); the `final` frame carries `elapsed_ms: int`. See §2.4 for the frame grammar.

5. **Auth token** — unified JWT: `sub=web_user_pk`, `scopes: string[]`, `wallet_address?`, `email?`, `exp`. `web_user_pk` is the extended `web_users` composite identity (see §4.2).

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
- Rate limit: 0.5s min gap per user, enforced via the existing rate-limit middleware at `src/api/middleware/rate_limit.py` (or a new per-session variant there if the current shape is global-only). New file is NOT added — this lives in the existing middleware module.
- Output sanitizer: port `_clean_agent_output` to strip leaked `Thought:`/`Action:` scaffolding from `final` frames.
- Query normalizer: port `_normalize_short_swap_query` for shorthand like `🔄 Swap BNB → USDT`.
- **Execution safety gate:** The LLM can chain `simulate_*` and read-only tools autonomously, but all `build_*_tx` tools (`build_swap_tx`, `build_solana_swap`, `build_stake_tx`, `build_deposit_lp_tx`, `build_bridge_tx`, `build_transfer_tx`) require either (a) an unsigned transaction returned to the client for user signature, or (b) an explicit user-approved plan card already acknowledged in session. The agent never broadcasts. Policy enforced at the tool boundary in §2.7 — each `build_*` tool returns `{unsigned_tx, simulation_result}`, and the frontend signs.

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
event: thought       data: {"step_index": 1, "content": "I should check the top staking APYs..."}
event: tool          data: {"step_index": 1, "name": "get_staking_options", "args": {...}}
event: observation   data: {"step_index": 1, "name": "get_staking_options", "ok": true, "error": null}
event: card          data: {"step_index": 1, "card_id": "uuid", "card_type": "allocation", "payload": {...}}
event: thought       data: {"step_index": 2, "content": "Next I should build the stake txs..."}
...
event: final         data: {"content": "Here's the allocation...", "card_ids": ["uuid1","uuid2"], "elapsed_ms": 4210, "steps": 8}
event: done          data: {}
```

`step_index` is monotonic across an agent turn and lets the frontend's `ReasoningAccordion` at `web/app/agent/chat/page.tsx` (which currently consumes `{steps, time, lines}`) render incrementally. `elapsed_ms` on `final` supplies the `time` prop.

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

A static `DECORATION_MAP` routes each of the 14 tools to one or more enrichers and a card builder. Every tool has an entry; `get_defi_market_overview` and `search_dexscreener_pairs` get `card_type: "market_overview"` and `"pair_list"` respectively, with Sentinel-lite badges on each row instead of full per-pool decoration.

### 2.6 Tool → service binding (with audit of what exists today)

Status column: ✅ service module exists in `src/`; 🟡 partial/needs extension; 🆕 new adapter required (W2a).

| Tool | Primary service | Status | Fallback |
|---|---|---|---|
| `get_wallet_balance` | `src/portfolio/multichain_aggregator.py` | ✅ | — |
| `get_token_price` | `src/pricing/price_service.py` (Binance + CoinGecko) | 🟡 audit coverage | DexScreener |
| `simulate_swap` | new `src/routing/quote_service.py` wrapping Enso+Jupiter | 🆕 | — |
| `build_swap_tx` | `src/routing/enso_client.py` | 🆕 port assistant's Enso integration | — |
| `build_solana_swap` | `src/routing/jupiter_client.py` | 🆕 port assistant's Jupiter integration | — |
| `get_defi_market_overview` | `src/defi/defillama_client.py` | ✅ | — |
| `get_defi_analytics` | **Tiered**: `src/defi/market_scan_pipeline.py` (lists) → `src/defi/opportunity_engine.py::deep` (specific) | ✅ (both exist) | DefiLlama raw |
| `get_staking_options` | `src/defi/opportunity_engine.py` (category filter) + new `src/defi/staking_metadata.py` overlay | 🟡 | — |
| `search_dexscreener_pairs` | `src/defi/dexscreener_client.py` | ✅ | — |
| `find_liquidity_pool` | `opportunity_engine.find_pool` → `dexscreener_client` fallback | ✅ | — |
| `build_stake_tx` | new `src/routing/stake_builder.py` (adapters: Lido, Rocket Pool, Jito, Marinade) | 🆕 | — |
| `build_deposit_lp_tx` | new `src/routing/lp_builder.py` (Uniswap v3, PancakeSwap, Raydium) | 🆕 | — |
| `build_bridge_tx` | new `src/routing/debridge_client.py` (DLN) | 🆕 | — |
| `build_transfer_tx` | new `src/routing/transfer_builder.py` (web3/solana-py) | 🆕 | — |

### 2.7 W2a — adapters to build

Every 🆕 row above is owned by W2a and must land before the matching W2 tool is flipped on. Each adapter exposes:

```python
async def build(...) -> BuiltTx:
    """Returns {unsigned_tx_hex | serialized_tx_b64, chain, simulation: SimulationResult}."""
```

The simulation field feeds the §2.2 execution safety gate — tools never sign, never broadcast.

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
│       ├── StakeCard.tsx
│       ├── MarketOverviewCard.tsx   # aggregate protocol stats
│       └── PairListCard.tsx         # DexScreener search results
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
type CardBase = { card_id: string };

export type AgentCard = CardBase & (
  | { card_type: 'allocation';       payload: AllocationPayload }
  | { card_type: 'swap_quote';       payload: SwapQuotePayload }
  | { card_type: 'pool';             payload: PoolPayload }
  | { card_type: 'token';            payload: TokenPayload }
  | { card_type: 'position';         payload: PositionPayload }
  | { card_type: 'plan';             payload: PlanPayload }
  | { card_type: 'balance';          payload: BalancePayload }
  | { card_type: 'bridge';           payload: BridgePayload }
  | { card_type: 'stake';            payload: StakePayload }
  | { card_type: 'market_overview';  payload: MarketOverviewPayload }
  | { card_type: 'pair_list';        payload: PairListPayload }
);
```

Every payload carries the Sentinel block `{sentinel: number, safety, durability, exit, confidence, risk_level, strategy_fit, flags[]}` when the decorator attached it, plus `shield: {verdict, grade, reasons[]}` where relevant. Types live in `web/types/agent.ts` and mirror Pydantic models in `src/api/schemas/agent.py` — generated by the W7 pipeline (see §8.4). `card_id` is a stable uuid set by the decorator; `ChatMessage.cards` JSONB stores the full card array keyed by this id, so a refresh re-renders with identical references.

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
2. **Email + password fallback** — new endpoints `POST /api/v1/auth/register` and `POST /api/v1/auth/login`; argon2 via `passlib`.

### 4.2 User table — extend `web_users`, do not touch `users`

The existing Ilyon `users` table (`src/storage/database.py:35-62`) is **telegram-bound** (`telegram_id BIGINT NOT NULL UNIQUE`, `referral_code VARCHAR(32) NOT NULL UNIQUE`) and belongs to the Telegram bot surface. The web surface already has its own table `web_users` (`src/storage/database.py:385-403`), keyed on `wallet_address VARCHAR(44) PRIMARY KEY`. The agent platform extends `web_users`, not `users`.

Alembic migration:

```sql
-- Add a synthetic integer primary key so chats/chat_messages can FK a stable opaque id,
-- independent of wallet_address rotation.
ALTER TABLE web_users ADD COLUMN id            BIGSERIAL;
ALTER TABLE web_users ADD COLUMN email         VARCHAR(255);
ALTER TABLE web_users ADD COLUMN password_hash VARCHAR(255);
ALTER TABLE web_users ADD COLUMN display_name  VARCHAR(100);

-- Unique email when present
CREATE UNIQUE INDEX ix_web_users_email
    ON web_users (email)
    WHERE email IS NOT NULL;

-- id becomes the application-level primary identifier; wallet_address stays a natural
-- secondary key (still UNIQUE via its old PK role, carried over by a new constraint).
ALTER TABLE web_users ADD CONSTRAINT web_users_id_unique UNIQUE (id);
-- wallet_address remains PRIMARY KEY to preserve existing FKs in user_sessions,
-- tracked_wallets, etc. No existing FK needs to change.

-- Allow a user row with only email (no wallet yet) by making wallet_address nullable-
-- but since it's PK we add a parallel table OR keep wallet_address PK and require
-- email users to have a derived placeholder wallet? Neither is clean.
--
-- DECISION: wallet_address stays PK for backward compat. Email-only users get a
-- synthetic sentinel wallet_address of the form "email:<sha256(email)[:36]>" which
-- is blocked from on-chain verification paths by the auth layer and replaced on
-- first wallet link via MERGE (see §4.5).
```

Existing Ilyon web-auth code continues to resolve users by `wallet_address`; new code resolves by `web_users.id`. JWT `sub` is `web_users.id` (integer), so the token format stays stable even if the user later links a wallet or changes email.

### 4.3 Endpoints

```
POST /api/v1/auth/challenge     (existing)  → {challenge, ttl}
POST /api/v1/auth/verify        (existing)  → {token, user}    # Solana Ed25519
POST /api/v1/auth/verify-evm    (new)       → {token, user}    # MetaMask ECDSA
POST /api/v1/auth/register      (new)       → {token, user}    # email+password
POST /api/v1/auth/login         (new)       → {token, user}    # email+password
POST /api/v1/auth/link-wallet   (new)       → {user}           # authenticated; links wallet to email account
POST /api/v1/auth/refresh       (existing)
POST /api/v1/auth/logout        (existing)
GET  /api/v1/auth/me            (existing)
```

### 4.4 Token

Single JWT issued by `create_token(user_id: int, scopes, wallet_address?, email?)`. `user_id` is `web_users.id`. Assistant's `app/core/security.py` is discarded entirely.

### 4.5 Account-merge path

If a user registers with email, then later signs a wallet challenge that proves ownership of an address matching a sentinel row, the two are merged inside a transaction: the email row's `id` is kept, `wallet_address` is overwritten, sessions are invalidated, a new JWT is issued. This is the only path that deletes a `web_users` row.

### 4.6 CORS

`src/api/middleware/cors.py::get_cors_origin` today whitelists `/actions/`, `/blinks/`, `/api/v1/blinks/`, `/.well-known/` as `*`. `/api/v1/agent` and `/api/v1/auth` fall through to `settings.get_cors_origins()`. This works for the web frontend as long as its origin is in `CORS_ORIGINS`, but the Chrome extension runs on `chrome-extension://<id>` and Firefox `moz-extension://<id>`. Add a `_is_extension_origin(origin)` helper that matches those schemes and allows them when `FEATURE_CHROME_EXT` is enabled. Extension IDs are pinned in `.env` (`ALLOWED_EXTENSION_IDS`).

---

## 5. Data model

### 5.1 New tables (Alembic migration)

```sql
CREATE TABLE chats (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       BIGINT       NOT NULL REFERENCES web_users(id) ON DELETE CASCADE,
    title         VARCHAR(200) NOT NULL DEFAULT 'New Chat',
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX ix_chats_user_updated ON chats (user_id, updated_at DESC);

CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER chats_set_updated_at
    BEFORE UPDATE ON chats
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE chat_messages (
    id             BIGSERIAL    PRIMARY KEY,
    chat_id        UUID         NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role           VARCHAR(20)  NOT NULL,           -- 'user' | 'assistant' | 'tool'
    content        TEXT         NOT NULL,
    cards          JSONB,                            -- array of AgentCard (each with card_id)
    tool_trace     JSONB,                            -- thought/action/observation frames
    status         VARCHAR(16)  NOT NULL DEFAULT 'complete', -- 'complete' | 'cancelled' | 'error'
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX ix_chat_messages_chat_id ON chat_messages (chat_id, created_at);
```

Prerequisite extension: `CREATE EXTENSION IF NOT EXISTS pgcrypto;` (gen_random_uuid).

### 5.2 Persistence rules

- One row per message; assistant messages store the final content + cards + full tool trace.
- Cards carry their own `card_id` (uuid); persisted inside the `cards` JSONB so a refreshed UI can rehydrate references without regenerating IDs.
- Short-term context (LLM window memory) rehydrates the last k=10 messages on session resume.
- Long-term context (Greenfield, W11) stores a distilled summary of everything beyond k=10, keyed on `{user_id}/{chat_id}.json`. When feature-flagged on, the agent prompt template is `[greenfield_summary?] + [k=10 window]`; the summary is regenerated every 10 turns via a background task.
- `DELETE /api/v1/agent/sessions/{id}` cascades to messages and (if enabled) the Greenfield object.

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

- W7 ships a Pydantic→TS generator (`scripts/gen_agent_types.py` using `datamodel-code-generator` or equivalent). Ilyon does not have one today; W7 adds it.
- CI step: regenerate, `git diff --exit-code web/types/agent.ts` — fails if drift.
- Fixture corpus of every `AgentCard` variant in `tests/fixtures/cards/`; both backend serializer and frontend renderer must accept the same fixtures.

---

## 9. Chrome extension (W10 UI + W13 background/content)

- Ported from the assistant's extension tree (`IlyonAi-Wallet-assistant-main/client/src/{background,content,popup,sidepanel}` and manifest).
- `popup.html` and `sidepanel.html` both mount the same React shell as `web/app/agent/chat` via the shared component library under `web/components/agent/*`.
- Backend URL is a build-time env (`NEXT_PUBLIC_ILYON_API_BASE` for web; `ILYON_API_BASE` baked into the extension bundle).
- Auth: extension stores JWT in `chrome.storage.local`; refresh flow identical to web; CORS allows the pinned extension origin per §4.6.
- **W13 scope:** service-worker / background script (session keep-alive, cross-tab auth sync), content script launcher (floating button on host allowlist), options page for allowlist + feature toggles.
- **W12 scope:** MetaMask + Phantom connectors ported from `client/src/wallets/*`, extracted into `web/lib/wallets/*` so both the web app and the extension consume the same adapters.

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
MORALIS_API_KEY=                  # ROTATED — see §11.1 Pre-Day-0
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
# Extension
ALLOWED_EXTENSION_IDS=abc123...   # comma-separated
# Feature flags
FEATURE_GREENFIELD_MEMORY=false
FEATURE_AFFILIATE_HOOK=false
FEATURE_CHROME_EXT=false
FEATURE_AGENT_V2=false
FEATURE_TOKENS_BAR=false
```

Every hardcoded key in the assistant tree is deleted before first run. A pre-merge audit script (`scripts/audit_secrets.py`) greps for known key prefixes and fails CI if any slip through.

### 11.1 Pre-Day-0 immediate action

The hardcoded Moralis JWT at `IlyonAi-Wallet-assistant-main/server/app/agents/crypto_agent.py:38` was committed to this repository. It is **compromised as of now**, not "as of merge time." Sequence:

1. Rotate the Moralis key in the Moralis dashboard **today** — before any Day-0 stub PR.
2. Replace the file's hardcoded literal with `os.environ["MORALIS_API_KEY"]` in the same commit that rotates (even though the file will be deleted by §12 step 5 eventually, it should not sit in HEAD with a live-looking JWT pattern).
3. Add the literal's SHA-256 to `scripts/audit_secrets.py`'s blocklist so any resurrection fails CI.

This is the only pre-Day-0 blocker in the plan.

---

## 12. Rollout

0. **Pre-Day-0 (§11.1):** Moralis key rotated; hardcoded literal replaced with env read.
1. **Day 0:** single PR lands:
   - Contracts §1.3 as typed stubs (Pydantic + TS).
   - Alembic migration for `web_users` extension + `chats` + `chat_messages` + pgcrypto.
   - `AffiliateHook.sol` **copied** from `IlyonAi-Wallet-assistant-main/contracts/` to the monorepo's new `contracts/` directory (so deletion in step 5 can't remove it).
   - Empty route handlers for `/api/v1/agent*`, `/api/v1/auth/{verify-evm,register,login,link-wallet}`, `/api/v1/tokens/ticker` behind feature flags (all default off).
2. **Parallel phase:** W1–W13 open in parallel. Each workstream ships behind a feature flag (`FEATURE_AGENT_V2`, `FEATURE_TOKENS_BAR`, `FEATURE_AFFILIATE_HOOK`, `FEATURE_GREENFIELD_MEMORY`, `FEATURE_CHROME_EXT`).
3. **Integration phase:** flags flipped on staging; Playwright surface tests (§8.3) gate promotion.
4. **Cutover:** `/agent/chat` and `/agent/swap` mockups replaced with live components; old mock components deleted from `web/app/agent/**`.
5. **Post-cutover (≥ 2 weeks after cutover + green Playwright runs on prod):** `IlyonAi-Wallet-assistant-main/` tree deleted from repo. Kept as reference in the interim.

---

## 13. Out of scope (explicit)

- No support for the assistant's FastAPI, SQLite, or uvicorn runtime at any point — Ilyon's aiohttp + async PG is the only runtime.
- No dual-write between old and new user tables — one table, one migration.
- No preservation of the assistant's hardcoded Moralis JWT — it is burned and rotated before first run.
- No new branding — emerald everywhere (assistant already uses emerald).
- No partial rollout of "features but not scoring" — every tool response flows through the Sentinel decorator from day 1.
