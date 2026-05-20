# Matrix Pass A — Wave 7 — Category G findings

`SUMMARY: CLOSED=2 STILL=6 MUTATED=2 NEW=2 P0_REMAINING=2 P1_REMAINING=5`

## CLOSED (2)
- **NEW-W6-G-B G04 T4 en-dash "Execution Plan" header** — canonical refusal returned. En-dash regex landed correctly.
- Wave-5 closures held: structured `**Protocol · Verb** —` absent, three-source divergence, JSON tail.

## STILL (6)
### P0
- **STILL-W4-G-01 rebuild remints plan_id** — G05 T2/T3/T4 different plan_ids same params byte-identical calldata.
- **STILL-W4-G-03 chain-switch ignored** — G10 T2 "switch to Base" → T3 re-parses ethereum, T4 rehydrates eth plan.

### P1
- **STILL-W4-G-06 fallback-to-X mis-routes** — G06 T2 wide allocation 1562.5% blended HIGH-risk.
- **STILL-W4-G-07 no card rehydrate on pure freeform** — 8 G scenarios.
- **STILL-W4-G-10 parser echoes `extra.action.supply`** — G05/G09 T4.
- **NEW-W4-G-B fresh DefiLlama on pick-alt** — STILL.

## MUTATED (2)
### P0
- **MUTATED-W6-G-NEW-A G04 T1 upstream curl 90s → in-envelope TOOL_TIMEOUT epidemic** — Wave-6: 1 turn hung. Wave-7: 7 turns hit `ok:true → TOOL_TIMEOUT` (G01/G03/G05/G07 T1, G07 T4, G09 T1/T4, G10 T1). **Wave-7 regression: 1 → 7 user-visible failures.**

### P1
- **MUTATED-W6-G-NEW-B G09 T1 cancel-prep produces TOOL_TIMEOUT** — cancel flow now starts from error state; T2 "Cancelled. What next?" hallucinates a cancel of a phantom plan.

## NEW (2)
- **NEW-W7-G-A (P1) G03 T4 empty `content:""`** — three thoughts execute then final emits empty string. Blank message.
- **NEW-W7-G-B (P1) G07 T2 RPC-failure freeform mis-narration** — assistant says "An RPC failure is just a communication hiccup… the plan will pause at that step" with `card_ids:[]`. Hallucinated state-machine claim.

## Verdict
Wave-7 closed exactly one targeted finding (en-dash sanitizer). Four state-management P0/P1 items confirmed STILL. Wave-6 upstream curl timeout mutated into a WIDER in-envelope TOOL_TIMEOUT epidemic spanning 6 scenarios — net regression.

P0_REMAINING=2 + 1 mutated (TIMEOUT epidemic).
P1_REMAINING=5 + 1 mutated (cancel-phantom) + 2 new.
