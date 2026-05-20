# Matrix Pass A — Wave 6 — Category G findings

`SUMMARY: CLOSED=4 STILL=6 MUTATED=0 NEW=2 P0_REMAINING=2 P1_REMAINING=5`

## CLOSED (4)
- **STILL-W4-G-02 freeform structured header hallucination** — `**Protocol · Verb** —` absent across all 10 G scenarios.
- **MUTATED-W4-G-04 TOOL_TIMEOUT regression** — zero in-envelope timeouts.
- **STILL-G-05 three-source divergence** — stays CLOSED.
- **STILL-G-08 raw JSON tail** — zero hits.

## STILL (6)

### P0
- **STILL-W4-G-01 rebuild remints plan_id** — G05 T3 `plan_7fd64eaac09f` vs T4 `plan_fa02fcbe719e` same params byte-identical calldata. G07 T1 vs T4 same. G09 T1 vs T4 same.
- **STILL-W4-G-03 chain-switch ignored** — G10 T2 "switch to Base" → freeform; T3 re-parses `chain:"ethereum"`; T4 rehydrates eth plan.

### P1
- **STILL-W4-G-06 fallback-to-X mis-routes** — G06 T2 wide allocation with HIGH-risk pools (1562.5% blended) instead of routing to specific protocol.
- **STILL-W4-G-07 no card rehydrate on freeform turns** — pure freeform never rehydrates.
- **STILL-W4-G-10 parser echoes `extra.action.supply`** — G05/G09 T4.
- **NEW-W4-G-B fresh DefiLlama on pick-alt intent** — not re-exercised; STILL.

## NEW (2)
- **NEW-W6-G-A (P1) G04 T1 upstream curl 90s HTTP timeout** — single G turn hangs ≥90s and dies at HTTP layer.
- **NEW-W6-G-B (P1) G04 T4 freeform "Execution Plan" prose with bullet body** — uses en-dash separator + "Execution Plan" header instead of `**Protocol · Verb** —`; sanitizer regex does not match. Hallucinates gas estimates without deterministic source. `card_ids:[]`.

## Verdict
Wave-6 made zero progress on the 4 targeted state-management items (W4-G-01/-03/-06/-07). All confirmed STILL. Wave-5 closures hold. Two NEW regressions: upstream curl timeout + sanitizer-bypass variant in G04 T4.
