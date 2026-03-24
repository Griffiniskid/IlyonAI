# Platform Bugfix and Feature Wiring Design

Date: 2026-03-22
Status: Draft
Companion to: `2026-03-19-platform-wide-product-overhaul-design.md` (long-term vision)
Primary focus: Fix all currently broken features and wire up incomplete plumbing so every shipped page works end-to-end

## Summary

Users report that most pages outside the analysis core show empty data, zeros, or placeholder content. Root causes are a mix of actual bugs (wrong constructor calls, missing context managers), missing API keys, hardcoded stubs, and unfinished wiring. This spec addresses every reported issue with minimal, targeted fixes — no architectural redesign.

All work targets `.worktrees/main-local/`.

## Scope

**In scope (Tier 1 — fix broken code):**
- Smart Money pipeline crash (SolanaClient constructor + context manager)
- Flows page (same root cause)
- Wallet Lookup (same root cause)
- Navigation gaps

**In scope (Tier 2 — wire incomplete features):**
- Shield approval scanner (API key handling + graceful degradation)
- Audit records (live fetch from DefiLlama)
- Entity page (wire to backend GraphStore/ProfileService)
- Portfolio capability display (meaningful reporting + PnL approximation)
- Alerts system (bootstrap a producer from existing data sources)
- Settings integrations page
- Rekt database enrichment

**Out of scope:**
- Analysis core (user explicitly excluded)
- WebSocket/SSE real-time transport (Phase 3 of mega-spec)
- Command palette (Phase 1 of mega-spec)
- App shell redesign (Phase 1 of mega-spec)
- Full forensics implementation (Phase 2 of mega-spec)

## Root Cause Analysis

| Surface | Symptom | Root Cause | Fix Category |
|---|---|---|---|
| Smart Money Hub | All zeros | `SolanaClient()` called without `rpc_url`; class lacks `__aenter__`/`__aexit__` — error silently caught | Tier 1: Bug |
| Flows | Empty list | Consumes same broken `/api/v1/smart-money/overview` | Tier 1: Bug |
| Wallet Lookup | "Not in snapshot" | Searches empty `top_buyers`/`top_sellers` arrays (consequence of above) | Tier 1: Bug |
| Entity | Zero info | `entity/[id]/page.tsx` is a stub — no data fetching | Tier 2: Wiring |
| Shield | No approvals | All 7 Etherscan API keys unset, fallback to `"YourApiKeyToken"` | Tier 2: Config + degradation |
| Audit Records | Only 4 | `AuditDatabase` has 4 hardcoded records, no live fetch | Tier 2: Enhancement |
| Rekt | Sparse data | 9 seed records + DefiLlama; no detail page | Tier 2: Enhancement |
| Alerts | 0 alerts | `InMemoryAlertStore` is CRUD shell; no alert producer exists | Tier 2: Wiring |
| Portfolio capabilities | 40x "degraded" | All capabilities default to degraded; no providers report overrides | Tier 2: Wiring + display |
| Portfolio PnL | Always $0 | Hardcoded `total_pnl_usd=0, total_pnl_percent=0` | Tier 2: Approximation |
| Settings integrations | Empty | Page has no integrations section | Tier 2: New section |
| Navigation | Missing routes | Header lacks Smart Money, Rekt, Alerts links | Tier 1: Config |

## Design

### 1. Smart Money Pipeline Fix (Tier 1)

**Files:** `src/api/routes/smart_money.py`, `src/data/solana.py`

**Changes:**

1. Add `__aenter__` and `__aexit__` to `SolanaClient`:
   ```python
   async def __aenter__(self):
       return self

   async def __aexit__(self, *args):
       await self.close()
   ```

2. In `get_smart_money_overview()`, instantiate with config:
   ```python
   from src.config import get_settings
   settings = get_settings()
   async with SolanaClient(rpc_url=settings.solana_rpc_url, helius_api_key=settings.helius_api_key) as client:
       activity = await client.get_whale_transactions(limit=50)
   ```

3. Replace bare `except Exception` with structured error handling that returns an error envelope via `envelope_response` with appropriate HTTP status, so the frontend can distinguish "no data yet" from "data fetch failed."

**Downstream impact:** Fixes Smart Money Hub, Flows, and Wallet Lookup simultaneously since all three consume the same endpoint.

### 2. Navigation Updates (Tier 1)

**Files:** `web/components/layout/header.tsx`

**Changes:**

Add missing nav items. Current nav has 6 items (Dashboard, Trending, Shield, Portfolio, Whales, Settings). Add:
- Smart Money (links to `/smart-money`)
- Rekt (links to `/rekt`)
- Alerts (links to `/alerts`)

Group logically:
- Discover: Dashboard, Trending
- Analyze: (existing token/pool/contract/defi routes are already linked contextually)
- Smart Money: Smart Money hub (with sub-links to Whales, Flows, Entity)
- Protect: Shield, Rekt, Alerts
- Portfolio
- Settings

### 3. Shield Graceful Degradation (Tier 2)

**Files:** `src/shield/approval_scanner.py`, `src/config.py`, API route for shield status

**Changes:**

1. Add a `/api/v1/shield/status` endpoint that returns per-chain availability:
   ```json
   {
     "chains": {
       "ethereum": {"available": true, "source": "etherscan"},
       "bsc": {"available": false, "reason": "API key not configured"},
       ...
     }
   }
   ```

2. In `ApprovalScanner`, check if the API key for a chain is set and not the placeholder `"YourApiKeyToken"` before attempting a scan. Return an explicit "not configured" result instead of a network error.

3. Frontend shield page reads `/api/v1/shield/status` and shows per-chain status badges. Chains without keys show "Configure API key in Settings" with a link.

4. Where Moralis provides equivalent token approval data, use it as a fallback for EVM chains.

### 4. Audit Records Live Fetch (Tier 2)

**Files:** `src/intel/rekt_database.py` (note: `AuditDatabase` is co-located in this file alongside `RektDatabase`)

**Changes:**

1. Add `fetch_audit_data()` method to `AuditDatabase` that pulls protocol audit metadata from DefiLlama's protocols endpoint (which includes `audit_links`, `audits`, `audit_note` fields).

2. Merge with `KNOWN_AUDITS` seed data, deduplicate by protocol name.

3. Cache for 1 hour (same pattern as `RektDatabase._cached_incidents`).

4. Update the backend route serving audit data to use the enhanced method.

### 5. Rekt Database Enrichment (Tier 2)

**Files:** `src/intel/rekt_database.py`

**Changes:**

1. Expand `KNOWN_REKT_INCIDENTS` seed data to ~25 well-known incidents covering diverse attack types (flash loan, reentrancy, oracle manipulation, bridge exploit, rug pull, key compromise).

2. Enhance DefiLlama fetch to capture additional fields where available: `funds_returned`, `technique`, `post_mortem_url`.

3. Add severity classification heuristic:
   - CRITICAL: > $100M
   - HIGH: $10M–$100M
   - MEDIUM: $1M–$10M
   - LOW: < $1M

### 6. Entity Page Wiring (Tier 2)

**Files:** `web/app/entity/[id]/page.tsx`, new `src/api/routes/entity.py`, `src/smart_money/profile_service.py`, `src/smart_money/graph_store.py`

**Changes:**

1. Add backend routes:
   - `GET /api/v1/entities` — list known entities from `GraphStore`
   - `GET /api/v1/entities/{id}` — get entity profile from `ProfileService`

2. Wire `GraphStore` to ingest wallet data from the smart money flow pipeline so entities accumulate over time.

3. Frontend entity page fetches from `/api/v1/entities/{id}` and displays:
   - Entity label and confidence
   - Associated wallets
   - Aggregated flow volume
   - Activity summary

4. Entity explorer page (`/entity`) shows a list of known entities with search/filter.

### 7. Portfolio Capability & PnL (Tier 2)

**Files:** `src/portfolio/multichain_aggregator.py`, `src/api/routes/portfolio.py`, `web/app/portfolio/page.tsx`

**Changes:**

**Capabilities:**

1. Wire existing Solana provider to report `capability_overrides()`:
   - `token_balances: available`
   - `nft_balances: available` (if Helius supports it)

2. Wire EVM/Moralis provider similarly:
   - `token_balances: available`
   - `nft_balances: available`

3. All other capabilities (LP, lending, vault, risk, alerts) remain `degraded` with honest reasons until backends exist.

**Display:**

1. Change portfolio UI to group capabilities by state:
   - Show "Available" capabilities with green indicators
   - Show count of degraded capabilities in a collapsed section: "5 capabilities degraded" expandable to see details
   - Remove the repetitive "available 1, degraded 5" per-chain pattern

2. Show chain count as "X of Y chains active" with a breakdown.

**PnL:**

1. Use DexScreener price data to compute approximate 24h value change:
   - Fetch current token prices for held tokens
   - Fetch 24h-ago prices (DexScreener provides 24h change percentages)
   - Compute estimated delta
   - Label clearly as "Est. 24h Change" (not "PnL")

2. Replace hardcoded `total_pnl_usd=0` with the computed estimate.

### 8. Alerts System Bootstrap (Tier 2)

**Files:** `src/api/routes/alerts.py`, new `src/alerts/producer.py`

**Changes:**

1. Create `AlertProducer` class that generates alerts from existing data:
   - Whale transactions above configurable threshold → "Large flow detected"
   - New rekt incidents (on each rekt database refresh) → "Security incident reported"
   - Portfolio value swings > 10% → "Portfolio swing detected"

2. Run producer as a periodic `asyncio.create_task` in app startup (every 5 minutes).

3. Producer obtains the shared `InMemoryAlertStore` instance via `app[ALERT_STORE_KEY]` (the same key used by the alerts route setup). The producer task receives the `app` reference at startup and reads the store from it.

4. Existing alerts inbox UI (`/alerts`) should render alerts once the store has data.

5. Keep in-memory storage for now. Persistence is a Phase 3 concern.

### 9. Settings Integrations Page (Tier 2)

**Files:** `web/app/settings/page.tsx` (or new `web/app/settings/integrations/page.tsx`)

**Changes:**

1. Add an "Integrations" section/tab to Settings with form fields for:
   - Helius API Key (Solana RPC)
   - Moralis API Key (EVM data)
   - Etherscan API Key (Ethereum)
   - BscScan API Key
   - PolygonScan API Key
   - (remaining explorer keys)

2. Store in `localStorage` under a namespaced key.

3. Send configured keys via `X-Api-Key-*` headers on relevant API requests.

4. Backend reads from request headers with fallback to `.env` config.

5. Show connection status per integration: green check if key is set and a quick health-check ping succeeds, red X otherwise.

**Security note:** Storing API keys in `localStorage` means any XSS vulnerability would expose them. This is acceptable for the current self-hosted testing phase. For production, keys should be stored server-side via an encrypted settings API. This tradeoff is explicitly deferred to the mega-spec's later phases.

## Implementation Order

Recommended sequence based on dependencies:

1. **Smart Money pipeline fix** (Section 1) — unblocks 3 pages at once
2. **Navigation updates** (Section 2) — independent, quick win
3. **Shield degradation** (Section 3) — independent
4. **Audit records live fetch** (Section 4) — independent, similar pattern to rekt
5. **Rekt enrichment** (Section 5) — enriches existing rekt pages
6. **Entity wiring** (Section 6) — depends on smart money fix for data flow
7. **Portfolio capability & PnL** (Section 7) — independent
8. **Alerts bootstrap** (Section 8) — depends on other data sources being live
9. **Settings integrations** (Section 9) — independent but lower priority

Note: The rekt detail page (`/rekt/[id]`) and its backend route (`GET /api/v1/intel/rekt/{id}`) already exist and are fully implemented.

## Testing Strategy

Each fix should include:

- Unit test for the backend change (mock external APIs)
- Verify the frontend page renders with both data and error states
- Manual smoke test with actual API keys where available

No new test framework or infrastructure needed — use existing pytest + vitest setup.

## Risks

| Risk | Mitigation |
|---|---|
| Helius RPC URL not configured in .env | Smart money page shows explicit "RPC not configured" error instead of silent zeros |
| Etherscan API keys still missing after fix | Shield shows per-chain "configure in settings" guidance |
| DexScreener rate limits on PnL estimation | Cache prices aggressively (5-min TTL), degrade gracefully |
| InMemoryAlertStore loses data on restart | Acceptable for this phase; persistence is Phase 3 |
| Entity graph starts empty | Expected cold-start; entities accumulate as flows process |
