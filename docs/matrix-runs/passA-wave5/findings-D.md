# Matrix Pass A — Wave 5 — Category D findings

`SUMMARY: CLOSED=2 STILL=14 MUTATED=2 NEW=2 P0_REMAINING=10 P1_REMAINING=10`

## CLOSED (2) — Held hold from wave 4
- **D-P1-14a Yearn ERC-4626 withdraw(0) drain** — D07 t2 refuses cleanly, no `0xb460af94 ffff…` calldata.
- **D-P1-14b Aave WTG3 native withdrawETH(0) drain** — D09 t2 refuses cleanly.

## **NEW wave-5 P0 — CRITICAL DRAIN REGRESSION (2)**

### **D-P0-NEW-WAVE5-01 (P0 DRAIN) — Aave V3 ERC20 USDC withdraw(0) drains entire aUSDC balance**
D02 t3 SSE: `build_yield_execution_plan{chain:"base", protocol:"aave-v3", action:"withdraw", asset_in:"USDC", amount_in:0}` → `status:"ready"`, `signatures_required:1`, single step `action:"withdraw"`, transaction:
- `to: 0xa238dd80c259a72e81d7e4664a9801593f98d1c5` (Aave V3 Pool, Base)
- `data: 0x69328dec 000000…833589fcd...02913 ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff 000000…aaaaaaaa…aaaa`
- `Pool.withdraw(asset=USDC, amount=MAX_UINT256, to=user)` — drains entire aUSDC balance for a "Withdraw 0 USDC" summary.

D02 t4 SSE: identical card re-emitted via continuation handler (compounds D-P1-11b).

**Wave-4 drain-guards only covered Yearn ERC-4626 and Aave V3 native WTG3 — the Aave V3 ERC20 standard `pool.withdraw` path is UNGUARDED.** Same drain class wave-4 thought was closed; same regression as D-P1-14a/b but on a third adapter.

Fix pointer: extend `_validate_amount_in_positive` guard from yearn/aave-wtg3 adapters to the Aave V3 ERC20 `pool.withdraw` adapter. Same error message pattern: require `extra.withdraw_all=true` to mint MAX_UINT256 calldata; reject `amount_in==0` with blocker.

### **D-P0-10b MUTATED (WORSE) — Balancer exit_pool now emits READY DEPOSIT plan**
D05 t1 SSE: prompt is Balancer wstETH-WETH EXIT, intent extractor emits `action: deposit_lp`, adapter builds READY 3-step plan: wrap ETH→WETH + approve Vault + `joinPool(0x32296969ef14eb0c6d29669c550d4a044913023000020000…)` Balancer V2 Vault calldata for 0.05 ETH.

Wave-4 had this fail safe (Enso timeout). Wave-5 succeeds → user deposits when they meant to withdraw. **Drain-equivalent severity uplift.**

Fix pointer: intent_extractor's Balancer verb table must map `{exit_pool, withdraw_lp, remove_lp, redeem_bpt} → action=withdraw_lp`. Reject `execute_pool_position` when prompt contains exit/withdraw/remove keywords.

### D-P0-NEW-WAVE5-02 (P0) — execution_plan_v2 emits status:"ready" with no transaction body
D11 t3 SSE: `card_type:"execution_plan_v2", steps:[{action:"stake", params:{protocol:"via-secondary-market-on-jupiter", chain_id:1, amount:"0.5"}, status:"ready"}], requires_signature_count:1` — `transaction` key absent. Wallet would attempt to sign undefined.

Fix pointer: ExecutionPlanV2 serializer: if `step.transaction` is null/missing, force `status="blocked"` + `requires_signature_count=0` + emit `INCOMPLETE_TRANSACTION` blocker.

## STILL (14)

### P0
- **D-P0-03 claim/remove_liquidity verb router** — D03 t2, D06 t3, D04 t4 all hit freeform.
- **D-P0-04 slug + chain_id validator** — D05 t1 trailing-space pool `"balancer-wsteth-weth "` builds READY 3-step joinPool; D11 t3 `via-secondary-market-on-jupiter chain_id=1`; D12 t3 `orca-usdc-` trailing dash.
- **D-P0-05 DAG balance preflight** — D09 t1 false-blocks WETH despite Step 0 wrap; D08 t1 borrow reaches ready without HF check (supply path PARTIAL CLOSED).
- **D-P0-06 adapter-build error wrapper** — D14 t3 raw bn.js TypeError; D15 t3 raw kamino account list leak.
- **D-P0-07 unstake/liquid_unstake verb router** — D10 t2 mSOL, D11 t2 jitoSOL, D13 t2 Raydium CLMM close all freeform-only.
- **D-P0-09 kamino withdraw mislabeled "deposit"** — D15 t3 blocker says "deposit could not be built" for WITHDRAW request.

### P1
- **D-P1-01 / D-P1-13 requires_signature:false on signable Stake/Supply** — D10/D11 t1.
- **D-P1-06..10 Enso timeout cluster** — 9 turns ≥20s elapsed, several >45s.
- **D-P1-11b continuation re-emit re-leaks blocker.detail** — D02/D03/D06/D07/D15 t4 all re-emit full payload including drain-instructions / internal account lists. Now applies to 4+ protocols.
- **D-P1-15 Step 0 indexing** — D05 t1 has steps `[0,1,2]`; D09 t1 has `[0,1]`.
- **D-P1-16 close_position adapter rejects amount=0 with generic invalid_amount** — D01 t3.
- **D-P1-17 D04 v2 remove-liquidity routes to pool_link titled "Supply"**.

## MUTATED (2)
- **D-P0-10 → D-P0-10b** — Balancer exit_pool now emits READY DEPOSIT (covered in NEW above).
- **D-P1-11 → D-P1-11b** — continuation re-emit re-leaks card payloads + drain instructions on more protocols.

## Verdict
**NET REGRESSION**. 2 closed (drain-guards held) but 1 NEW P0 drain (Aave V3 ERC20 withdraw(0)) + 1 MUTATED P0 (Balancer exit → READY deposit) + 1 NEW P0 (ExecutionPlanV2 phantom). P0 count wave-4 8 → wave-5 10.

Top wave-6 priorities:
1. **D-P0-NEW-WAVE5-01** Aave V3 ERC20 withdraw(0) drain — extend wave-4 guard.
2. **D-P0-10b** Balancer exit → deposit READY plan.
3. **D-P0-NEW-WAVE5-02** ExecutionPlanV2 phantom ready+null-tx.
4. **D-P1-11b** continuation re-emit must stop replaying card payloads.
5. **D-P0-06/-09** adapter-error sanitizer + correct verb in error templates.
6. **D-P0-03/-07** verb router for {claim, remove_liquidity, unstake, close_position}.
7. **D-P0-04** slug + chain_id cross-validator.
8. **D-P0-05** DAG-walk preflight.
