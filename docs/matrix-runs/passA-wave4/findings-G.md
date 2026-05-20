# Matrix Pass A — Wave 4 — Category G findings

`SUMMARY: CLOSED=2 STILL=6 MUTATED=1 NEW=2 P0_REMAINING=4 P1_REMAINING=3`

## CLOSED (2)

### STILL-G-05 (three-source divergence on G06 T2) — CLOSED
Card `total_usd:"$1,000"`, prose `$1,000 across 5`, footer admits placeholder. All three sources agree.

### STILL-G-08 (raw JSON tail / brace leak) — CLOSED
G01 T3/T4 + G03 T3 clean prose; no raw JSON tail. Scratchpad-strip CHOKEPOINT + widened `_STRATEGY_SCRATCHPAD_LEAD_RE` worked here.

## STILL (6)

### STILL-W4-G-01 — rebuild-after-amount-change mints fresh plan_id (P0)
G05 T3 `plan_5bdf91afa018` → T4 `plan_08fd91ef9ac7`, byte-identical calldata. Same params, two ids.
Fix: `_make_plan_id` deterministic on `(wallet, chain, protocol, action, asset_in, amount_in)`.

### STILL-W4-G-02 — freeform fallback invents Aave V3 supply state (P0)
G08 T2 final: `**Aave V3 · Supply** — Asset: USDC — Amount: 99.8 USDC (post-bridge) — Network: Optimism — Risk: MEDIUM` with `card_ids:[]`. T3 byte-duplicate. T1 only produced a debridge-dln pool_link draft on ethereum — Aave V3 on Optimism never existed.
Fix: Sentinel freeform prompt must reject "**Protocol · Verb** —" structured summary when no execution_plan_v3 card emitted.

### STILL-W4-G-03 — wallet-swap/chain-switch continuation ignored (P0)
G10 T2 user says switch to Base; T3 re-parses ethereum; T4 rehydrates ethereum plan. Wrong-network signing risk.
Fix: when freeform turn includes "switch to <chain>", inject `chain=<chain>` into next turn's tool-arg defaults.

### STILL-W4-G-06 — post-block continuation no rebuild CTA + re-runs spark-savings (P1)
G06 T3 user says fallback to Aave V3 on Base; T4 re-parses spark-savings/ethereum, emits byte-identical pool_link from T1.
Fix: same chain/protocol carry-over + one-click rebuild button in freeform fallback.

### STILL-W4-G-07 — no card rehydrate on freeform turns (P1)
Pure freeform turns never rehydrate prior `execution_plan_v3` card. Rehydrate fires only on explicit-continue verb.
Fix: `RehydrateCardsMiddleware` should fire on any turn within active plan session.

### STILL-W4-G-10 — parser echoes redundant `extra.action.supply` (P2)

## MUTATED (1)

### MUTATED-W4-G-04 — TOOL_TIMEOUT regression (was CLOSED at wave 3) (P0)
Wave 3: `0/40`. Wave 4: **6/40** all on first explicit `Supply <amount> USDC to Aave V3 on <chain>` calls. G09 T4 specifically regresses the wave-3 P1-G-02 "post-cancel rebuild successful" win.
Fix: warm aave-v3 adapter on session start OR raise SLO for first-call OR eagerly hydrate DefiLlama pool cache.

## NEW (2)

### NEW-W4-G-A (P2) — informational, drain-guard not exercised
Supply turns don't trigger withdraw drain-guard; no regression evidence either way.

### NEW-W4-G-B (P1) — G04 T3 fresh search ignoring "pick alt pool" intent
Different APY values (T1 USDC 7.76512% vs T3 8.2434%) confirm fresh DefiLlama query not reuse.
Fix: `_reuse_pools_from_prior_turn` should match on `(protocol, chains)` tuple, not exact card_id.

## Verdict
Commit `231c299` fixes landed cleanly where targeted (STILL-G-08 chokepoint, STILL-G-05 divergence). But three wave-3 P0s never targeted persist (rebuild remint, freeform invents state, wallet-swap ignores chain) and **TOOL_TIMEOUT regressed at 6/40**. 2 wins, 1 regression, 4 P0s active.
