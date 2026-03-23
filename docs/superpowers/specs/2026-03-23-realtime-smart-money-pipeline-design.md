# Real-Time Smart Money Pipeline — Design Spec

## Problem

The Smart Money Hub is empty most of the time. The current architecture fetches the 100 most recent transactions from 9 DEX programs on every request, filters for $10K+, and discards everything between requests. Transactions that appear on one load disappear on the next because they've been pushed out of Helius's 100-transaction window by newer (smaller) swaps. There is no persistence and no real-time streaming.

## Goals

1. **Persistent accumulation** — Store $10K+ whale transactions in PostgreSQL with a 24-hour rolling window so data accumulates instead of vanishing between requests.
2. **Real-time streaming** — New transactions appear on the frontend instantly via WebSocket (backend infrastructure exists, frontend client needs extension).
3. **Remove wallet page** — Replace internal wallet detail page with external Solscan links.
4. **Merge Flows into Hub** — Single unified Smart Money page with filters, replacing both `/smart-money` and `/flows`.
5. **$0 cost** — Use only the existing Helius free tier.
6. **Solana only** — EVM chain support is a future project.

## Non-Goals

- Helius webhook integration (saved for post-staging deployment)
- EVM chain whale tracking
- Changes to analysis core, Whales page, Entity page, Alerts, DeFi, or Portfolio
- New API keys or paid services
- Authentication changes

## Architecture

### Data Pipeline

```
[WhaleTransactionPoller]          (new background asyncio task)
    │  runs every 15 seconds
    │  calls SolanaClient.get_recent_large_transactions()
    │
    ├─► [PostgreSQL: whale_transactions]   (persist, dedupe by signature)
    │       24h rolling window, cleanup on each cycle
    │
    └─► [StreamHub.publish("whale-transactions", tx)]
            │
            ├─► WebSocket subscribers (frontend)
            └─► SSE subscribers (fallback)
```

### Rate Budget

The poller calls `get_recent_large_transactions()` every 15 seconds. That method fetches from 9 DEX programs in parallel (9 Helius API calls per cycle). To stay within the Helius free tier:

- 9 calls per 15 seconds = 36 calls/minute = 51,840 calls/day
- Helius free tier: ~500K credits/day (enhanced transactions cost ~5 credits each)
- Budget: 51,840 * 5 = ~259K credits/day — well within the 500K daily limit

To further reduce usage, the poller should skip programs that returned 0 qualifying transactions in the last 3 cycles (adaptive polling). This can reduce calls by 30-50% during quiet periods.

### Database Schema

New table `whale_transactions`:

| Column | Type | Notes |
|--------|------|-------|
| `signature` | `String(128)` PRIMARY KEY | Solana tx signature, natural dedup key |
| `wallet_address` | `String(44)` NOT NULL | Matches existing `WebUser.wallet_address` pattern |
| `wallet_label` | `String(128)` NULL | Known whale label if any |
| `token_address` | `String(44)` NOT NULL | Solana mint address |
| `token_symbol` | `String(32)` NOT NULL | |
| `token_name` | `String(128)` NOT NULL | |
| `direction` | `String(8)` NOT NULL | 'buy' or 'sell' |
| `amount_usd` | `Float` NOT NULL | |
| `amount_tokens` | `Float` NOT NULL | |
| `price_usd` | `Float` NOT NULL | |
| `dex_name` | `String(64)` NOT NULL | |
| `tx_timestamp` | `DateTime` NOT NULL | On-chain transaction time (naive UTC, matches existing DB pattern) |
| `created_at` | `DateTime` NOT NULL DEFAULT NOW() | When we ingested it |

Uses SQLAlchemy `DateTime` (not `TIMESTAMPTZ`) to match the existing database layer pattern in `database.py`. All timestamps stored as naive UTC, consistent with the `datetime.utcnow()` pattern used throughout the codebase.

Indexes:
- `ix_whale_tx_created_at` on `created_at` (24h cleanup uses ingestion time, not on-chain time, to guarantee 24h visibility)
- `ix_whale_tx_wallet` on `wallet_address` (wallet aggregation)
- `ix_whale_tx_direction` on `direction` (buy/sell filtering)

### WhaleTransactionPoller

New module: `src/services/whale_poller.py`

Responsibilities:
- Registers both `app.on_startup` and `app.on_cleanup` hooks (following the pattern in `src/api/routes/alerts.py` for the alert producer)
- Creates a new `SolanaClient` context manager per cycle (create, use, close — matching the pattern in `smart_money.py` and `whale.py`)
- Every 15 seconds: calls `SolanaClient.get_recent_large_transactions(min_amount_usd=10000, limit=200)`
- For each transaction, attempts `INSERT ... ON CONFLICT (signature) DO NOTHING`
- Any genuinely new rows (where the insert succeeded) are published to `StreamHub` topic `whale-transactions`
- Deletes rows where `created_at < NOW() - INTERVAL '24 hours'` (uses ingestion time, not on-chain time, to guarantee 24h of UI visibility even for late-discovered transactions)
- Circuit breaker: after 5 consecutive Helius failures, backs off to 60s polling, gradually recovers
- On `app.on_cleanup`: cancels the background asyncio task gracefully

### API Changes

**`GET /api/v1/smart-money/overview`** — Rewritten to query PostgreSQL:
- Aggregates inflow/outflow/net from the `whale_transactions` table (last 24h)
- Top buyers/sellers by wallet aggregation
- Recent transactions list (newest first, limit 100)
- Response is instant (DB query) instead of slow (9 parallel Helius API calls)

### WebSocket Integration

**Backend:** The poller publishes new transactions to `StreamHub` with topic `whale-transactions`. The existing `/api/v1/stream/ws` endpoint delivers them to subscribers.

**Frontend — `RealtimeClient` extension:** The current `RealtimeClient` (`web/lib/realtime.ts`) can establish WebSocket connections and detect fallback to polling, but lacks message-receiving and reconnection APIs. It must be extended with:
- `onMessage(callback: (data: unknown) => void)` — registers a handler on `this.socket.onmessage`
- `subscribe(topic: string, callback)` — convenience method combining `connect_or_fallback` + `onMessage`
- Automatic reconnection with exponential backoff (1s, 2s, 4s, max 30s)
- `close()` cleanup that removes listeners

**React integration:** A new `useWhaleStream()` hook in `web/lib/hooks.ts`:
- On mount: fetches initial data via REST (`/api/v1/smart-money/overview`)
- Opens WebSocket subscription to `whale-transactions` topic
- New transactions from WebSocket are prepended to the React Query cache
- If WebSocket fails, falls back to 15-second React Query polling
- Exposes a `streamStatus` state: `"live"` | `"reconnecting"` | `"polling"`

### Frontend Changes

#### Remove `/wallet` routes
The wallet page directories (`web/app/wallet/`) may or may not exist as physical directories. The actual work is:
- Delete `web/app/wallet/` if it exists
- Remove "Wallet" entry from `web/components/layout/nav-config.ts` (this is where nav items are defined, not in `sidebar.tsx`)
- All wallet address links site-wide become external Solscan links: `https://solscan.io/account/{address}`
- Update: smart-money page, whales page, dashboard, any component rendering wallet addresses

#### Merge Flows into Hub (`/smart-money`)
The redesigned page contains:
- **Metrics row:** Net Flow, Inflow, Outflow, Flow Direction (same as current)
- **Top Buyers / Top Sellers:** Side-by-side tables (same as current, but wallet addresses are Solscan links)
- **Transaction Feed:** Full feed with:
  - Direction filter (All / Buys / Sells)
  - Min USD filter input
  - Live streaming indicator ("Live" / "Reconnecting..." / "Polling")
  - Transactions animate in as they arrive via WebSocket
  - Each row: direction icon, wallet (Solscan link), token, amount, DEX badge, timestamp, Solscan tx link

#### Remove `/flows` routes
- Delete `web/app/flows/` if it exists
- Remove "Flows" entry from `web/components/layout/nav-config.ts`

#### Sidebar update
Final SMART MONEY nav in `nav-config.ts`: Hub, Whales, Entity

### Error Handling

- **Poller failure:** Log and retry on next 15s cycle. Circuit breaker backs off after 5 consecutive failures.
- **WebSocket failure:** Extended `RealtimeClient` auto-reconnects with exponential backoff; `useWhaleStream` falls back to 15s REST polling.
- **Database unavailable:** Poller logs error and retries. Frontend falls back to direct Helius API calls (current behavior).
- **Server restart:** 24h of persisted transactions are immediately available — no cold start gap.
- **Server shutdown:** Poller task cancelled gracefully via `on_cleanup` hook.
- **Cleanup:** Each poll cycle deletes transactions where `created_at` is older than 24h.

## Files Changed

| File | Action |
|------|--------|
| `src/services/whale_poller.py` | **Create** — Background poller service with startup/cleanup hooks |
| `src/storage/database.py` | **Modify** — Add `WhaleTransaction` model and query methods |
| `src/api/routes/smart_money.py` | **Modify** — Read from DB instead of live Helius calls |
| `src/main.py` | **Modify** — Register poller startup/cleanup hooks |
| `web/lib/realtime.ts` | **Modify** — Extend `RealtimeClient` with onMessage, subscribe, reconnection |
| `web/lib/hooks.ts` | **Modify** — Add `useWhaleStream()` hook |
| `web/app/smart-money/page.tsx` | **Modify** — Merge flows UI, add WebSocket streaming, Solscan links |
| `web/app/flows/` | **Delete** (if exists) |
| `web/app/wallet/` | **Delete** (if exists) |
| `web/components/layout/nav-config.ts` | **Modify** — Remove Wallet and Flows nav items |
| Site-wide wallet links | **Modify** — Replace `/wallet/{addr}` with Solscan URLs |

## Future Work

After deploying to a public URL, replace the polling loop with Helius webhooks for true sub-second real-time data. The pipeline architecture (persist → broadcast) stays the same — only the ingestion source changes. See memory: `project_helius_webhook_upgrade.md`.
