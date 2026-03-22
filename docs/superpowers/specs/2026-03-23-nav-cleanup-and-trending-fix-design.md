# Navigation Cleanup & Trending Fix — Design Spec

## Goal

Clean up the sidebar navigation (remove dead/duplicate entries, restructure groups) and fix the trending tokens page which fails to display tokens due to an envelope unwrapping bug.

## Context

The platform sidebar has accumulated redundant and confusing entries:
- **Analyze group** (DeFi, Token, Pool, Contract) — Token/Pool/Contract are analysis *result* pages reached via search or direct URL, not navigation destinations. DeFi is a discovery feature.
- **Market Overviews** — a hash link to `Dashboard#market-overviews`, not a separate page. Duplicates Dashboard.
- **Portfolio sub-links** (Exposures, Scenarios) — hash links to sections on the same Portfolio page. Clutter.
- **Settings sub-links** (Auth, Preferences, Integrations) — hash links to sections on the same Settings page. Clutter.

The Trending page has a bug where no tokens render because the API response is envelope-wrapped but the frontend doesn't unwrap it.

## Non-Goals

- No pages are deleted — Token, Pool, Contract remain accessible via URL.
- No backend changes.
- No visual redesign of any page content.

---

## Design

### 1. Navigation Restructure

**Current nav (6 groups, 22 items):**

```
DISCOVER:     Overview, Dashboard, Trending, Market Overviews
ANALYZE:      DeFi, Token, Pool, Contract
SMART MONEY:  Hub, Whales, Flows, Wallet, Entity
PROTECT:      Shield, Audits, Rekt, Alerts
PORTFOLIO:    Overview, Exposures, Scenarios
SETTINGS:     Auth, Preferences, Integrations
```

**New nav (5 groups, 16 items):**

```
DISCOVER:     Overview, Dashboard, Trending, DeFi
SMART MONEY:  Hub, Whales, Flows, Wallet, Entity
PROTECT:      Shield, Audits, Rekt, Alerts
PORTFOLIO:    Portfolio
SETTINGS:     Settings
```

**Changes:**

| Action | Item | Reason |
|--------|------|--------|
| Remove group | Analyze | Token/Pool/Contract are reached via search, not nav. DeFi moves to Discover. |
| Move item | DeFi → Discover | It's a discovery/exploration feature, not an analysis input page. |
| Remove item | Market Overviews | Hash link duplicate of Dashboard. |
| Collapse items | Portfolio (Exposures, Scenarios) | Hash links to same page — one entry is enough. |
| Collapse items | Settings (Auth, Preferences, Integrations) | Hash links to same page — one entry is enough. |

**File:** `web/components/layout/nav-config.ts`

### 2. Trending Tokens Envelope Bug

**Root cause:** The backend's `get_trending_tokens` handler wraps responses in `envelope_response()`, producing `{ "status": "ok", "data": { "tokens": [...], ... } }`. The frontend's `getTrendingTokens()` passes the raw response directly to `normalizeTrendingResponse()`, which looks for `raw.tokens` — but tokens are at `raw.data.tokens`.

**Fix:** Add `unwrapEnvelope()` call before normalization in all four trending API functions:

- `getTrendingTokens()`
- `getNewPairs()`
- `getGainers()`
- `getLosers()`

This is the same pattern already used by `getWalletPortfolio()`, `getWhaleActivity()`, and `getSmartMoneyOverview()`.

**File:** `web/lib/api.ts`

### 3. Icon Import Cleanup

After removing nav entries, unused icon imports (`Coins`, `Droplets`, `Search` used only by removed Analyze items) should be cleaned from `nav-config.ts`.

**File:** `web/components/layout/nav-config.ts`

---

## Testing

- Verify sidebar renders 5 groups with correct items.
- Verify Trending page renders token cards for "All Chains" and each individual chain filter.
- Verify Token (`/token/[address]`), Pool (`/pool`), and Contract (`/contract`) pages still work via direct URL.
- Verify Dashboard page is unchanged.
- Verify DeFi page is accessible from Discover group.

## Files Changed

| File | Change |
|------|--------|
| `web/components/layout/nav-config.ts` | Restructure nav groups, clean imports |
| `web/lib/api.ts` | Add `unwrapEnvelope()` to 4 trending functions |
