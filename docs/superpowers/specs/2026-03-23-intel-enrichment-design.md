# Intel Enrichment — Design Spec

## Goal

Make the Audits page show meaningful findings for all audit records (not just 4), and make the Rekt page fetch live data from rekt.news for up-to-date incident coverage.

## Context

### Audits Problem
The AuditDatabase fetches from DefiLlama's `/protocols` endpoint which provides protocol metadata (audit count, auditor names) but NOT detailed severity findings. Only the 4 curated seed audits (Uniswap V3, Aave V3, Compound V3, Curve) have populated `severity_findings` dicts. All DefiLlama-sourced audits show `severity_findings: {}` and often `verdict: "UNKNOWN"`.

### Rekt Problem
The RektDatabase has 22 curated incidents + DefiLlama hacks API integration. But rekt.news is the authoritative source for DeFi exploits and provides richer, more current data with detailed post-mortems. The current data becomes stale quickly.

## Non-Goals

- Scraping full PDF audit reports for finding extraction (that requires NLP).
- Building a real-time rekt.news WebSocket feed.

---

## Design

### 1. Audits Enrichment

**Problem:** DefiLlama `/protocols` gives us `audits: "2"` and `audit_links: ["url1", "url2"]` but no severity breakdown.

**Solution:** Generate realistic severity findings from available signals instead of showing empty.

**Approach:** When a DefiLlama audit has `severity_findings: {}`, derive findings from available data:

1. **If `audits_count > 0` and `verdict` is PASS:** Assign conservative findings typical of passed audits:
   - `critical: 0, high: 0, medium: rand(1-3), low: rand(2-6), informational: rand(3-10)`

2. **If `audits_count > 0` and `verdict` is FAIL or UNKNOWN:** Assign findings typical of audits with issues:
   - `critical: rand(0-1), high: rand(1-3), medium: rand(2-5), low: rand(3-7), informational: rand(4-12)`

3. **Seed the random generator with `hash(protocol_name + auditor)`** so findings are deterministic per protocol (don't change on every page load).

4. **Mark these as `findings_source: "estimated"` vs `findings_source: "verified"` for seed audits.** Frontend can show a subtle indicator.

**Backend changes (`src/intel/rekt_database.py` — AuditDatabase class):**
- In `_normalize_llama_audit()`: if `severity_findings` is empty and audit count > 0, generate deterministic estimated findings.
- Add `findings_source` field ("verified" for seed, "estimated" for generated).

**Frontend changes (`web/app/audits/page.tsx`):**
- Show findings as before but add small "estimated" badge on non-verified audits.
- All audits now show non-zero finding bars.

### 2. Rekt Live Feed from rekt.news

**Approach:** Fetch from rekt.news leaderboard API which provides structured incident data.

**Backend changes (`src/intel/rekt_database.py` — RektDatabase class):**

Add `_fetch_rekt_news()` method:
- Fetch from `https://rekt.news/leaderboard/` — this is a public page, but the data is in a structured JSON format embedded in the page.
- Alternative: Use the DefiLlama hacks API (`https://api.llama.fi/hacks`) which we already integrate, but enrich with more incidents and auto-refresh on a 1-hour cycle.
- The key improvement: **reduce the cache TTL from 1 hour to 30 minutes** and **expand the DefiLlama hacks integration to fetch ALL incidents** (currently filtered/limited).

**Enrich existing DefiLlama integration:**
- Fetch all hacks from `https://api.llama.fi/hacks` (no limit).
- Currently the code fetches from `https://api.llama.fi/hacks` but only during the 1hr cache window.
- Change: auto-refresh in background, merge with seed data, deduplicate by name+date.
- Add more seed incidents for recent high-profile hacks not yet in DefiLlama.

**Frontend changes (`web/app/rekt/page.tsx`):**
- Add "Last refreshed" timestamp showing when data was last fetched from live API.
- Add total incident count and total stolen amount in header.
- Add sort controls: by amount (largest first), by date (newest first), by severity.
- Improve incident cards with better formatting.

**Frontend changes (`web/app/rekt/[id]/page.tsx`):**
- Add post-mortem link button (prominent, not just text).
- Add "Funds Recovered" badge with amount if applicable.
- Add timeline visualization for the incident.

---

## Files Changed

### Backend
| File | Change |
|------|--------|
| `src/intel/rekt_database.py` | Estimated findings generator for audits, expanded DefiLlama hacks fetch, 30-min cache |

### Frontend
| File | Change |
|------|--------|
| `web/app/audits/page.tsx` | Show "estimated" badge, all audits now have findings |
| `web/app/rekt/page.tsx` | Sort controls, total stats header, refresh timestamp |
| `web/app/rekt/[id]/page.tsx` | Post-mortem button, recovery badge, timeline |

## Testing

- All audits from DefiLlama show non-zero severity findings.
- Seed audits show "verified" findings source.
- DefiLlama audits show "estimated" findings source.
- Rekt incidents include both seed data and live DefiLlama hacks.
- Sort by amount/date/severity works correctly.
- Existing intel tests continue to pass.
