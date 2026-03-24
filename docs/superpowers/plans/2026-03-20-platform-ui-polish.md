# Platform UI Polish Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Overhaul the incomplete barebones frontend stubs (Alerts, Smart Money, Whales, Sidebar) into a beautiful, fully functional UI using Tailwind, Lucide React, and Radix, directly matching the platform overhaul design spec.

**Architecture:** Use `GlassCard`, `Button`, `Badge`, and `lucide-react` icons to create modern, responsive dashboard pages. Connect missing navigation routes. Fix any data fetching and rendering issues from API payloads.

**Tech Stack:** Next.js App Router, React, Tailwind CSS, Lucide React, React Query

---

### Task 1: Global Information Architecture (Sidebar & Nav)

**Files:**
- Modify: `web/components/layout/nav-config.ts`
- Modify: `web/components/layout/sidebar.tsx`
- Modify: `web/components/layout/mobile-nav.tsx`
- Test: `web/tests/app/app-shell-layout.test.tsx`

- [ ] **Step 1:** Modify `nav-config.ts` to define the full hierarchical taxonomy from the spec. Use groups (Discover, Analyze, Smart Money, Protect, Portfolio, Settings) with their respective child routes (e.g., Smart Money -> Hub, Whales, Flows). Add Lucide icons to definitions.
- [ ] **Step 2:** Modify `sidebar.tsx` to render navigation groups with headers and child links properly styled. Handle active route states correctly.
- [ ] **Step 3:** Modify `mobile-nav.tsx` to match the new nested/grouped taxonomy in a mobile-friendly sheet menu.
- [ ] **Step 4:** Ensure `web/tests/app/app-shell-layout.test.tsx` passes.
- [ ] **Step 5:** Commit changes `feat: implement full platform information architecture in navigation`.

### Task 2: Alerts Inbox Redesign

**Files:**
- Modify: `web/app/alerts/page.tsx`
- Modify: `web/tests/app/alerts.page.test.tsx`

- [ ] **Step 1:** In `web/app/alerts/page.tsx`, replace the bare text/buttons with a professional inbox layout. Use a two-column or main-content layout.
  - Header with title "Alerts Inbox", unread badge, and an icon button to request notifications (`BellRing`).
  - Filter bar (All, High, Medium, Low) using `Tabs` or styled buttons.
  - Use `GlassCard` to render individual alerts with severity colors (Critical=red, High=orange, Medium=yellow, Low=blue/emerald), icons (e.g., `AlertTriangle`, `Info`), formatted time, and a "View Token" button link.
- [ ] **Step 2:** Add an empty state component (e.g., `Inbox` icon, "No alerts found").
- [ ] **Step 3:** Ensure the component still calls `requestAlertPermission` and uses `useAlerts` correctly.
- [ ] **Step 4:** Update `web/tests/app/alerts.page.test.tsx` to ensure it targets the new UI labels/buttons instead of the old stub texts.
- [ ] **Step 5:** Commit changes `feat: redesign alerts page with polished inbox UI`.

### Task 3: Smart Money Hub Redesign

**Files:**
- Modify: `web/app/smart-money/page.tsx`
- Modify: `web/tests/app/smart-money.page.test.tsx` (create or update if missing)

- [ ] **Step 1:** In `web/app/smart-money/page.tsx`, transform the 3 bare cards into a comprehensive dashboard.
  - Header: "Smart Money Hub" with `BrainCircuit` or `Wallet` icon.
  - Top Stats: Net Flow, Inflows, Outflows presented cleanly.
  - Middle Section: "Top Buyers" and "Top Sellers" data tables/lists. Iterate over `data.top_buyers` and `data.top_sellers` (which are arrays of `SmartMoneyParticipant`). Show address (truncated), net flow value (formatted USD), and an `ExternalLink` or profile link.
- [ ] **Step 2:** Ensure graceful loading/error states using Skeleton or `Loader2`.
- [ ] **Step 3:** Write/Update tests to confirm it renders the hub correctly.
- [ ] **Step 4:** Commit changes `feat: redesign smart money hub into comprehensive dashboard`.

### Task 4: Whales Page Fixes

**Files:**
- Modify: `web/app/whales/page.tsx`
- Modify: `web/tests/app/whales.page.test.tsx`

- [ ] **Step 1:** Identify if `web/app/whales/page.tsx` is broken due to API typing (e.g., `data.transactions.length` failing if envelope unwrapping missed `transactions`, though whale API doesn't use `fetchAPI` unwrapping globally yet, maybe it returns an object). Inspect the hook/API definition to ensure `data.transactions` is safe to read.
- [ ] **Step 2:** Check if the `useWhaleActivity` hook correctly extracts the envelope if required by the new standard. Update the page to gracefully handle empty `data` or missing `data.transactions`. Add a check `data?.transactions?.map` instead of assuming it's an array if it might be undefined.
- [ ] **Step 3:** Polish any visual quirks in the Whales page, ensuring responsiveness.
- [ ] **Step 4:** Update/run tests to confirm Whales renders.
- [ ] **Step 5:** Commit changes `fix: whale page rendering and envelope data access`.
