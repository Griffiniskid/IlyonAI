# Matrix Pass A — Wave 7 — Category D findings

`SUMMARY: CLOSED=3 STILL=15 MUTATED=2 NEW=1 P0_REMAINING=7 P1_REMAINING=8`

## CLOSED (3) — Drain guards re-verified hold
- **D-P0-NEW-WAVE5-01 Aave V3 ERC20 USDC withdraw(0)** — D02 t3 refuses cleanly.
- **D-P1-14a Yearn ERC-4626 withdraw(0)** — D07 t2.
- **D-P1-14b Aave WTG3 native withdrawETH(0)** — D09 t2.

## STILL (15)
### P0
- **D-P0-10b Balancer exit_pool → READY 3-step joinPool DEPOSIT** — D05 t1 "Exit Balancer wsteth-weth with 0.5 BPT" → `execute_pool_position(pool:"balancer-wsteth-weth ", asset_in:"ETH", amount:0.05)`. Title literally says "Balancer V3 Deposit LP" for an EXIT request. **Wave-7 verb-guard NOT live on this path** — the verb extractor lowered "Exit" to a deposit intent BEFORE tool dispatch. No `verb_inverted` err_envelope. **CRITICAL still P0.**
- **D-P0-NEW-WAVE5-02 execution_plan_v2 phantom ready+null-tx+wrong chain_id** — D11 t3/t4 STILL.
- **D-P0-03 claim/remove_liquidity verb router** — D03 t2, D04 t4, D06 t3 freeform.
- **D-P0-04 slug + chain_id validator** — D05 t1 trailing space, D11 t3 EVM chain_id for Solana, D12 t3 trailing dash.
- **D-P0-05 DAG balance preflight** — D09 t1 false-blocks WETH; D09 t3 borrow no HF check.
- **D-P0-06 adapter-error inner-paren leak** — D14 t1 `_bn` JS error; D15 t3 raw kamino account-list.
- **D-P0-07 unstake/close_position verb router** — D01/D11/D13/D14 freeform.
- **D-P0-09 kamino/meteora withdraw mislabeled "deposit"** — D15 t3 error template wrong.

### P1
- **D-P1-01/-13 requires_signature:false** on signable Stake.
- **D-P1-06..10 Enso timeout cluster** — D05 t3 49.3s, D13 t4 78s.
- **D-P1-15 Step 0 indexing**.
- **D-P1-16 close_position rejected with generic invalid_amount**.
- **D-P1-17 D04 v2 remove-liquidity titled "Supply"**.

## MUTATED (2)
- **D-P0-06 adapter-error sanitizer** — wrap added but inner-paren still leaks.
- **D-P1-11b continuation re-emit** — STILL re-leaks across 4+ protocols (D03/D05/D11/D15 t4).

## NEW (1)
- **D-NEW-WAVE7-01 (P0) `execute_pool_position` accepts space-padded slug + verb-inverts to deposit** — failure mode of the wave-7 fix itself. Guard placed on wrong tool path.

## Verdict
Drain guards 3/3 HOLD. But the wave-7 advertised CRITICAL fix (Balancer P0-10b) did NOT land on live dispatch path. ExecutionPlanV2 phantom + continuation re-emit + sanitizer inner-paren + verb routers all unchanged.

Top wave-8 priorities:
1. **D-P0-10b** — install verb-guard at intent extractor level (where `extra.action` is set), not at tool level. The dispatcher silently rewrites "Exit" to "supply" before tool selection.
2. **D-P0-NEW-WAVE5-02** ExecutionPlanV2 phantom-ready guard.
3. **D-P1-11b** continuation re-emit sanitization.
4. **D-P0-06** sanitizer nested-paren strip.
5. **D-P0-03/-07** verb router for claim/remove_liquidity/unstake/close_position.
