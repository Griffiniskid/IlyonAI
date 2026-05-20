# Matrix Pass A — Wave 6 — Category D findings

`SUMMARY: CLOSED=4 STILL=15 MUTATED=2 NEW=1 P0_REMAINING=8 P1_REMAINING=8`

## CLOSED (4) — Drain guards hold + new Aave V3 ERC20 guard

### **D-P0-NEW-WAVE5-01 Aave V3 ERC20 USDC withdraw(0) drain — CLOSED**
D02 t3: now blocks with `ADAPTER_BUILD_FAILED` "Aave V3 withdraw: amount_in must be > 0. To withdraw the entire aToken balance, pass extra.withdraw_all=true". No MAX_UINT256 calldata emitted. **DRAIN GUARD HOLDS.**

### **D-P1-14a Yearn ERC-4626 withdraw(0)** — STILL CLOSED
### **D-P1-14b Aave WTG3 native withdrawETH(0)** — STILL CLOSED

## STILL (15)

### P0 (CRITICAL — Balancer drain regression NOT closed)

### **D-P0-10b Balancer exit_pool → READY DEPOSIT — STILL** ⚠️
D05 t1: prompt for Balancer wstETH-WETH EXIT, intent extractor STILL emits `execute_pool_position` with `pool: "balancer-wsteth-weth "` (trailing space), adapter builds READY 3-step plan: wrap ETH→WETH + approve Vault + joinPool calldata. **Wave-6 detector dispatch reorder did NOT fix this**: the request never reaches `_detect_lifecycle_withdraw` because `execute_pool_position` tool is selected before lifecycle detectors run. Drain-equivalent. **CRITICAL still P0**.

### **D-P0-NEW-WAVE5-02 execution_plan_v2 phantom ready+null-tx — STILL**
D11 t3: `status:"ready"`, `requires_signature_count:1`, `tx_hash:null`, no `transaction` key. Also wrong `chain_id:1` (Ethereum) for JITOSOL on Solana.

### Other P0 STILL
- **D-P0-03 claim/remove_liquidity verb router** — D03 t2, D04 t4, D06 t3 freeform.
- **D-P0-04 slug + chain_id validator** — D05 t1 trailing space, D11 t3 EVM-chain-id for Solana protocol, D12 t3 trailing dash.
- **D-P0-05 DAG balance preflight** — D09 t1/t4 false-blocks WETH despite Step 0 wrap; borrow no HF check.
- **D-P0-07 unstake/close_position verb router** — D10/D11 mSOL/jitoSOL, D01/D13 close_position all freeform.
- **D-P0-09 kamino/meteora withdraw mislabeled "deposit"** — D14/D15.

### P1
- **D-P1-01/-13 requires_signature:false on signable Stake** — D10/D11/D12/D13 t1.
- **D-P1-06..10 Enso timeout cluster** — 13+ turns ≥20s, two ≥75s.
- **D-P1-15 Step 0 indexing**.
- **D-P1-16 close_position rejected with generic invalid_amount**.
- **D-P1-17 D04 v2 remove-liquidity titled "Supply"**.

## MUTATED (2)
- **D-P0-06 adapter-error sanitizer** — wrap+protocol-prefix added but inner-paren still leaks JS errors (`_bn`) and internal field names (`obligation/lendingMarketAuthority/reserveSourceColl`).
- **D-P1-11b continuation re-emit** — STILL re-leaks full transaction calldata + blocker.detail + drain instructions across 5 protocols.

## NEW (1)
- **D-NEW-WAVE6-01 (P1) execution_plan_v2 wrong chain_id for Solana** — D11 t3 chain_id=1 (Ethereum) for JITOSOL stake step.

## Verdict
**NET POSITIVE BUT MIXED**. 3 of 3 drain fixes HOLD. But Balancer P0-10b NOT closed (wave-6 targeted wrong dispatch path), ExecutionPlanV2 phantom-ready not addressed, continuation re-emit still leaks across 5 protocols. P0 wave-5 10 → wave-6 8.

Top wave-7 priorities:
1. **D-P0-10b** Balancer exit at `execute_pool_position` path (verb check at top of tool, refuse exit/withdraw/remove).
2. **D-P0-NEW-WAVE5-02** ExecutionPlanV2 phantom ready serializer guard.
3. **D-P1-11b** continuation re-emit sanitization (strip blocker.detail + step.transaction).
4. **D-P0-06** sanitizer inner-paren strip.
5. **D-P0-09** verb in error templates.
6. **D-P0-03/-07** claim/remove_liquidity/unstake router.
7. **D-P0-04** slug + chain_id cross-validator.
8. **D-P0-05** DAG preflight.
