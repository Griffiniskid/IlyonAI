# IlyonAI × Wallet Assistant — Shell Merge Redesign

**Status**: Draft
**Date**: 2026-04-25
**Supersedes**: `2026-04-24-ilyonai-assistant-merge-design.md`
**Starting commit**: `671a7e5`

## Why this redesign

The 2026-04-24 design mounted the assistant's `MainApp.tsx` wholesale into Next.js client pages via `<MainAppClient />`. That worked at the API/proxy level (chat, swap, auth, persistence all flow end-to-end), but the UX is broken:

- MainApp wraps its tabs in its own `<div class="app"><aside class="sidebar">…</aside><main>…</main></div>`. Mounting that inside IlyonAI's `AppShell` produces **two sidebars stacked side-by-side**.
- MainApp's `<style>` block defines `.app`, `.sidebar`, `.main`, `.intro-screen` at full-bleed and conflicts with Tailwind, forcing the user to zoom out to ~50% to see content.
- `MainAppClient` uses `key={usePathname()}` to drive tab state via URL, which **remounts the entire MainApp on every navigation**, wiping React state and re-running the auth-hydrate. localStorage holds the token, but in-memory chat/wallet/intro state is lost — the intro overlay re-shows and the user perceives "re-login on every click."
- The market ticker top bar is internal to MainApp, so it only appears under `/agent/*`. The user wants it global.

## Goal

True shell-level merge:
- **One sidebar**: IlyonAI's, with assistant features integrated *into* it (wallet card, market list).
- **Global market ticker** at the top of the layout, visible on every route.
- **Global auth + chats state** that survive navigation — no flicker, no re-login, no re-render of intro.
- **Each assistant tab is a Next.js page body**, not a wholesale MainApp mount.
- **CSS scoped** under `.aa-` so assistant styles never compete with Tailwind/Radix.

API wiring from the prior merge (Next.js path-routed proxy, FastAPI on `:8000`, IlyonAI aiohttp on `:8080`, JWT, `/agent`, `/chats`, `/auth/*`) is preserved unchanged. Only the frontend mount strategy changes.

## Architecture

### Three layers in `web/app/layout.tsx`
```tsx
<AssistantProviders>
  <MarketTickerBar />            {/* sticky 32px strip, sees CoinGecko */}
  <AppShell>{children}</AppShell> {/* IlyonAI sidebar + content */}
  <AuthModal />                  {/* global Portal, opened via context */}
  <GlobalChatListDrawer />       {/* global slide-in chat history */}
</AssistantProviders>
```

`AssistantProviders` wraps existing `Providers` (React Query, wallet-adapter, MultiWallet, Toast) with two new contexts:
- `AuthProvider` — owns `{ token, user, walletType }`, hydrates from localStorage + `/api/v1/auth/me`, exposes `useAuth()` with `requireSignIn()`.
- `ChatsProvider` — owns `{ chats[], currentChatId, messages[], draft }`, exposes `selectChat`, `createChat`, `deleteChat`, `appendMessage`.

### IlyonAI sidebar (`web/components/layout/sidebar.tsx`) gains
- `<SidebarWalletCard />` — between nav groups and footer
- `<SidebarMarketList />` — collapsible "Market" section, rows dispatch `?prompt=…` to `/agent/chat`
- `<SidebarStatusBadges />` — Greenfield-Memory pill, version badge, backend-online dot

### Page bodies (each tiny, just imports a panel)
- `web/app/agent/chat/page.tsx` → `<ChatPanel />`
- `web/app/agent/swap/page.tsx` → `<SwapPanel />`
- `web/app/agent/portfolio/page.tsx` → `<PortfolioPanel />`
- `web/app/agent/dashboard/page.tsx` → `<DashboardPanel />`
- `web/app/portfolio/page.tsx` → `<PortfolioPanel />` (overrides IlyonAI's existing one)
- `web/app/page.tsx` (homepage) → `<IntroLanding />` for unauthed; redirect to `/agent/dashboard` for authed (server-side cookie check)

### Files extracted from `web/lib/agent-app/MainApp.tsx`

| New file under `web/components/agent-app/` | Source line range | Purpose |
|---|---|---|
| `providers/AuthProvider.tsx` | 3689–3710, 3905–3920 | auth state |
| `providers/ChatsProvider.tsx` | 3697–3700, 3923–4060 | chat list + CRUD |
| `MarketTickerBar.tsx` | 3771–3805 | global top strip |
| `SidebarWalletCard.tsx` | 4438–4470, 3300–3360 | sidebar wallet |
| `SidebarMarketList.tsx` | 4475–4485 | sidebar market list |
| `SidebarStatusBadges.tsx` | sidebar-footer subtree | status pills |
| `AuthModal.tsx` | 3302–3433 (AuthScreen) | global Portal |
| `ChatListPanel.tsx` | 3436–3670 | chat history drawer |
| `ChatPanel.tsx` | 4604–4750 | chat tab body |
| `SwapPanel.tsx` | swap activeTab body | swap tab body |
| `PortfolioPanel.tsx` | portfolio activeTab body | portfolio tab body |
| `DashboardPanel.tsx` | 4499–4603 | dashboard tab body |
| `IntroLanding.tsx` | 4202–4320 | landing JSX |
| `Composer.tsx` | composer subtree | input bar |
| `MessageList.tsx` + `AssistantBubble.tsx` + `UserBubble.tsx` | their sections | message rendering |
| `QuickChips.tsx` | quick chips | suggestions |
| `ReasoningAccordion.tsx` | 2650–2710 | ReAct chain UI |
| `SimulationPreview.tsx` | 2713–3030 | swap/bridge/stake/lp preview + sign |
| `BalanceCard.tsx` | 3034–3180 | balance card |
| `LiquidityPoolCard.tsx` | 3182–3295 | LP card |
| `UniversalCardList.tsx` | 481–650 | generic cards |
| `intent-router.ts` | 132–187 | client-side intent classifier |
| `useAgentRun.ts` | 4080–4170 | POST `/agent` hook |
| `lib/auth-storage.ts` | localStorage helpers | typed key access |

### CSS plan
The MainApp `<style>` block (lines ~720–2620) → `web/styles/agent-app.css`:
- Every selector renamed `.x` → `.aa-x` (mechanical sed: `.sidebar` → `.aa-sidebar`, `.app` → `.aa-app`, `.intro-hero` → `.aa-intro-hero`, etc.)
- `body`, `html`, `*` global rules **deleted** (don't fight IlyonAI's globals.css)
- Layout rules for `.aa-app` (the wholesale shell flex), `.aa-sidebar` (the assistant's sidebar that stacks against IlyonAI's) — **deleted**
- Intro-screen full-bleed positioning kept, scoped under `.aa-intro-screen`
- Imported once in `web/app/layout.tsx` via `import "@/styles/agent-app.css"`

### Wholesale mount removal
Delete:
- `web/components/agent-app/MainAppClient.tsx`
- `web/lib/agent-app/MainApp.tsx` import path from any page

Keep on disk as canonical reference (not imported):
- `web/lib/agent-app/MainApp.tsx`
- `IlyonAi-Wallet-assistant-main/client/src/MainApp.tsx`

## Implementation order

1. Extract CSS to `web/styles/agent-app.css` with `.aa-` rename and dead-rule deletion. Import in root layout.
2. Build providers: `AuthProvider`, `ChatsProvider`. Wrap in `AssistantProviders`. Mount in root layout.
3. Build small global widgets: `MarketTickerBar`, `AuthModal` (Portal). Mount in root layout.
4. Build extracted leaf components: `Composer`, `MessageList`, `AssistantBubble`, `UserBubble`, `QuickChips`, `ReasoningAccordion`, `SimulationPreview`, `BalanceCard`, `LiquidityPoolCard`, `UniversalCardList`, `ChatListPanel`. Each imports JSX/handlers from MainApp.tsx with no logic changes.
5. Build the four panels: `ChatPanel`, `SwapPanel`, `PortfolioPanel`, `DashboardPanel`. Each composes the leaf components.
6. Build `IntroLanding`. Replace `web/app/page.tsx`. Add server-side auth-cookie redirect.
7. Replace each `/agent/*` page body with a tiny panel import. Delete `web/components/agent-app/MainAppClient.tsx`.
8. Add `SidebarWalletCard`, `SidebarMarketList`, `SidebarStatusBadges` to `web/components/layout/sidebar.tsx`.
9. Smoke pass via curl: backends + auth + agent + chats persistence still work.
10. Smoke pass via headless browser HTML inspection: every UI route returns 200 and contains the expected anchor strings (no double sidebars, ticker bar present on every page, no intro overlay on `/agent/*`).

## Acceptance criteria

- Open `http://localhost:3030/agent/chat` at 100% browser zoom → exactly one sidebar (IlyonAI's), market ticker visible at top, content fills the right pane without horizontal scroll.
- Sign in once via the auth modal. Navigate `/agent/chat` → `/agent/swap` → `/agent/portfolio` → `/`. No re-auth prompt. No intro overlay on `/agent/*`. Auth state survives.
- Sidebar shows: nav groups, wallet card (Phantom 5Mg7…839L + Disconnect), Market list (SOL/ETH/BNB/USDT live prices), status badges, sign-out — all in IlyonAI's existing sidebar style.
- Market ticker bar visible on `/`, `/shield`, `/token`, `/agent/chat`, `/portfolio`, etc.
- Chat: send message → reasoning streams into accordion → assistant message appears → message persists, visible in chat history drawer.
- Swap: composer accepts pair + amount → "Continue in chat" hands off → SimulationPreview renders → wallet sign flow available.
- Portfolio: shows multi-chain balance breakdown for connected wallet.
- Sentinel pages (`/shield`, `/token`, `/whales`, `/trending`, `/smart-money`, `/rekt`, `/audits`, `/alerts`) untouched and still load.

## Out of scope

- Greenfield SDK live integration (the storage badge stays decorative until backend wires it).
- Mobile responsiveness beyond what IlyonAI already supports.
- Replacing the existing IlyonAI Tailwind theme — only adding `.aa-` styles.
