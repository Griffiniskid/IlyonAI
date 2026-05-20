# Matrix Pass A — Wave 5 — Category G findings

`SUMMARY: CLOSED=4 STILL=6 MUTATED=0 NEW=0 P0_REMAINING=2 P1_REMAINING=3`

## CLOSED (4)
- **STILL-W4-G-02 G08 T2 freeform structured header hallucination** — `_FREEFORM_TX_STATE_HALLUCINATION_RE` working across all 10 G scenarios. Zero `**Protocol · Verb** —` patterns in any freeform turn.
- **MUTATED-W4-G-04 TOOL_TIMEOUT regression** — zero TOOL_TIMEOUT, zero ok:false, zero error envelopes. Wave-4 6/40 first-call build failures gone. Latency persists (19-30s) but builds succeed. Downgrade P0 → P2-latency cosmetic.
- **STILL-G-05 three-source divergence** — not re-exercised, stays CLOSED.
- **STILL-G-08 raw JSON tail** — zero hits.

## STILL (6)

### STILL-W4-G-01 rebuild remints plan_id (P0)
G05 T3 `plan_0d477c2cccb6` vs T4 `plan_1a4f7fb5d832` (byte-identical calldata). G07 T1 `plan_6f890f92f576` vs T4 `plan_ea2a955af887` (same).
Fix: `_make_plan_id` deterministic on `(wallet, chain, protocol, action, asset_in, amount_in)`.

### STILL-W4-G-03 chain-switch continuation ignored (P0)
G10 T2 user says "switch to Base" → freeform-only prose; T3 re-parses `chain_id:1` ethereum; T4 rehydrates ethereum plan.
Fix: inject `chain=<chain>` into next turn's tool-arg defaults via session state.

### STILL-W4-G-06 fallback-to-X mis-routes to wide allocation (P1, MUTATED safer)
G06 T2 user says "fallback to Aave V3 on Base" → wide search returns HIGH-risk pools (morpho ADPUSDC 5359%, pharaoh, tonco) blended 1562.5%. T4 now says `BLOCKER_NOT_RESOLVED` instead of byte-identical re-emission (improvement).
Fix: detect "fallback to <protocol> on <chain>" → route to `build_yield_execution_plan(protocol=<protocol>, chain=<chain>)`.

### STILL-W4-G-07 no card rehydrate on freeform turns (P1)
Pure freeform turns never rehydrate prior plan card.

### STILL-W4-G-10 parser echoes redundant `extra.action.supply` (P2)

### NEW-W4-G-B fresh DefiLlama query on pick-alt intent (P1)
G04 T1 apy 8.2434 vs T3 fresh search apy 9.69492 — values differ → not cache reuse.

## Verdict
Wave-5 commit cleanly closed two targeted regex-level hallucination chokepoints (structured header + JSON tail) AND incidentally closed TOOL_TIMEOUT failure regression. 4 of 11 findings closed. 6 STILL items are state-management bugs explicitly excluded from wave-5 scope.

Severity-weighted: wave-4 P0=4 → wave-5 P0=2 (50% reduction); P1=3 → P1=3 unchanged.
