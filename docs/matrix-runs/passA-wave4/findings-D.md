# Matrix Pass A — Wave 4 — Category D findings

`SUMMARY: CLOSED=3 STILL=10 MUTATED=1 NEW=3 P0_REMAINING=8 P1_REMAINING=12`

## CLOSED (3)

### D-P1-14a CLOSED — Yearn ERC-4626 withdraw(0) drain
D07 t2 evidence: tool args `{action:"withdraw",amount_in:0}` now returns `blocked` with text "ERC-4626 withdraw: amount_in must be > 0. To withdraw entire position, pass extra.withdraw_all=true (description will say 'Withdraw ALL' + calldata uses MAX_UINT256)." No `0xb460af94 ffff…ffff` calldata emitted.

### D-P1-14b CLOSED — Aave WTG3 withdrawETH(0) drain
D09 t2: blocker text "Aave V3 native withdraw via WTG3: amount_in must be > 0…" No drain calldata.

### D-P0-08 PARTIAL CLOSED — Borrow verb router (D08 t1)
D08 t1 "borrow 0.05 ETH" → `action=borrow`, built 2-step plan with WTG3 `approveDelegation` + `borrowETH(0x66514c97…)` calldata. D08 t2-t4 matrix scenario diverged to SUPPLY USDT/USDC — REPAY verb still untested.

## MUTATED (1)

### D-P1-11 → D-P1-11b MUTATED — Continuation re-emit now leaks blocker text
D03/D11/D15 t4: continuation re-emits prior `execution_plan_v3` card payload PLUS "BLOCKER_NOT_RESOLVED" boilerplate. D15 t4 re-prints full kamino `obligation/lendingMarket/lendingMarketAuthority/reserve/reserveSourceColl` leak — doubles exposure.
Fix: gate `_continue_from_prior_plan` to strip `blocker.detail` or render generic "previous plan unresolved" without re-emitting card payload.

## STILL (10)

- D-P0-02 close_position: parser learned verb but adapter still gates on positive amount.
- D-P0-03 claim/remove_liquidity verb router missing.
- D-P0-04 slug validator missing (weth9-wrap accepted, "via-secondary-market-on-jupiter chain_id=1", "orca-usdc-" trailing dash).
- D-P0-05 DAG-walk balance preflight missing (wrap-then-supply false-blocks).
- D-P0-06 adapter-build error wrapper (D14 raw bn.js TypeError leaks, D15 kamino account-list leaks).
- D-P0-07 unstake/liquid_unstake verb router missing (Marinade, Jito unwinds blocked).
- D-P0-09 kamino withdraw mislabeled "deposit" + raw account leak.
- D-P1-15 Step 0 indexing.
- D-P1-01 / D-P1-13 requires_signature:false on signable Stake/Supply.
- D-P1-06..10 timeout cluster (8 turns × 45s on Enso calls).

## NEW (3)

### D-P0-10 NEW — Balancer exit_pool → action=deposit_lp (drain-equivalent)
D05 t2: prompt is Balancer exit-pool; intent extractor emits `action:"deposit_lp"`. Would have deposited $0.50 instead of withdrawing if Enso hadn't timed out.
Fix: intent extractor's Balancer verb table must map `exit_pool|withdraw_lp|remove_lp → action=withdraw_lp`.

### D-P1-16 NEW — close_position adapter rejects amount=0 with generic invalid_amount
D01 t3: parsed correctly as `{action:"close_position", extra:{token_id:12345}}` but tool returns text-only `"invalid_amount: amount_in must be a positive decimal value"` — bypasses blocker card entirely.
Fix: validator must whitelist `action in {close_position, claim, harvest}` from positive-amount precondition.

### D-P1-17 NEW — D04 v2 remove-liquidity routes to pool_link titled "Supply"
Pool_link card titled "Pancakeswap-V2 · Supply" for a REMOVE request.
Fix: render `"… · Remove Liquidity"` linking to `/remove-liquidity`.

## Verdict
3 closed (both drain-paths held, borrow partial), 1 mutated (continuation re-leak worse), 3 new (1 P0 drain-equivalent, 2 P1). Net wave-3 → wave-4: P0 9 → 8, P1 flat.

Top wave-5 priorities for D:
1. D-P0-10 Balancer exit→deposit inversion (drain-equiv)
2. D-P0-06 + D-P0-09 public-error sanitizer + kamino label
3. D-P1-11b continuation re-leak gate
4. D-P0-02 / -03 close/claim/remove_liquidity router
5. D-P0-07 unstake/liquid_unstake router
6. D-P0-04 slug validator
7. D-P0-05 + D-P1-15 DAG preflight + step indexing
8. D-P1-06..10 Enso retry/SLO
