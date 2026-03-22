# Platform-Wide Polish — Design Spec

## Goal

Review every remaining page for usability and completeness. Ensure each page serves its purpose fully — no "coming soon" placeholders, no empty states without guidance, no stub features pretending to be real.

## Context

After Specs 1-3 (nav cleanup, smart money overhaul, intel enrichment), several pages still need attention:
- Dashboard could surface more actionable intelligence
- DeFi Discover has a half-working client component
- Overview/Home page search results could be richer
- Shield page works but could show API key status
- Alerts page works but could surface more context
- Portfolio page could show PnL chart

## Non-Goals

- Complete UI redesign or theme changes.
- New feature development beyond what existing APIs support.
- Backend API changes (this is purely frontend polish).

---

## Design

### 1. Dashboard (`/dashboard`)

**Current state:** Functional — stats grid, volume chart, market distribution, grade distribution, trending tokens, whale activity.

**Polish:**
- Add "Last updated" timestamp.
- Make trending token cards clickable → `/token/{address}`.
- Make whale activity items clickable → `/wallet/{address}`.
- Add loading skeletons instead of spinner.

### 2. DeFi Discover (`/defi`)

**Current state:** The DiscoverClient component triggers an opportunity analysis on mount and shows provisional shortlist while loading.

**Polish:**
- Add proper loading state with progress indicator.
- Show provisional shortlist cards with APY, protocol, chain, risk level.
- When analysis completes, show full results with scoring breakdown.
- Add "New Analysis" button to re-trigger.
- Handle error state with retry button.

### 3. Overview / Home (`/`)

**Current state:** Hero, search bar, stats, features grid, how-it-works, CTA.

**Polish:**
- Make trending dropdown results show chain badges.
- Add quick-action buttons: "View Trending", "Track Portfolio", "Smart Money Feed".
- Stats section: ensure numbers are live (they already call `useDashboardStats()`).

### 4. Shield (`/shield`)

**Current state:** Functional approval scanner with revoke capability.

**Polish:**
- Show which chains have API keys configured vs not (using shield status endpoint).
- Add total USD exposure at risk in the summary.
- Sort approvals by risk level (highest first).

### 5. Alerts (`/alerts`)

**Current state:** Functional alerts inbox with severity filters and lifecycle actions.

**Polish:**
- Group alerts by date (Today, Yesterday, Earlier).
- Add alert count per severity in the filter buttons.
- Show "No alerts yet" empty state with explanation of how alerts are generated.

### 6. Portfolio (`/portfolio`)

**Current state:** Functional with wallet connection, holdings, chain exposure, risk breakdown.

**Polish:**
- Add sparkline or mini-chart for 24h PnL trend.
- Make token rows clickable → `/token/{address}`.
- Show total tracked wallets count in header.

---

## Files Changed

| File | Change |
|------|--------|
| `web/app/dashboard/page.tsx` | Clickable items, timestamps, skeletons |
| `web/app/defi/_components/discover-client.tsx` | Loading/error states, new analysis button |
| `web/app/page.tsx` | Chain badges in search, quick-action buttons |
| `web/app/shield/page.tsx` | API key status, exposure total, risk sorting |
| `web/app/alerts/page.tsx` | Date grouping, severity counts, empty state |
| `web/app/portfolio/page.tsx` | Clickable tokens, tracked count |

## Testing

- All pages render without errors.
- Clickable elements navigate correctly.
- Loading and error states display properly.
- Existing tests continue to pass.
