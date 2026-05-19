# findings-G — matrix Pass A wave 1, category G (resume / rebuild / alt-pool)

**Scope**: `docs/matrix-runs/passA-wave1/G01..G10/turn_*.txt` — 10 chains, 40 turns.
**Verdict**: FINDINGS. Dominant theme = state-loss across multi-turn resume.

## P0 (BLOCKER)

### P0-G-01 — rebuild-after-amount-change mints NEW plan_id (state-loss)
Chain `G05_rebuild_after_amount_change`. Same chain+protocol+action+asset across 4 turns, only `amount_in` changes:
- T1 100 USDC → `plan_a836d948f8c5`
- T2 200 USDC → `plan_ac0c306328b9`
- T3 50 USDC → `plan_3fe22e0b0228`
- T4 50 USDC → `plan_852d0ccd87c6`

Spec requires in-place update (preserve plan_id, regen calldata + amounts). Client-side state keyed off plan_id is silently dropped.

### P0-G-02 — alt-pool recovery surfaces but `alternatives=[]` and no `defi_opportunities` card
Chain `G03_session_resume` turn 2. ADAPTER_BUILD_FAILED for `MORE` token. Plan card has `recovery.posture="Pool unavailable — surfacing alternatives"`, `recovery.cta` set, but `recovery.alternatives=[]`, no companion `defi_opportunities` card. User can only hit "Leave funds in wallet".

### P0-G-03 — freeform fallback invents plan/step state with no card
Chain `G08_slippage_breach`:
- T3 final: `"Aave V3 · Supply — Asset: USDC, Amount: 99.8 USDC (post-bridge), Network: Optimism..."` — NO `execution_plan_v3` card, empty `card_ids`, invented slippage-adjusted amount.
- T4 final: `"Step 2 is confirmed: it supplies the bridged ≈ 99.8 USDC into Aave V3 on Optimism. You can now sign step 1..."` — phantom "confirmed" status.

Same class as the freeform-invents-calldata P0. Forbidden by spec contract. Sanitizer should refuse.

### P0-G-04 — wallet-swap continuation ignores chain switch (signs on wrong chain)
Chain `G10_walletswap_continuation`. T2 user requests switch to Base (chain_id 8453). T3 supply goes through but `chain="ethereum"` / `chain_id=1`. T4 correctly rehydrates the T3 plan_id `plan_6ee3ea32c6a4` (good!), but the plan is on the wrong network.

## P1 (HIGH)

### P1-G-01 — retry-after-RPC mints new plan_id
Chain `G07_retry_after_rpc`. T1 `plan_b6cc284dc434` vs T4 `plan_7be2fa982bf2` for identical request. Weaker form of P0-G-01.

### P1-G-02 — post-cancel re-request mints new plan_id
Chain `G09_user_initiated_cancel`. T1 `plan_983c71bfafd6` → cancel → T4 identical request `plan_bb8f2df09cc2`. Cancelled plan should be resumable or marked `superseded` with back-reference.

### P1-G-03 — session-resume after blocked plan goes silent
Chain `G03_session_resume`. T1 emits clean plan `plan_b84c250126d5`. T2 blocks on MORE. T3+T4 degrade to generic "I can't confirm that action..." boilerplate — no rehydrate of T1's still-valid USDC plan, no "resume previous plan" CTA.

### P1-G-04 — G04 T1 missed expected blocker codes (structured surface)
Chain `G04_pick_alt_pool_after_blocker` T1. EXPECTED = UNSUPPORTED_ADAPTER + ADAPTER_BUILD_FAILED on `NonExistentVault`. Observed: no `blockers[]` codes on cards; freeform text mentions the rejection but the structured `blocker_codes` surface that automation depends on is missing. (Alt-pool surfacing DID work for the *real* pools — that's the good news.)

### P1-G-05 — $1,000 placeholder vs $100 user request (10x divergence)
Chain `G06_post_block_continuation` T2. Allocation card `total_usd="$1,000"` with `$200 × 5` positions; final-message prose says "deposit of $100 USDC"; footer admits placeholder. Two sources of truth disagree 10x.

### P1-G-06 — post-block continuation re-emits identical pool_link
Chain `G06_post_block_continuation` T4. Same Spark-Savings vault `pool_link` as T1 with new card_id but identical payload. No state advancement, no acknowledgement of re-emission.

## P2 (MEDIUM)

- **P2-G-01** — G01 T1 TOOL_TIMEOUT (45.26s on `build_yield_execution_plan`); T2-T4 degrade to freeform with no "retry build" CTA or plan stub.
- **P2-G-02** — G02 T4 TOOL_TIMEOUT (45.009s) on a request identical to T1 which succeeded in 74ms. Upstream flakiness leaking into SLO; no cached plan fallback.
- **P2-G-03** — Parser cosmetic: turn-4 thoughts in multiple chains show redundant `"extra": {"action": "supply"}`.

## What works (regression baseline)

- G02 T1: clean ExecutionPlanV3 for Aave V3 Supply on Optimism (risk_gate, blockers, calldata, depends_on all correct).
- G04 T1: alt-pool recovery DID surface 8 real Aave-V3 pools as `defi_opportunities` with non-empty `items` (confirms pre-Wave-1 baseline intact for the *non-MORE* class).
- G05 T2: INSUFFICIENT_BALANCE blocker correctly shaped (code, severity, detail "Need 200 USDC, wallet has 190.132 USDC", recoverable=true, CTA).
- G10 T4: session-resume of `162cbc1a-…` / `plan_6ee3ea32c6a4` is byte-identical — preserves both card_id and plan_id. Proves the resume path *can* work; bugs above are all "doesn't fire when it should".

## Summary
- Chains reviewed: 10
- Total turns: 40
- P0: 4
- P1: 6
- P2: 3
- Verdict: **FINDINGS** — state-loss + chain-switch + freeform-invents-state are the dominant themes.
