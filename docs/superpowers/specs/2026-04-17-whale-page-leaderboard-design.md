# Whale Page — Token Leaderboard Redesign

**Date:** 2026-04-17
**Status:** Approved (brainstorm)
**Owner:** Web + API

## Problem

`/whales` is a chronological list of large transactions filtered out of the same `whale_transactions` table that powers Smart Money. Users browsing the page see raw flow but cannot answer the two questions they actually have: *what are whales buying right now*, and *what new tokens are showing up on the radar*. A tx feed is the wrong shape for both jobs — signal is buried under noise, and aggregation is left to the user's eyeballs.

## Goals

- **Alpha hunting** — surface tokens with the strongest, freshest, hardest-to-fake whale buying so a user can ride the wave.
- **Discovery** — make tokens that "just appeared on the radar" obvious without manual filtering.
- **Honesty about scope** — the data is Solana-only; the UI must reflect that, not pretend to support EVM.

## Non-goals

- EVM whale ingestion. That is its own backend project (new RPC adapter, new dedup, new credit budget) and lands as a separate spec.
- Persistent watchlists / starred wallets. Useful, but adds account-bound storage concerns. Re-evaluate after the leaderboard ships.
- Per-wallet PnL / win-rate. The existing whale-profile page can grow this independently.
- Replacing `/whales/token/{address}` (per-token whale list). That route stays — only the index page changes.

## Design

### Backend

Two new endpoints, both reading from the existing `whale_transactions` table populated by `WhaleTransactionStream`.

#### `GET /api/v1/whales/leaderboard`

Query params:

| Param | Type | Default | Notes |
|---|---|---|---|
| `window` | `1h` \| `6h` \| `24h` | `6h` | Lookback for aggregation |
| `sort` | `composite` \| `buyers` \| `new` | `composite` | Ordering of the result set |
| `limit` | int | 50 | Cap at 100 |

Per-token row in response:

```json
{
  "token_address": "...",
  "token_symbol": "WIF",
  "token_name": "dogwifhat",
  "net_flow_usd": 2_400_000,
  "gross_buy_usd": 2_700_000,
  "gross_sell_usd": 300_000,
  "distinct_buyers": 8,
  "distinct_sellers": 2,
  "tx_count": 14,
  "composite_score": 87.0,
  "is_new_on_radar": true,
  "acceleration": 2.4,
  "top_whales": [
    {"address": "...", "label": "Alameda", "side": "buy", "amount_usd": 800_000}
  ]
}
```

**Composite score** (0–100, normalized within result set):

```
score = 100 * (
  0.40 * percentile(distinct_buyers) +
  0.30 * percentile(max(net_flow_usd, 0)) +
  0.20 * percentile(buy_sell_ratio) +
  0.10 * percentile(acceleration)
)
```

`buy_sell_ratio = gross_buy_usd / max(gross_sell_usd, 1)` capped at 100 to avoid divide-by-near-zero outliers. `acceleration = (tx_count_in_last_window/4) / max(tx_count_in_first_3*window/4 / 3, 1)` — ratio of recent quarter-window pace to earlier-three-quarters pace.

Each component is a 0–1 percentile rank among the candidate set, so the score is interpretable across windows.

**`is_new_on_radar`:** true iff the token has zero whale activity in `(now - 2*window, now - window)`. Computed via a single grouped SQL query, not N+1.

**`top_whales`:** up to 3 wallets with the largest absolute USD on this token in the window, with `wallet_label` from the row (which falls back to the `KNOWN_WHALES` map at API layer).

Caching: 60s by `(window, sort, limit)` key, identical pattern to the existing `_token_cache_ttl` in `whale.py`. `force_refresh=true` busts the cache.

#### `GET /api/v1/whales/top-wallets`

Query params:

| Param | Type | Default | Notes |
|---|---|---|---|
| `window` | `1h` \| `6h` \| `24h` | `6h` | |
| `limit` | int | 15 | Cap at 50 |

Per-wallet row:

```json
{
  "address": "...",
  "label": "Alameda",
  "total_volume_usd": 4_200_000,
  "tx_count": 12,
  "tokens_touched": 5,
  "dominant_side": "buy"
}
```

`dominant_side`: `"buy"` if `gross_buy / total > 0.6`, `"sell"` if `< 0.4`, else `"mixed"`. Sorted by `total_volume_usd` desc.

Same caching pattern.

#### Database

A single new method on `Database`:

```python
async def get_whale_aggregations(self, hours: int) -> dict:
    """Returns {'rows': [{token_address, ...tx fields...}], 'prior_token_addresses': set[str]}.

    Single query for window rows + a separate single query for prior-window
    distinct token_addresses (used to compute is_new_on_radar).
    """
```

This keeps the route handlers free of SQL and centralizes the table contract.

### Frontend

Full rewrite of `web/app/whales/page.tsx`. The old chronological feed is removed entirely; users wanting tx-level detail per token use `/token/[address]` (which already shows whale activity for that token).

**Layout:**

```
┌─────────────────────────────────────────────────────────────┐
│  🐋 Whale Tracker                          [Refresh ↻]      │
│  Discover what whales are buying right now                  │
├─────────────────────────────────────────────────────────────┤
│  Window: [1h] [6h ●] [24h]    Sort: [Score ●] [Buyers] [New]│
├──────────────────────────────────────────┬──────────────────┤
│  TOKEN LEADERBOARD                       │  TOP WHALES (6h) │
│  ┌────────────────────────────────────┐  │  ┌────────────┐  │
│  │ #1  WIF  dogwifhat       Score 87  │  │  Alameda     │  │
│  │     +$2.4M net  •  8 buyers        │  │  $4.2M • 12tx│  │
│  │     ↑ accelerating  •  🆕 new      │  │  ──────────  │  │
│  │     [whale1][whale2][whale3]+5     │  │  Jump        │  │
│  ├────────────────────────────────────┤  │  $2.8M • 7tx │  │
│  │ #2  BONK ...                       │  │  ──────────  │  │
│  └────────────────────────────────────┘  │  ...         │  │
└──────────────────────────────────────────┴──────────────────┘
```

**Components** (each focused, testable, in `web/app/whales/_components/`):

- `window-sort-controls.tsx` — pill toggles for window + sort, controlled by page state
- `leaderboard-row.tsx` — rank, token symbol/name (links to `/token/[address]`), composite score, net-flow chip, distinct-buyers chip, conditional `↑ accelerating` and `🆕 new` badges, top-whale avatar stack with overflow count
- `top-whales-panel.tsx` — sidebar list, each item links to `/whales/wallet/[address]` (existing route)
- `empty-state.tsx` — "Quiet hour — try a wider window" with one-click jump to 24h

**Hooks** added to `web/lib/hooks.ts`:

- `useWhaleLeaderboard({ window, sort })` — TanStack Query, `staleTime: 60_000`, `queryKey: ["whales", "leaderboard", window, sort]`. Enabled on mount (no click-to-search gate — the goal is "what's happening right now").
- `useTopWhales({ window })` — same pattern, `queryKey: ["whales", "top", window]`.

**API client** added to `web/lib/api.ts`:

- `getWhaleLeaderboard({ window, sort, limit, forceRefresh })`
- `getTopWhales({ window, limit })`
- Response normalizers if the envelope wrapper requires unwrapping (match existing `normalizeWhaleActivityResponse` pattern).

**Types** added to `web/types/index.ts`:

- `WhaleLeaderboardRow`, `WhaleLeaderboardResponse`
- `TopWhaleRow`, `TopWhalesResponse`
- `WhaleWindow = "1h" | "6h" | "24h"`, `WhaleSort = "composite" | "buyers" | "new"`

**Responsive:** sidebar collapses below the leaderboard at the `md` breakpoint; window/sort pills wrap.

**Files removed from this page:** the existing tx-list rendering and `useWhaleActivity` call inside `web/app/whales/page.tsx` are deleted. `useWhaleActivity` itself stays in `hooks.ts` (still exported) only if other pages consume it; otherwise removed. (Verify in implementation.)

### Data flow

1. Page mounts → both queries fire in parallel with default `window=6h`.
2. Window pill change → both query keys change → TanStack refetches; previous data stays visible during fetch (no flash).
3. Sort pill change → only leaderboard query key changes; sidebar unaffected.
4. Refresh button → `queryClient.invalidateQueries({ queryKey: ["whales"] })` → both refetch with `forceRefresh=true`.
5. Backend computes from `whale_transactions` table on demand; no new background job. Cleanup remains the existing `cleanup_old_whale_transactions` cron.

### Error handling

- Backend exception → `envelope_error_response(code="LEADERBOARD_FAILED" | "TOP_WHALES_FAILED")`. Frontend renders inline error card with retry; sidebar fails independently of leaderboard (one panel down ≠ whole page broken).
- Empty window → frontend renders the `empty-state` component with a one-click jump to 24h. Same copy whether the table is empty because of a quiet hour or because the stream hasn't seeded yet — the user-facing meaning is identical.

## Testing

### Backend (`tests/api/test_whale_leaderboard.py`, new)

- Composite score ordering — handcrafted txs across 3 tokens; assert ranking matches expected
- Window filtering — txs at the boundary (just inside / just outside) are correctly in/excluded
- `is_new_on_radar` — token with prior-window activity returns false; token without returns true
- `sort=buyers` and `sort=new` reorder correctly
- Empty result set returns `200` with `[]`, not `500`
- `top-wallets` aggregation — same wallet across multiple tokens collapses to one row, volume summed
- Invalid window param returns `400 INVALID_PARAMS`

### Frontend (`web/tests/app/whales.page.test.tsx`, full rewrite)

- Default render shows leaderboard + sidebar with mocked data
- Window pill change triggers refetch with new query key
- Sort pill change triggers refetch with new query key
- Empty state renders the "quiet hour" copy and jump-to-24h button
- Leaderboard row link goes to `/token/[address]`
- Sidebar wallet item link goes to `/whales/wallet/[address]`
- Sidebar query failure does not unmount the leaderboard

### Live validation (post-implementation)

Beyond unit tests, the implementation is not done until:

1. Backend up via existing `docker compose` / `python -m src.main`.
2. `curl http://localhost:8000/api/v1/whales/leaderboard?window=6h` returns `200` with a non-empty `data.rows` array (assuming the stream has seeded the table).
3. `curl http://localhost:8000/api/v1/whales/top-wallets?window=6h` returns `200` with a non-empty `data.rows` array.
4. Frontend dev server up; navigating to `/whales` renders the leaderboard with real data, window pills change the data, refresh works, links navigate to existing token / wallet pages.

## Migration / rollback

No DB migration. The new endpoints add only read paths. Rollback is `git revert` of the commit(s); no data shape changes.

## Open questions

None at design time. Implementation may surface response-shape minutiae (field naming, normalization ranges) — those are decided in the plan, not the spec.
