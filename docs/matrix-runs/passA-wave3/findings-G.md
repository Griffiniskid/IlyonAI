# findings-G — matrix Pass A wave 3, category G (resume / rebuild / alt-pool)

**Scope**: 10 chains, 40 turns. **Baseline**: wave 2 (4 P0 + 9 P1; TOOL_TIMEOUT regression 7/40).
**Wave 3 fix**: err_envelope normalizer (general).
**Verdict**: PARTIAL RECOVERY. CLOSED=4, STILL=8, NEW=1, EXPECTED_BLOCKED=1.

## CLOSED (4)

- **CLOSED-G-01** (was N-G-01 P0) — build_yield_execution_plan TOOL_TIMEOUT regression FULLY RECOVERED. Wave 2 had 7/40 turns at 45s timeout; wave 3 has **0/40**. Confirms wave-2 infrastructure-transient hypothesis.
- **CLOSED-G-02** (was STILL-G-04 / P1-G-03) — session-resume rehydrate now works. G02 T4 re-emits saved execution_plan_v3 byte-identical. Same rail confirmed on G07 T4 + G10 T4.
- **CLOSED-G-03** (was N-G-02) — G02 T4 no longer emits "card frame was not persisted" boilerplate; replaced by clean rehydrate.
- **CLOSED-G-04** (was N-G-03) — G06 T2 truncation fixed. Wave 2 ended mid-string; wave 3 ends cleanly.

## STILL (8)

- **STILL-G-01** (P0-G-01) — rebuild-after-amount-change still mints fresh plan_id. G05 T3→T4 identical 50 USDC → different plan_ids.
- **STILL-G-02** (P0-G-03) — freeform fallback still invents plan/step state with no card. G08 T3+T4 emit Aave V3 Supply summary with card_ids=[]; T4 = exact duplicate of T3.
- **STILL-G-03** (P0-G-04) — wallet-swap continuation still ignores chain switch. G10 T2 says switch to Base; T3 re-parses ethereum; T4 rehydrates ethereum plan.
- **STILL-G-05** (P1-G-05 + N-G-04 fused) — G06 T2 three-source divergence reproduced bit-for-bit: card $1,000/1562.5% vs prose $100/1082.4% vs footer admits $1,000.
- **STILL-G-06** (P1-G-06) — post-block continuation: no one-click rebuild CTA. G06 T3 says "Let me know if you'd like me to generate that plan instead"; T4 re-runs spark-savings rather than honoring T3 Aave fallback.
- **STILL-G-07** ("no card rehydrate on freeform") — long tail (G01 T3/T4, G03 T3/T4, G04 T2/T4, G07 T2/T3, G08 T2/T3/T4, G09 T2) never rehydrate earlier card. Rehydrate only fires on explicit-continue verb.
- **STILL-G-08** (P2 escalated) — degenerate final.content. G01 T3 emits raw JSON tail leaked as prose; G03 T3 emits `"}"` single brace. Was masked by TOOL_TIMEOUT in wave 2; now visible.
- **STILL-G-10** (P2-G-03) — parser still echoes redundant `extra.action.supply`.

## NEW (1)

- **N-G-07 (P2/NEW)** — Freeform fallback prose generator produces JSON-string fragments as final.content when prior turn parsed direct yield args + current turn is freeform follow-up. Suspected Sentinel-prompt artifact when history contains JSON-shaped tool args.

## EXPECTED_BLOCKED (1)

- G04 T2 — canonical refusal fallback.

## What works (baseline holds)

- G05 T2 INSUFFICIENT_BALANCE clean (BUG-M02 normalizer holds).
- G02/G07/G10 T4 rehydrate byte-identical.
- G09 T2 cancel ack clean (7.7s).
- G09 T4 post-cancel rebuild successful — P1-G-02 now PASSING.
- G04 alt-pool reuse + fresh search.
- Spark-Savings pool_link safety notice in place.
- err_envelope normalizer no regression on G paths.

## Verdict

PARTIAL RECOVERY. TOOL_TIMEOUT plague fully gone; explicit-continue resume rail now byte-identical on G02/G07/G10. Wave-1 P0 bugs (rebuild remints, freeform invents state, wallet-swap ignores chain) never targeted by err_envelope fix and persist verbatim. STILL-G-08 raw-JSON leak in final.content newly observable without being masked by timeouts.
