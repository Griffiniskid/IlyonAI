# AI Agent Integration Plan

This document describes the "AI Agent" (codename: **Agent Platform**) — a multi-chain DeFi assistant being developed on a separate device that will be merged into Ilyon AI.

Source documents this plan consolidates:

- `project-full-system-description.md`
- `project-ui-ux-deep-dive.md`
- `PROJECT_SYSTEM_OVERVIEW.md`
- `FEATURE_CATALOG.md`
- `UI_PAGE_GUIDE.md`
- `BACKEND_AND_API_REFERENCE.md`

## 1. What the Agent Platform Is

A consumer-grade DeFi assistant whose primary surface is a chat that can both *answer questions* and *build signed transaction proposals*. The user always signs on the client; the backend never touches keys.

Three architectural layers:

1. **React/Vite frontend** (`client/`) — tabbed SPA with MetaMask + Phantom wallet integrations.
2. **FastAPI backend** (`server/`) — deterministic intent handlers plus a LangChain crypto agent.
3. **Foundry contracts** (`contracts/`) — affiliate-fee hooks for PancakeSwap Infinity.

Wallet execution contexts:

- MetaMask EVM
- Phantom Solana
- Phantom EVM (Phantom is treated as dual-context, not Solana-only)

## 2. The Real Page Set — Only Four Tabs

This is the critical correction vs. earlier plans. The Agent Platform has exactly **four top-level tabs** and nothing else:

| Agent Platform tab | Purpose |
|---|---|
| **Home** | Product-orientation dashboard: stat cards, market overview, quick-action shortcuts, feature grid. Not an analytics dashboard — a guided launch surface. |
| **AI Chat** | Central conversational execution surface. The majority of product power lives here. |
| **Portfolio** | Multi-chain wallet overview: summary cards, USD/native toggle, refresh, token table. |
| **Swap** | Guided pre-composer that hands final execution off to AI Chat. |

**There are no dedicated pages for bridge, stake, transfer, LP deposit, or automations.** Those capabilities exist *inside the AI Chat* as structured card types rendered in the message stream:

- `BalanceCard`
- `LiquidityPoolCard`
- `UniversalCardList`
- `SimulationPreview` (shared across swap / transfer / stake / LP / bridge)

Each card shares a common pattern: confirmation header, pay/receive blocks, route/impact/fee metadata, warnings, one wallet-action button, success or error state. Bridge is the richest variant (source vs destination chains, actual source spend, fill time, order id, source-execution warnings).

## 3. Ilyon Page Mapping

Given the four-tab set above, only **two new routes** land in Ilyon. The other two tabs already have counterparts:

| Agent Platform tab | Ilyon route | Status |
|---|---|---|
| Home | `/dashboard` (existing) + `/` (existing overview) | Merge content, no new route. |
| **AI Chat** | **`/agent/chat`** | New route. Layout mockup live today as a preview plug. |
| Portfolio | `/portfolio` (existing) | Enhance in place with multi-address Phantom EVM + Solana merging. No new route. |
| **Swap** | **`/agent/swap`** | New route. Layout mockup live today as a preview plug. |

The current Ilyon plugs (`web/app/agent/chat/page.tsx` and `web/app/agent/swap/page.tsx`) are static, non-interactive layout mockups that mirror the target UI: chat header, user/assistant bubbles, reasoning accordions, structured `WALLET BALANCES` card, quick-prompt chips, composer; and for Swap — pay/receive token fields, direction toggle, estimate strip, quick pairs, `Continue in Agent Chat` handoff button. Both pages carry a `Preview · Coming Soon` banner.

Bridge / stake / transfer / LP deposit / automations will appear inside the AI Chat page as card renderers — **not** as navigable routes.

## 4. Visual Language Notes

From the UX deep-dive:

- Dark navy / charcoal base; glass-like translucent panels.
- The Agent Platform uses **gold** as the primary brand/action accent. Ilyon uses **emerald**. The preview plugs use Ilyon's emerald to stay visually coherent; re-skinning to gold (if desired) is a cosmetic pass later.
- **Purple/blue** is reserved for AI / system-intelligence framing — reasoning accordions, structured card headers. The Chat mockup uses purple for those elements to match the Agent Platform convention.
- Green/red are semantic (positive/negative market, success/error). Preserved.
- Motion: `fadeUp` for content, `slideIn` for overlays, `scaleIn` for cards, ticker marquee, status pulses, typing-dot bounce, reasoning-accordion transitions. These are implemented during Phase 2.

Global chrome from the Agent Platform (ticker bar, persistent wallet card, market mini-list sidebar) is deferred — Ilyon's existing AppShell covers these concerns; visual parity can be tuned post-merge.

## 5. Backend API Surface (to port)

| Endpoint | Role |
|---|---|
| `POST /api/v1/agent` | Main chat/action orchestration |
| `POST /api/v1/rpc-proxy` | JSON-RPC relay |
| `GET /api/v1/bridge-status/{order_id}` | deBridge order polling (used by SimulationPreview card) |
| `POST /api/v1/auth/{metamask,phantom}` | Wallet-signature login |
| `GET /api/v1/auth/me` | Profile |
| `GET/POST/PATCH/DELETE /api/v1/chats[/id]` | Chat persistence |
| `GET /api/portfolio/{wallet_address}` | Multi-address, multi-chain portfolio scan |

LLM agent tools (LangChain): `get_wallet_balance`, `simulate_swap`, `get_token_price`, `build_swap_tx`, `get_defi_market_overview`, `get_defi_analytics`, `get_staking_options`, `search_dexscreener_pairs`, `find_liquidity_pool`, `build_solana_swap`, `build_stake_tx`, `build_deposit_lp_tx`, `build_bridge_tx`, `build_transfer_tx`.

Deterministic fast paths (anti-hallucination): direct swap, direct bridge, direct yield search, direct staking info, direct stake, direct LP deposit, direct pool lookup.

## 6. Third-Party Integrations

| Role | Provider |
|---|---|
| EVM swaps / staking / LP routing | Enso |
| Solana swaps | Jupiter |
| Cross-chain bridge | deBridge DLN |
| Yield pools | DefiLlama |
| Pair / token discovery | DexScreener |
| Token prices | Binance → CoinGecko fallback |
| Wallet inventory | Moralis + RPC + DexScreener enrichment |

## 7. Merge Roadmap

### Phase 0 — Plugs in place (done)
- `AI Agent` nav group with `Chat` and `Swap` entries.
- Layout mockup pages at `/agent/chat` and `/agent/swap`, gated by the preview banner. The structure previewed matches the Agent Platform screenshot: sample conversation with user/assistant bubbles, reasoning accordions, Wallet Balances structured card, quick-prompt chips, composer for Chat; token-pair composer with quick pairs and chat-handoff CTA for Swap.

### Phase 1 — Backend port
- Port `crypto_agent.py` tool surface into Ilyon's Python backend (FastAPI sidecar or port handlers to aiohttp — decision pending).
- Reuse Ilyon's existing response envelope + CORS middleware.
- Unify the auth challenge flow; MetaMask/Phantom verifiers become alternative verifiers, not parallel endpoints.
- Persist chats in Ilyon Postgres (not SQLite): add `chats` and `chat_messages` tables to `src/storage/database.py`.

### Phase 2 — AI Chat surface
- Replace the Chat mockup with a live client component.
- Implement: composer (auto-resizing textarea, Enter-to-send, Shift+Enter newline), message feed, user/assistant bubble polarity, reasoning accordion (collapsed by default, expandable, step count), quick-prompt chips row, empty-state capability grid for fresh chats.
- Implement structured card renderers: `BalanceCard`, `LiquidityPoolCard`, `UniversalCardList`, `SimulationPreview`.
- Wire `POST /api/v1/agent` with streaming reasoning where supported.
- Replace in-process LangChain memory with a per-session cache keyed on `session_id`.

### Phase 3 — Structured execution via `SimulationPreview`
- Single shared card handles swap / transfer / stake / LP / bridge.
- EVM: chain-switch request → optional approval tx → main tx.
- Solana: deserialize base64 versioned tx → Phantom sign-and-send.
- Bridge: source-execution warning copy, `GET /bridge-status/{order_id}` polling, source-vs-destination chain labels.

### Phase 4 — AI Swap surface
- Replace the Swap mockup with a live composer.
- Amount input, from/to token pickers, direction toggle, live client-side estimate, quick-pair presets.
- On continue, format a structured prompt and hand to `/agent/chat` — chat owns real routing, simulation, wallet signing.

### Phase 5 — Portfolio enhancement
- Extend existing `/portfolio` with multi-address scan so Phantom Solana + Phantom EVM merge into one view.
- Keep current shape (summary cards, token table, USD/native toggle, refresh).

### Phase 6 — Extension surfaces (optional)
- Browser popup and sidepanel can be layered on top of the Ilyon UI once structured cards stabilize.

## 8. Explicit Boundaries (unchanged)

The Agent Platform does **not** support, and Ilyon will **not** claim to support on day one:

- unstaking
- removing liquidity
- claiming rewards
- arbitrary contract interaction
- contract deployment

Narrow-by-design behaviors:

- Staking limited to ETH / BNB / MATIC and supported protocol families (Lido, Rocket Pool, Coinbase, Frax, Binance, Ankr).
- LP deposits require a resolvable EVM pool address.
- Bridge outcomes depend on deBridge solver / compliance screening.
- Transfer builder is EVM-first (native + ERC-20); Solana-native transfers are not full parity.

## 9. Open Questions

1. **Backend framework**: Ilyon uses aiohttp, Agent Platform uses FastAPI. Port handlers to aiohttp or run FastAPI as a sidecar.
2. **Auth unification**: replace Ilyon's challenge verifier or augment it.
3. **Brand color**: Agent Platform uses gold; Ilyon uses emerald. Preview plugs use emerald today. Decide whether to re-skin post-merge.
4. **Chat persistence**: SQLite → Postgres migration path for existing Agent Platform users (if any).
5. **Ticker bar**: whether to adopt the Agent Platform's scrolling market ticker globally in Ilyon's AppShell.

## 10. Related Ilyon Files

- `web/components/layout/nav-config.ts` — `AI Agent` group (Chat + Swap only).
- `web/app/agent/chat/page.tsx` — Chat layout mockup.
- `web/app/agent/swap/page.tsx` — Swap layout mockup.
- `web/components/coming-soon.tsx` — shared "feature disabled" plug (not used by the two mockups above; reserved for other coming-soon features).
- `web/lib/feature-flags.ts` — `COMING_SOON` switch.
