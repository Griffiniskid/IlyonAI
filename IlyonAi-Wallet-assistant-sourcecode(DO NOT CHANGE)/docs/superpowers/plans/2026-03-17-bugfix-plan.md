# Agent Platform Bug-Fix Plan

**Goal:** Fix all confirmed bugs discovered in the comprehensive audit, prioritised by impact.

**Architecture:** Fixes span the FastAPI backend (`server/`) and React frontend (`client/src/`). A full git backup was committed at `e30c8e8` before any changes.

**Tech Stack:** Python 3.9, FastAPI, SQLAlchemy, React 18, TypeScript, Vite, Bun

---

## Priority 1 — Critical / User-Visible

### Task 1: Phantom wallet session persistence (handleLogout clears wallets + showAuth fix)
- Modify: `client/src/MainApp.tsx`
- [ ] Fix `handleLogout` to also remove `ap_wallet`, `ap_sol_wallet`, `ap_wallet_type` from localStorage and clear wallet state
- [ ] Fix `showAuth` initial state: also check `ap_sol_wallet` so Phantom users don't see login modal on refresh
- [ ] Gate Chats UI and `handleSelectChat` on `authUser?.token` being non-empty

### Task 2: Live ticker prices
- Modify: `client/src/MainApp.tsx`
- [ ] Replace hardcoded `TICKER_ITEMS` with live state fetched from Binance `/ticker/24hr` for top coins
- [ ] Poll every 30s; show stale indicator if fetch fails
- [ ] Apply same live prices to the sidebar `TOKENS` cards

### Task 3: Backend health check re-polling
- Modify: `client/src/MainApp.tsx`
- [ ] Change the one-shot health check to `setInterval` every 30s with cleanup

### Task 4: Fix `CELO` Binance pair → `CELOUSDT`
- Modify: `server/app/agents/crypto_agent.py`
- [ ] Change `"CELO": "CELOUSD"` → `"CELO": "CELOUSDT"` in `_BINANCE_PAIRS`

### Task 5: Fix `handleLogout` incomplete wallet cleanup (already in Task 1)

### Task 6: Fix `executeSwap` using raw `window.ethereum`
- Modify: `client/src/MainApp.tsx`
- [ ] Replace `window.ethereum` with `resolveMetaMaskProvider()` from `metamask.ts`

### Task 7: Fix `executeSolanaSwap` using deprecated `window.solana`
- Modify: `client/src/MainApp.tsx`
- [ ] Replace `window.solana` with `window?.phantom?.solana`

### Task 8: Fix `display_name[0]` crash on empty string
- Modify: `client/src/MainApp.tsx`
- [ ] Change to `(authUser.display_name?.[0] ?? "?").toUpperCase()`

### Task 9: Fix portfolio nativeSym hardcoded as "BNB" for Phantom users
- Modify: `client/src/MainApp.tsx`
- [ ] Derive `nativeSym` from `walletType` — use "SOL" for Phantom, "BNB" for others

### Task 10: Fix `WELCOME` stale timestamp
- Modify: `client/src/MainApp.tsx`
- [ ] Replace `[WELCOME]` with `[{ ...WELCOME, ts: new Date() }]` in `setMessages` calls

### Task 11: Fix `wallet_address` column too short for Solana keys
- Modify: `server/app/db/models.py`
- [ ] Change `String(42)` → `String(64)`

### Task 12: Move hardcoded Moralis API key to env var
- Modify: `server/app/agents/crypto_agent.py`
- [ ] Read from `os.environ.get("MORALIS_API_KEY", "")` with fallback

### Task 13: EVM chain scan parallelisation
- Modify: `server/app/agents/crypto_agent.py`
- [ ] Replace serial `for chain in evm_chains` loop with `ThreadPoolExecutor` for wallet balance scanning

### Task 14: Fix `totalUsd` always 0 in portfolio endpoint
- Modify: `server/app/api/portfolio.py`
- [ ] Compute total from token `valueUsd` field after conversion

### Task 15: APY label fix — relabel back correctly
- Modify: `server/app/agents/crypto_agent.py`
- [ ] Pool cards: key should be "APY" since DefiLlama provides compound APY, not simple APR

---

## Restore Instructions

If anything breaks, run:
```bash
cd /Users/v/agent-platform && git stash  # or git reset --hard e30c8e8
```
