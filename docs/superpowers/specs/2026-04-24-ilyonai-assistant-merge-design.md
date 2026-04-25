# IlyonAI × Wallet Assistant Merge — Design

**Status**: Draft
**Date**: 2026-04-24
**Starting commit**: `4bda868` (staging, post-rewind)
**Safety branch**: `safety/pre-rewind-2026-04-24` (preserves the prior absorb attempt)

## Goal

One web shell — IlyonAI's Next.js `web/` — that contains **every feature and element** from the AI Wallet Assistant alongside IlyonAI's existing sentinel features. No assistant features lost, no IlyonAI sentinel features lost. Minimum rewriting: existing assistant code is copied verbatim and re-imported into Next.js pages, not re-implemented.

When a feature exists in both projects, the assistant version wins (per user directive). Where IlyonAI has features the assistant lacks (Shield, Token analyzer, Whales, Rekt, Audits, Smart Money, Alerts, DeFi v2), they are preserved untouched.

## Non-goals

- Combining the two backends into one process. They run side-by-side.
- The previous "pool analysis with diagrams in chat" demo workflow. Out of scope.
- Mounting the assistant as a standalone single page; it is decomposed into Next.js routes.

## Source-of-truth locations

- **Assistant source**: `/home/griffiniskid/Downloads/IlyonAi-Wallet-assistant-main/` — full `client/` (Vite + React), `server/` (FastAPI), tests.
- **In-repo assistant folder**: `IlyonAi-Wallet-assistant-main/` (currently has only `server/app/agents/crypto_agent.py` at `4bda868`). Will become a full mirror of the Downloads tree.
- **IlyonAI Next.js shell**: `web/` (App Router, Radix UI, Tailwind, Zustand, React Query, Solana wallet-adapter, MultiWalletProvider).
- **IlyonAI Python backend**: `src/` (aiohttp, async SQLAlchemy, port `18090`).

## Architecture

### Three processes
- IlyonAI aiohttp `src/main.py` → port `18090` (sentinel routes).
- Assistant FastAPI `IlyonAi-Wallet-assistant-main/server/main.py` → port `8000` (agent, chats, auth, portfolio).
- Next.js dev/server → port `3000` (proxies to both).

### Path-routed proxy in `web/next.config.js`
Replaces the current single `/api/:path*` rewrite with longest-prefix-first list:

| Rewrite source | Destination |
|---|---|
| `/api/v1/agent` | `${ASSISTANT_API_TARGET}/api/v1/agent` |
| `/api/v1/chats/:path*` | `${ASSISTANT_API_TARGET}/api/v1/chats/:path*` |
| `/api/v1/auth/:path*` | `${ASSISTANT_API_TARGET}/api/v1/auth/:path*` |
| `/api/v1/rpc-proxy` | `${ASSISTANT_API_TARGET}/api/v1/rpc-proxy` |
| `/api/v1/bridge-status/:path*` | `${ASSISTANT_API_TARGET}/api/v1/bridge-status/:path*` |
| `/api/portfolio/:path*` | `${ASSISTANT_API_TARGET}/api/portfolio/:path*` |
| `/api/:path*` | `${API_REWRITE_TARGET}/api/:path*` (catch-all → IlyonAI aiohttp) |

Env defaults: `ASSISTANT_API_TARGET=http://localhost:8000`, `API_REWRITE_TARGET=http://localhost:18090`.

The hardcoded `localhost:8000` URLs inside `MainApp.tsx` (lines 250, 3295, 3652, 3896, 4104) become relative `/api/v1/...` and `/api/portfolio/...` paths so all assistant fetches go through Next.js. This is the only source-level change to assistant client code.

### Nav-config map (`web/components/layout/nav-config.ts`)

| Group | Item | Origin |
|---|---|---|
| Discover | Overview, Dashboard, Trending | IlyonAI (unchanged) |
| Smart Money | Hub, Whales, Entity | IlyonAI (unchanged) |
| Protect | Shield | IlyonAI (unchanged) |
| Portfolio | Portfolio | **content replaced** by assistant's portfolio tab UI |
| AI Agent | Dashboard (NEW), Chat, Swap | content sourced from assistant tabs |
| Settings | Settings | content replaced by assistant's settings region; IlyonAI alert/sentinel preferences appended |

Homepage (`/`): assistant's intro-landing (hero, stats, features, how-it-works, partners) added on top; existing IlyonAI sentinel widgets (TokensTicker, etc.) compose below.

## Frontend file checklist

### Assistant client → in-repo mirror
Copy `/Downloads/.../client/` → `IlyonAi-Wallet-assistant-main/client/` (entire tree, verbatim). Files:
- `MainApp.tsx` (5,157 lines) — canonical reference and source for extracted components
- `MainApp.bridge.test.tsx`, `main.tsx`, `vite-env.d.ts`
- `wallets/metamask.ts`, `wallets/phantom.ts`
- `services/GreenfieldService.ts`, `services/spUtils.ts`
- `utils/copyWithFeedback.ts` + test
- `popup/`, `sidepanel/`, `background/` (preserved for reference; not used by Next.js)
- `vite.config.ts`, `tsconfig.json`, `package.json`, `index.html`

### New Next.js pages (each pulls a tab/section from MainApp.tsx)

| Path | Source region in MainApp | Content |
|---|---|---|
| `web/app/page.tsx` (homepage REPLACE) | `showIntro` overlay (4201–4320) | hero, intro-stats-row, intro-feat-grid, how-it-works, partners; sentinel widgets (TokensTicker) appended below |
| `web/app/agent/dashboard/page.tsx` (NEW) | `activeTab === "dashboard"` (4499–4603) | dashboard cards + CoinGecko market overview strip (3771–3800) |
| `web/app/agent/chat/page.tsx` (REPLACE stub) | `activeTab === "chat"` (4604–4750) | composer, message list, reasoning accordion, simulation preview, chat-list panel |
| `web/app/agent/swap/page.tsx` (REPLACE mock) | `activeTab === "swap"` | real swap composer, route preview, sign flow |
| `web/app/portfolio/page.tsx` (REPLACE) | `activeTab === "portfolio"` | wallet balances, BalanceCard, multi-chain breakdown |
| `web/app/settings/page.tsx` (REPLACE) | settings region | wallet management, auth status, sign-out; IlyonAI sentinel prefs appended |

### Extracted shared modules (`web/components/agent-app/`)
Mechanical extraction of inline components from MainApp.tsx — no logic changes:
- `UniversalCardList.tsx` (line 481)
- `ReasoningAccordion.tsx` (line 2650)
- `SimulationPreview.tsx` (line 2713) — handles bridge order polling
- `BalanceCard.tsx` (line 3034)
- `LiquidityPoolCard.tsx` (line 3182)
- `AuthScreen.tsx` (line 3302)
- `ChatListPanel.tsx` (line 3436)
- `Composer.tsx` (assistant's composer)
- `MarketOverview.tsx` (NEW — extracted CoinGecko polling block)
- `IntroLanding.tsx` (NEW — extracted intro overlay)
- `intent-router.ts` (lines 132–187 — query → intent classifier)

### Global styles
The `<style>` block from MainApp.tsx → `web/styles/agent-app.css`, imported by `web/app/layout.tsx`. To prevent collisions with Tailwind/Radix, every selector is scoped under `.agent-app`. Each new page wraps content in `<div className="agent-app">`. Mechanical sed-style change.

### Providers (`web/components/providers.tsx`)
Existing scaffolding stays. Two providers added:
- `AuthProvider` (NEW, `web/components/providers/AuthProvider.tsx`) — owns JWT + user, persists `ap_token`, `ap_user`, `ap_wallet_type` in localStorage; exposes `useAuth()`. Replaces the auth state currently inline in MainApp (3689–3700).
- `ChatProvider` (NEW, `web/components/providers/ChatProvider.tsx`) — owns chat list + active chat id; replaces 3697–3700.
- `MultiWalletProvider` (existing) — extended to use assistant `wallets/metamask.ts` + `wallets/phantom.ts` as canonical signers.

### Wallet adapters
`metamask.ts` and `phantom.ts` copied to `web/lib/wallets/` and consumed by `MultiWalletProvider`. The existing Solana wallet-adapter (`@solana/wallet-adapter-react`) stays mounted because IlyonAI components depend on it; the assistant's `phantom.ts` is the signer-of-record.

### Deleted (replaced by assistant equivalents)
- `web/components/agent/DemoChatFrame.tsx`
- `web/components/agent/ChatShell.tsx`
- `web/components/agent/MessageList.tsx`
- `web/components/agent/AssistantBubble.tsx`
- `web/components/agent/UserBubble.tsx`
- `web/components/agent/QuickChips.tsx`
- `web/components/agent/ReasoningAccordion.tsx`
- `web/components/agent/Sidebar.tsx`
- `web/components/agent/SidePanel.tsx`
- `web/components/agent/Composer.tsx`
- `web/components/agent/cards/`
- existing hardcoded swap mock in `web/app/agent/swap/page.tsx`

## Backend file checklist

Copy `/Downloads/.../server/` → `IlyonAi-Wallet-assistant-main/server/` (entire tree, verbatim). Final layout:

| File | Purpose |
|---|---|
| `server/main.py` | uvicorn entrypoint shim |
| `server/app/main.py` | FastAPI factory + CORS + router mounting |
| `server/app/api/endpoints.py` | `/agent`, `/rpc-proxy`, `/bridge-status/{order_id}` + direct intent handlers |
| `server/app/api/auth.py` | `/auth/{register,login,metamask,phantom,me}` |
| `server/app/api/chats.py` | `/chats` CRUD |
| `server/app/api/portfolio.py` | `/portfolio/{wallet_address}` (mounted under `/api`) |
| `server/app/agents/crypto_agent.py` | LangChain ReAct agent + swap/bridge/stake/LP/balance tools |
| `server/app/core/config.py`, `core/security.py` | settings, JWT |
| `server/app/db/database.py`, `db/models.py` | SQLAlchemy engine + User/Chat/ChatMessage |
| `server/app/schemas/{auth,request}.py` | Pydantic schemas |
| `server/requirements.txt`, `server/.env.example`, `server/tests/` | deps, env template, tests |

Adapter (small addition, only "rewrite"): `auth.py` performs a best-effort upsert into IlyonAI's `web_users` table (in `ai_sentinel.db`) on every successful sign-in keyed by wallet address. Lets shared sentinel features (alerts, tracked wallets) tie to the assistant-issued JWT.

## Data flow

### Auth
1. `AuthScreen` collects email/password OR triggers MetaMask/Phantom signature.
2. POST → `/api/v1/auth/{register|login|metamask|phantom}` (proxy → FastAPI :8000).
3. FastAPI returns `{ token, user, wallet_type }`. `AuthProvider` persists in localStorage.
4. FastAPI also performs the `web_users` upsert (adapter above).
5. All authed fetches add `Authorization: Bearer ${token}` via `apiFetch()` helper in `web/lib/api/assistant.ts`.

### Agent run
1. Composer in `/agent/chat` collects `{ message, chat_id, client_session_id, wallet_address, wallet_type }`.
2. POST `/api/v1/agent` (proxy → FastAPI). FastAPI tries `_try_direct_swap`, `_try_direct_balance`, `_try_direct_bridge`, `_try_direct_lp_deposit`, `_try_direct_stake`, `_try_direct_yield_search`, `_try_direct_pool_lookup` first; falls back to LangChain agent.
3. Response: `{ messages[], reasoning_steps[], simulation_preview?, card_data? }` where `simulation_preview.actionType ∈ {swap, bridge, stake, lp_deposit}`.
4. `SimulationPreview` renders the card. User clicks "Sign" → wallet adapter signs and broadcasts. Bridge orders poll `/api/v1/bridge-status/{order_id}`.

### Market overview / token bar
- Dashboard CoinGecko price strip polls `https://api.coingecko.com/api/v3/simple/price` directly from browser every 60s. No backend involvement.
- IlyonAI's `/api/v1/tokens/ticker` (sentinel-scored) keeps powering `web/components/tokens/TokensTicker.tsx`. Two distinct strips with different purposes; both stay.

### Chat history
- `useChats()` hook drives list (`GET /api/v1/chats`), open (`GET /api/v1/chats/{id}`), delete (`DELETE`), implicit create on first agent message.
- All authenticated.

### Portfolio
- `/portfolio` page calls `GET /api/portfolio/{wallet_address}` → assistant FastAPI.
- Assistant's `get_smart_wallet_balance()` returns multi-chain balances.
- IlyonAI aiohttp `/api/v1/portfolio/wallets` endpoints stay live for sentinel-side tracked-wallet management; not consumed by `/portfolio` page itself anymore.

## State boundaries (replacing MainApp.tsx monolith)
- Wallet → `MultiWalletProvider`
- Auth/JWT → `AuthProvider`
- Chat list + active chat → `ChatProvider`
- Reasoning steps + live agent stream → page-level state in `/agent/chat`
- Intro overlay → page-level state in `/`
- Tab state → eliminated; replaced by Next.js routing

## Run script (root `run.sh`)
```bash
#!/bin/bash
trap 'kill 0' EXIT
( cd src && python main.py ) &                                                              # :18090
( cd IlyonAi-Wallet-assistant-main/server && venv/bin/uvicorn app.main:app --port 8000 --reload ) &
( cd web && npm run dev ) &
wait
```

## Dependencies

### Backend (assistant venv at `IlyonAi-Wallet-assistant-main/server/venv/`)
fastapi 0.115.0, uvicorn[standard] 0.30.6, langchain 0.3.1, langchain-openai 0.2.1, langchain-groq 0.2.1, web3 7.3.0, sqlalchemy 2.0.36, python-jose[cryptography] 3.3.0, PyNaCl 1.5.0, base58 2.1.1, requests 2.32.3, httpx 0.27.2, bcrypt 5.0.0, python-multipart 0.0.12, email-validator 2.2.0.

IlyonAI's existing `requirements.txt` and `venv/` untouched.

### Frontend (`web/package.json`)
Add `@bnb-chain/greenfield-js-sdk` (for `GreenfieldService`). Other deps verified post-extraction; most likely already present (Solana wallet-adapter, Radix, Tailwind, Recharts, Framer Motion, React Query).

## Environment

| File | Vars |
|---|---|
| `IlyonAi-Wallet-assistant-main/server/.env` | `OPENAI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `JWT_SECRET`, `DUNE_API_KEY`, `ENSO_API_KEY`, RPC URLs (Ethereum, Solana, BNB, etc.) |
| `web/.env.local` | `ASSISTANT_API_TARGET=http://localhost:8000` (NEW), `API_REWRITE_TARGET=http://localhost:18090`, existing `NEXT_PUBLIC_*` |
| `.env` (top-level IlyonAI) | unchanged |

## Database
- `ai_sentinel.db` (IlyonAI, async SQLAlchemy) — unchanged.
- `agent_platform.db` (assistant, sync SQLAlchemy) — created on first FastAPI boot via `Base.metadata.create_all`.
- Two databases, no merging. Assistant's `users`, `chats`, `chat_messages` tables don't exist in IlyonAI; IlyonAI's sentinel tables don't exist in assistant. The auth-time upsert into `web_users` keeps wallet→user identity aligned across both stores.

## Cutover order (becomes the implementation plan task list)

1. Copy assistant `server/` tree → in-repo, create venv, install deps, boot on `:8000`, hit `/health`.
2. Update `web/next.config.js` rewrites; verify proxy round-trip to both backends.
3. Copy assistant `client/` tree → in-repo (canonical reference, also runnable standalone via Vite).
4. Extract shared components into `web/components/agent-app/` (no logic changes).
5. Move CSS to `web/styles/agent-app.css` with `.agent-app`-scoped selectors; import in root layout.
6. Wire `AuthProvider` + `ChatProvider` in `web/components/providers.tsx`. Replace hardcoded `localhost:8000` in MainApp imports with relative paths.
7. Port `wallets/metamask.ts` + `wallets/phantom.ts` into `web/lib/wallets/`; integrate into `MultiWalletProvider`.
8. Replace `/agent/chat` page; smoke-test agent run end-to-end.
9. Replace `/agent/swap` page; smoke-test swap composer + sign on testnet.
10. Replace `/portfolio` page; smoke-test multi-chain balance load.
11. Replace `/settings` page; append IlyonAI sentinel preferences as new sections.
12. Add `/agent/dashboard` page + market overview; nav-config update.
13. Replace `/` homepage with intro-landing; compose existing TokensTicker below.
14. Delete `web/components/agent/*` dead code.
15. Author root `run.sh`; document in README; final smoke pass.

## Testing

- Backend: `pytest` in `IlyonAi-Wallet-assistant-main/server/tests/` (existing assistant suite). IlyonAI's `tests/` stays.
- Frontend: `npm run type-check`, `npm run lint`, `npm run test` in `web/`. Port `MainApp.bridge.test.tsx` to Vitest under `web/__tests__/agent-app/` if not subsumed by assistant tests.
- Manual smoke per cutover step: each numbered step ends with a smoke check.
- Live RPC flows (swap/bridge/stake/LP) require pre-loaded testnet wallets.

## Edge cases / risks

- **CoinGecko rate limits** — public endpoint; many concurrent users → rate limit. Acceptable now; flagged for later move behind `/api/v1/tokens/ticker`.
- **Two databases** — wallet→user upsert must run on every login (not just register), or IlyonAI alert UI won't see new assistant-registered users.
- **CSS conflicts** — assistant uses generic class names (`.sidebar`, `.intro-hero`). Mitigation: scope all assistant CSS under `.agent-app` parent class; each page wraps content in `<div className="agent-app">`.
- **Solana wallet-adapter vs. assistant `phantom.ts`** — both coexist; assistant `phantom.ts` is signer-of-record for assistant flows; wallet-adapter remains for IlyonAI components already using its hooks.
- **Assistant's hardcoded `localhost:8000`** — must be replaced with relative paths in every fetch call inside MainApp.tsx (lines 250, 3295, 3652, 3896, 4104). Mechanical change.
- **CORS** — assistant FastAPI currently whitelists only `localhost:5173` and `localhost:3000`. With the proxy, requests originate same-origin from Next.js and CORS is irrelevant; CORS config stays as-is for the rare case of direct hits during dev.

## What stays (IlyonAI-only — explicitly preserved)
- `web/app/{token,trending,defi,shield,whales,rekt,audits,smart-money,alerts,contract,pool,entity,dashboard,docs}/` pages
- All `src/` aiohttp routes and services
- `web/components/tokens/TokensTicker.tsx`
- `web/components/{shield,defi,intel,smart-money,alerts}/` sentinel components
- All sentinel-specific Python in `src/{shield,defi,intel,smart_money,alerts,analytics,portfolio}/`

## What dies
- `web/components/agent/*` (replaced by `web/components/agent-app/*`)
- Hardcoded mock swap UI in `web/app/agent/swap/page.tsx`
- DemoChatFrame and its mock data

## Open questions resolved before draft
- **Mount style**: existing nav slots (`/agent/chat`, `/agent/swap`), with `/agent/dashboard` added.
- **Portfolio overlap**: assistant version wins for the page; sentinel-side endpoints kept live.
- **Settings overlap**: assistant version wins; sentinel preferences appended.
- **Homepage**: intro landing on top, sentinel widgets below.
