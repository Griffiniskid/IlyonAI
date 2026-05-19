# findings-H — matrix Pass A wave 1, category H (§7 funding scenarios S1-S15)

**Scope**: `docs/matrix-runs/passA-wave1/H01..H15/turn_*.txt` — 15 chains, 60 turns.
**Verdict**: FINDINGS. P0=8, P1=7.

## Per-chain verdict

| Chain | Net |
|-------|-----|
| H01_S1_same_chain_dual | OFF-SPEC — generic 5-pos cross-chain alloc, not testing S1 dual-asset same-chain |
| H02_S2_split_swap | TIMEOUT + HALLUCINATION — t1 TOOL_TIMEOUT 45s; t2-4 freeform prose w/o cards |
| H03_S3_native_eth_V3 | PASS-AFTER-FIX — t3/t4 build real ETH→USDC + ETH→WETH prep_swap + V3 mint; t1/t2 bogus empty pool_deposit_v3 |
| H04_S4_xchain_same_token | OFF-SPEC — intent misroutes to `protocol=debridge-dln` as YIELD; pool_link link_only; no composed bridge+supply |
| H05_S5_xchain_diff_token | BLOCKED + HALLUCINATION — t1 `composed_plan_bridge_build_failed` (deBridge 400, `guest` addr); t3 hallucinates Allbridge/Wormhole |
| H06_S6_xchain_native | PARTIAL — t3 composed plan but `transaction:null` on bridge leg, `signatures_required:0`, totals empty |
| H07_S7_dust_mixing | EXPECTED_BLOCKED-MISMATCH — brief says deferred but Curve 3pool multi-input plan succeeds t1+t4 |
| H08_S8_partial_allowance | EXPECTED_BLOCKED-CONFIRMED + HALLUCINATION — full-amount approve unconditionally; t3 hallucinates wrong Aave spender |
| H09_S9_gas_missing_dst | OFF-SPEC — no GAS_TOPUP_REQUIRED; deBridge misrouted as yield protocol; t2 hallucinates "$2.10 total gas top-up" |
| H10_S10_pre_deposited_LST | OFF-SPEC + HALLUCINATION — no LST→LP detection / prep_swap; t2 fake Lido `withdraw(uint256)` calldata (real v2 = `requestWithdrawals` on unstETH NFT) |
| H11_S11_NFT_LP_refinance | OFF-SPEC — t1 inverted APY band; t2-4 prose only, no decreaseLiquidity+collect+mint composed plan |
| H12_S12_claim_compound | OFF-SPEC — no claim+compound intent; no reward-token resolution |
| H13_S13_aave_supply | PASS-SLOW — Aave V3 Base supply correct; t1 elapsed 41s (tight to 45s SLO) |
| H14_S14_v2_to_v3_migrate | OFF-SPEC + HALLUCINATION — APY float glitch `0.08000000000000002`; t3/t4 prose-only V2→V3 description, no atomic bundle |
| H15_S15_wrong_wallet | OFF-SPEC + UX REGRESSION — no wrong-wallet detector; t2 dumps raw JSON `balance_report` into final markdown; `"guest"` leaks into wallet_addresses |

## P0 findings (8)

- **P0-H-01** (H09 S9): GAS_TOPUP_REQUIRED detector missing. deBridge misrouted as a yield protocol; t2 hallucinates "$2.10 total gas top-up" prose without any card.
- **P0-H-02** (H10 S10): LST→LP intent + prep_swap step never emitted. t2 hallucinates Lido calldata `to:0xae7ab9…(stETH), data:0x2e1a7d4d…c28` — WRONG selector & wrong contract (real v2 = `requestWithdrawals(uint256[],address)` on `0x889edC2eDab5f40e902b864aD4d7AdE8E412F9B1`).
- **P0-H-03** (H14 S14): V2→V3 migration never bundled atomically. t3/t4 prose-only.
- **P0-H-04** (H12 S12): claim+compound flow absent; reward-token unresolved.
- **P0-H-05** (H11 S11): NFT LP refinance composed plan missing. All turns prose-only.
- **P0-H-06** (H15 S15): wallet-kind mismatch detector absent; raw JSON `balance_report` dumped into final markdown content (UX regression); `"guest"` placeholder leaks into wallet_addresses.
- **P0-H-07** (H02 + category-wide): TOOL_TIMEOUT on Slipstream Base WETH-USDC `build_yield_execution_plan` (45.08s). After timeout, 14+ turns across the category freeform-hallucinate calldata/gas/fees. Freeform must refuse prose when prior turn was deterministic-plan-build.
- **P0-H-08** (H06 S6): cross-chain composed plan emits unsigned `transaction:null` on a bridge leg with `status:"ready"`, `signatures_required:0`, totals empty. Plan looks healthy but is unsignable.

## P1 findings (7)

- **P1-H-01** H03 t1/t2 and H06 t1/t4 emit empty `pool_deposit_v3` cards with bogus ETH/WETH pair, `pool_address:""`.
- **P1-H-02** APY parser bugs — H11 t1 `min_apy:0.5, max_apy:0.48` (inverted band, target outside), H14 t1/t2 `min_apy:0.08000000000000002` (FP precision from `0.05+0.03`).
- **P1-H-03** H01 chain name says S1 same-chain-dual but emits generic 5-pos cross-chain allocation; scenario never exercised.
- **P1-H-04** H04 confirms same root as P0-H-01 — deBridge misrouted whenever bridge+supply co-occur.
- **P1-H-05** H05 t1 composed-plan upstream fails because `guest` placeholder is sent to deBridge `senderAddress=guest&dstChainTokenOutRecipient=guest` → HTTP 400. Same `"guest"` leaks in H15 t2.
- **P1-H-06** H08 t3 hallucinates wrong Aave spender — printed `0x794a61358D6845594F94dc1DB02A252b5b4814aD` (mainnet pool) for a Base context (real Base pool `0xa238dd80c259a72e81d7e4664a9801593f98d1c5` is in t1/t2/t4 cards).
- **P1-H-07** build_yield_execution_plan latency tail uncomfortable — H13 t1 41.0s, H15 t1 40.3s; get_wallet_balance H15 t2 43.7s.

## EXPECTED_BLOCKED status

| Test | Brief status | Actual |
|------|--------------|--------|
| H07_S7 dust_mixing t1 | EXPECTED_BLOCKED (deferred) | **NOT BLOCKED — succeeded** (Curve 3pool multi-input plan built: approve×3 + add_liquidity) |
| H08_S8 partial_allowance t1 | EXPECTED_BLOCKED (deferred) | **BLOCKED — confirmed** (full-amount approve, no allowance-delta read) |

## Summary
- Chains reviewed: 15
- P0: 8
- P1: 7
- 12 of 15 §7 funding-scenario detectors are missing or misroute
- Verdict: **FINDINGS** — §7 implementation is mostly absent or misrouted. P0-H-07 freeform-hallucinate-after-timeout is the dominant pattern.
