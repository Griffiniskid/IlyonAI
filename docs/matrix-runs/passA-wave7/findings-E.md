# Matrix Pass A — Wave 7 — Category E findings

`SUMMARY: CLOSED=8 STILL=8 MUTATED=2 NEW=4 P0_REMAINING=7 P1_REMAINING=4`

## CLOSED (8)
- **E01 t2/t3/t4 state-machine narration** — canonical refusal fires.
- **E03 t3, E04 t3, E07 t3, E08 t3** freeform fallback (new regexes hit).
- **E09 t2** clean.
- **BUG-E-017 aave-v3 cross-chain** — planner now stamps `extra.source_chain` for some protocols.

## STILL (8)
### P0
- **BUG-E-001 Pattern A** — 5 turns: E02 t1, E07 t1/t2, E10 t1/t4. Parser drops "via deBridge"; routes bridge protocol as supply target.
- **BUG-E-003 composed plan status=ready with bridge tx=null** — E07 t4. COMPOSED_PLAN_INCOMPLETE_TX normalizer not deployed.
- **BUG-E-004 freeform residual** — 3 turns: E03 t2 (LI.FI how-to), E03 t4, E13 t3 (`**Bridge route:**` with U+202F).
- **BUG-E-017 expanded** — STILL on 4 turns: E09 t1/t3/t4 (morpho-blue), E13 t1 (numeric-amount aave-v3). Protocol-fastpath stamps source_chain for SOME protocols not all.
- **NEW-2 wave-6 NBSP normalize on E02 t2** — STILL. Unicode normalize didn't deploy on this code path; ` ` survives.
- **NEW-2 wave-6 on E13 t3** — STILL. `**Bridge route:**` markdown-bold + `deBridge DLN` leaks.

### P1
- **BUG-E-008 mock balance 190.132 USDC** — STILL on E05/E09/E14 (EXPANDED).
- **BUG-E-015 junk Uniswap V4 pools executable:true** — STILL.

## MUTATED (2)
- **BUG-E-017** — partial: aave-v3 stamps source_chain; morpho-blue + numeric-amount don't.
- **BUG-E-004** — partial close (4 of 7 turns); 3 freeform shapes evade.

## NEW (4)
- **NEW-1 (P0) `build_yield_execution_plan` TOOL_TIMEOUT 45s on 6 turns** — E04 t1/t4, E05 t2, E12 t1/t4, E13 t4 all 45044-45147 ms. Same-chain builds that completed <100ms in wave-6 now hit SLO. **Wave-7 regression.**
- **NEW-2 (P0) E10 t2 EMPTY content** — `content:""`, 0 cards, 21307ms freeform fallback. Blank assistant message.
- **NEW-3 (P0) E06 t1 raw curl error in SSE stream** — `curl: (28) Operation timed out after 90007 milliseconds with 335 bytes received` appears as raw stderr in SSE without structured `event:error` envelope.
- **NEW-4 (P1) E07 t4 step description embeds "slippage band 25-50 bps"** — sanitizer scans final.content only, not `payload.steps[].description`.

## Highest-impact wave-8 moves
1. Fix Unicode normalize on sanitizer pre-pass (NEW-2 from wave-6 regressed). Closes E02 t2/t4 + E13 t3.
2. Generalize source_chain stamping for ALL protocols (morpho-blue, debridge-dln, weth9-wrap).
3. Deploy COMPOSED_PLAN_INCOMPLETE_TX normalizer.
4. Diagnose & roll back 45s timeout regression — 6 turns affected.
5. Add LI.FI how-to regex.
6. Sanitizer over `payload.steps[].description`.
7. Empty-content guard in freeform fallback.
8. SSE handler catches upstream curl timeout.
