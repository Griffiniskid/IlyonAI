# findings-G — matrix Pass A wave 2, category G (resume / rebuild / alt-pool)

**Scope**: 10 chains, 40 turns. **Baseline**: wave 1 (4 P0 + 6 P1 + 3 P2).
**Verdict**: REGRESSION + carryover. CLOSED=2, STILL=10, NEW=6.

## CLOSED (2)

- **C-G-01** — P1-G-01 partial close: G07 T4 cleanly rehydrates `plan_7be2fa982bf2` byte-identical to wave 1 (resume rail healthy). Cannot fully verify mint-path because T1 times out.
- **C-G-02** — G10 T4 session-resume still byte-identical (baseline holds). Still wraps the P0-G-04 wrong-chain plan.

## STILL (10)

- **STILL-G-01** P0-G-01 rebuild-after-amount-change still mints new plan_id (T3→T4 identical inputs still mint fresh plan).
- **STILL-G-02** P0-G-03 freeform fallback still invents plan/step state with no card (G08 — now WIDER: 3 turns instead of 2; T2 added "Step 2 is confirmed" phantom).
- **STILL-G-03** P0-G-04 wallet-swap continuation still ignores chain switch (G10 T3/T4 still chain_id=1 despite T2 switch to Base).
- **STILL-G-04** P1-G-03 session-resume after blocked plan goes silent (G03 T2-T4 degraded boilerplate; no rehydrate, no resume CTA).
- **STILL-G-05** P1-G-05 $1,000 placeholder vs $100 user-request — wave 2 WORSE: 3 sources disagree (card $1,000/1562.5%, prose $100/1082.4%, footer admits $1,000).
- **STILL-G-06** P1-G-06 post-block continuation rehydrates card but tells user to retype.
- **STILL-G-07** P1-G-02 post-cancel re-request untestable in wave 2.
- **STILL-G-08** P2-G-01 G01 TOOL_TIMEOUT + no retry CTA.
- **STILL-G-09** P2-G-02 G02 T4 TOOL_TIMEOUT (now expanded to T1 also).
- **STILL-G-10** P2-G-03 parser cosmetic redundant `extra.action.supply`.

## NEW (6)

### N-G-01 (P0/NEW) — build_yield_execution_plan TOOL_TIMEOUT regression (7 of 40 turns)

7 turns now hit 45s timeout where wave 1 had 1. Affected: G01 T1, **G02 T1 (was 74ms)**, **G03 T1 (was clean)**, **G05 T1 (was clean)**, G07 T1 (was clean plan), **G09 T4 (was clean plan)**, **G10 T1 (was clean)**.

Sanitizer correctly surfaces canonical TOOL_TIMEOUT message (BUG-M01 working — no fake cards leak, card_ids=[]). But underlying tool is collapsing. Dominant new finding; cascades into every resume/rebuild test downstream.

**Cross-cutting with E (7 turns), D (8+ turns), F (F06 t1 regression).** Suspected cause: RPC/Enso/DefiLlama/aggregator latency in test environment.

### N-G-02 (P1/NEW) — G02 T4 emits "card frame was not persisted" boilerplate
New string: "the card frame was not persisted in this session and can't be replayed directly". Honest admission of state-loss, but still UX regression — system should rehydrate or offer one-click rebuild CTA, not ask user to retype.

### N-G-03 (P1/NEW) — G06 T2 freeform prose truncated mid-string
Final ends `"...deposit of **$100\n\n_⚠ 4 of 5 ..."` — drops at "$100" with no closing **, no period. Template formatter bug.

### N-G-04 (P1/NEW) — G06 T2 allocation card APY vs prose APY divergence
Card `blended_apy="~1562.5%"`; prose says ~1082.4%. ~30% disagreement inside same response. Adds 3rd source-of-truth divergence on top of STILL-G-05.

### N-G-05 (P2/NEW informational) — G06 T1 emits pool_link instead of execution_plan_v3 for Spark Savings vault
Notice: "Direct execution from chat is currently disabled for this pool type because single-token Enso routing was silently depositing the wrong asset for many pools." Deliberate safety improvement.

### N-G-06 (P2/NEW informational) — G09 T2 cancel reply slimmed down to "Cancelled. What would you like to do next?" — baseline improvement.

## What works (baseline holds)

- G05 T2 INSUFFICIENT_BALANCE blocker clean shape (BUG-M02 normalizer holding).
- G04 T1 alt-pool recovery: 8 real pools surfaced correctly.
- G05 T2/T3/T4 valid execution_plan_v3 cards with calldata.
- G07 T4 rehydration proves resume rail works when it engages.
- G10 T3/T4 byte-identical resume (wrong chain notwithstanding).
- BUG-M01 sanitizer: all 7 TOOL_TIMEOUT occurrences emit canonical message; no fake cards leak.

## Summary
- CLOSED: 2
- STILL: 10
- NEW: 6 (1 P0 timeout-regression, 3 P1, 2 informational)
- EXPECTED_BLOCKED: 1 (G04 T1 — wave-2 different intent than wave 1)

**Verdict**: REGRESSION. TOOL_TIMEOUT plague (N-G-01) is dominant new signal and masks resume tests. Wave-1 P0s on state-loss/chain-switch/freeform-invents-state were never targeted by BUG-M01/M02/normalizer and all persist (some widened). In-scope fixes (BUG-M01, BUG-M02) are doing their job cleanly.
