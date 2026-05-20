# findings-A — matrix Pass A wave 3, category A (research+filter+execute)

**Scope**: 20 chains, 82 turns. **Baseline**: wave 2 (2 P0 + 7 P1).
**Verdict**: FINDINGS. **2 CLOSED · 7 STILL · 1 REGRESSED · 2 NEW.**

**Fix verification**: 0 lowercase blocker codes anywhere; all canonical UPPER_SNAKE (INSUFFICIENT_BALANCE, GAS_TOPUP_REQUIRED, VERB_NOT_SUPPORTED, AMOUNT_NOT_CONFIRMED). Zero in-band TOOL_TIMEOUT envelopes. **2 NEW outer-transport curl 90s timeouts** surfaced.

## Wave 2 → Wave 3 disposition

| Wave 2 finding | Status | Evidence |
|---|---|---|
| P0-A-W2-01 A11 t2 WrappedTokenGatewayV3 WETH-balance lockout + double-count | **STILL** | A11 t1 identical: `assets_required:{"WETH":"0.1","ETH":"0.1"}` + INSUFFICIENT_BALANCE "Not enough WETH" + native-ETH gateway calldata 0x474cf53d w/ msg.value 0.1 ETH |
| P0-A-W2-02 Allocation t3 scratchpad leak | **STILL + WORSE in A05** | A05 t3 = ~1.5kB CoT dump; A06/A09 t3 cleaner than wave 2 (mixed) |
| P1-A-W2-01 GAS_TOPUP 70 MATIC=$6.30 | **STILL** | A10 t3+t4: 70.16 MATIC, MATIC@$0.09 implied (~233× off) |
| P1-A-W2-02 weth9-wrap link_only | **STILL + BROADER** | A11/A15/A16/A17/A18 — 10 turns × 5 chains |
| P1-A-W2-03 Truncated final.content | **STILL** | A01 t3 (`aave-v`), A06 t3 (` 124.5%`), A08 t3 (` keeping risk`) |
| P1-A-W2-04 A05 t3 allocation inconsistencies | **STILL** | mezo `chain:"mainnet"`, blended_apy 54.7% (card) vs 40.5% (final), 20%×5 vs 12.5%×8 |
| P1-A-W2-05 execute_pool_position defaults supply for LST | **CLOSED** | A19 t4 (marinade), A20 t4 (jito) now emit VERB_NOT_SUPPORTED + recovery buttons |
| P1-A-W2-06 Frax intent re-routed to weth9-wrap | **STILL** | A16 t3/t4: protocol="weth9-wrap" on Frax stake |
| P1-A-W2-07 Rocket Pool stake calldata targets rETH ERC-20 | **CLOSED (not-a-bug)** | Hand-verified: selector 0xa3e0464d on rETH = RocketTokenRETH.deposit() payable; RP v1.5+ design — intentional |

## P0 (2 — both carry-over)

- **P0-A-W3-01** A11 t1 WTG3 native-ETH path blocks on WETH balance + double-counts assets (same as wave 2 — emits wrap-step AND gateway both with msg.value 0.1 ETH; gateway wraps internally; user with 0.1 ETH locked out)
- **P0-A-W3-02** Scratchpad leak — A05 t3 worst (~1.5kB CoT including "DEFAULT to EVEN split", "The instruction", arithmetic worksheet, meta-commentary on renderer)

## P1 (7)

- P1-A-W3-01 GAS_TOPUP math wrong (A10)
- P1-A-W3-02 Final.content truncation (A01/A06/A08 t3)
- P1-A-W3-03 weth9-wrap link_only broader (10 turns × 5 chains)
- P1-A-W3-04 A05 t3 allocation inconsistencies
- **P1-A-W3-05 [REGRESSED]** A02 t5 Renzo despite Lido filter. Wave 2 marked CLOSED; wave 3 t5 now BUILDS `Renzo Stake` execution_plan_v3 with full calldata for 0.5 ETH at `0x74a09653a083691711cf8215a6ab074bb4e99ef5` (ezETH minter), status:"ready", zero refusal, filter not enforced.
- P1-A-W3-06 A07 t1 Spark DAI search returns unrelated high-risk pools (saturn 124.5%, gmtrade XAU-USDC 161.7%, uniswap-v4 RAVE-USDT 888.5%)
- P1-A-W3-07 A15 t1/t2 narrated fake-plan resurfaces — freeform "Your Swell Supply draft for 0.05 ETH is ready" with card_ids:[] + zero calldata. Wave-1 P1-A-07 (A19 t3) was CLOSED wave 2; re-emerged on Swell. Sentinel guard rail leaks on fallback.

## NEW (2)

- **NEW-A-W3-01** HTTP-level 90s curl timeouts on allocation turns. A02 t3 + A09 t3 die with `curl: (28) Operation timed out after 90001 milliseconds`. SSE never emits `event: done`. Outer-transport timeout (NOT in-band TOOL_TIMEOUT envelope — sanitizer fix holds). Allocation card-building >90s when reusing 7-8 prior-turn pools with full Sentinel decoration.
- **NEW-A-W3-02** Stablecoin classifier false positives at risk_level:LOW. A03 t1 returns Mainstreet MSUSD, Apyx APXUSD, Re REUSD, fx-protocol FXUSDSTABILITYPOOLV2.0, falcon-finance SUSDF — none are widely-held stablecoins; most are <180-day-live protocol-specific pseudo-stables flagged Unaudited yet surfaced as "low-risk stablecoin".

## Summary
- Chains: 20, Turns: 82
- Wave-2 disposition: 2 CLOSED, 7 STILL, 1 REGRESSED (Lido-filter routing)
- Wave-3 P0: 2 carry-over
- Wave-3 P1: 7 (5 carry-over, 1 regression, 1 narrated-fake)
- Wave-3 NEW: 2 (HTTP 90s timeout on allocation; stablecoin classifier false-positives)
- Verdict: **FINDINGS** — sanitizer fix verified (0 lowercase blocker codes, 0 in-band TOOL_TIMEOUT). Both wave-2 P0s unmoved; need targeted fixes (Aave native-ETH WTG3 double-count; final-renderer scratchpad-strip).
