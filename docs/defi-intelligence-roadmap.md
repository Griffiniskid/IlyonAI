# DeFi Intelligence Roadmap

## Product Direction

Turn DeFi from a raw pools-and-yields screener into a capital allocation intelligence surface. The core objects are:

- `protocol`: quality, incident history, audits, deployment breadth, operational confidence
- `opportunity`: deployable pool, farm, or lending setup with explicit score breakdowns
- `scenario`: what can break, what to monitor, and what changes the thesis

## What Is Implemented

### Backend

- Added `src/defi/ai_explainer.py` for optional AI market, protocol, and opportunity explanations with deterministic fallbacks
- Added a fuller DeFi domain layer:
  - `src/defi/entities.py`
  - `src/defi/docs_analyzer.py`
  - `src/defi/history_store.py`
  - `src/defi/evidence.py`
  - `src/defi/risk_engine.py`
  - `src/defi/scenario_engine.py`
  - `src/defi/ai_router.py`
  - `src/defi/opportunity_engine.py`
- Reworked `src/defi/intelligence_engine.py` into a facade over the new opportunity engine
- Upgraded `src/api/routes/defi.py` with:
  - `GET /api/v1/defi/analyze`
  - `GET /api/v1/defi/opportunities`
  - `GET /api/v1/defi/opportunities/{opportunity_id}`
  - upgraded `GET /api/v1/defi/protocol/{slug}`
  - `GET /api/v2/defi/discover`
  - `GET /api/v2/defi/protocols/{slug}`
  - `GET /api/v2/defi/opportunities/{opportunity_id}`
  - `GET /api/v2/defi/compare`
  - `POST /api/v2/defi/simulate/lp`
  - `POST /api/v2/defi/simulate/lending`
  - `POST /api/v2/defi/positions/analyze`
- Updated `src/api/app.py` API metadata so the new DeFi surfaces are discoverable
- Updated `src/api/schemas/requests.py` and `src/api/schemas/responses.py` so DeFi request and response models match the new frontend payloads

### Frontend

- Rebuilt `web/app/defi/page.tsx` into an advanced discover page with:
  - ranked opportunities
  - scorecards
  - AI market brief
  - conservative / balanced / aggressive picks
  - protocol spotlights
- Added `web/app/defi/opportunity/[id]/page.tsx`
- Added `web/app/defi/protocol/[slug]/page.tsx`
- Added `web/app/defi/compare/page.tsx`
- Expanded `web/app/defi/lending/page.tsx` with stress simulation flows
- Extended `web/lib/api.ts` and `web/types/index.ts` to support advanced DeFi payloads

## Scoring Model

### Opportunity Score

- 45% safety
- 30% yield quality
- 15% exit quality
- 10% confidence

### Protocol Score Inputs

- contract safety
- incident history
- market maturity
- governance and admin posture
- confidence and evidence coverage

## Next Recommended Enhancements

1. Add persistence beyond in-memory caches for historical snapshots, docs metadata, and token inheritance
2. Add scenario-aware portfolio construction views across multiple opportunities
3. Add tests for DeFi normalizers, route payloads, and score-shape regressions
4. Add deeper deployment-specific due diligence for protocol-on-chain surfaces
5. Add alerting so protocol incidents and score downgrades flow into user-facing monitoring

## Validation Completed

- Python source compilation passed for:
  - `src/defi/ai_explainer.py`
  - `src/defi/opportunity_engine.py`
  - `src/defi/intelligence_engine.py`
  - `src/api/routes/defi.py`
- TypeScript type-check passed with `npm run type-check`
- Next production build passed with `NEXT_DIST_DIR=/tmp/ai-sentinel-next-2 npm run build`
