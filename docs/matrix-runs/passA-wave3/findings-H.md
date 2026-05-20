# findings-H — matrix Pass A wave 3, category H (§7 funding scenarios)

**Scope**: 15 chains, 60 turns. **Baseline**: wave 2 (7 P0 + 7 P1).
**Verdict**: FINDINGS — 2 wave-2 NEWs RECOVERED (parser + H15 infra), but wave-2 closed P0-H-07 has **re-opened in a new shape** (fabricated tx hashes / portfolio state). §7 detectors unchanged.
**Counts**: P0 STILL=7, CLOSED=0, NEW=1 · P1 STILL=5, CLOSED=2, PARTIAL=1, NEW=4.

## CLOSED from wave 2 (2 P1)

- **Chain-name-as-asset parser regression CLOSED**. H13 t1/t4 now parse `Supply 100 USDC to Aave V3 on Base` correctly to `asset_in:"USDC", chain:"base"` → real 2-step Aave plan on chain_id 8453 with spender `0xa238dd80c259a72e81d7e4664a9801593f98d1c5`. H08 also unblocked.
- **H15 wholesale infrastructure collapse CLOSED**. H15 t1 emits clean Aave-Ethereum plan, t2 returns full balance JSON, no SSE hangs, no rate_limited.

## STILL (7 P0 + 5 P1)

### P0 (7)
- P0-H-01 (H09) GAS_TOPUP_REQUIRED detector absent
- P0-H-02 (H10) LST→LP intent + prep_swap absent; t2 STILL hallucinates Lido calldata with WRONG selector 0x2e1a7d4d (= WETH.withdraw, not requestWithdrawals) + WRONG contract (stETH token, not withdrawal NFT)
- P0-H-03 (H14) V2→V3 migration not bundled
- P0-H-04 (H12) claim+compound flow absent (t2 properly refuses — improvement)
- P0-H-05 (H11) NFT LP refinance composed plan missing
- P0-H-06 (H15) wallet-kind mismatch detector absent — t1 builds Aave-Ethereum supply for Solana-wallet request with no WALLET_KIND_MISMATCH blocker
- P0-H-08 (H06) cross-chain composed plan still emits `status:"ready"` with `transaction:null` (err_envelope normalizer did not touch this)

### P1 (5)
- P1-H-01 (H07) dust-mixing untested
- P1-H-02 (H05 t2) JLP composition prose hallucinated (SOL≈45% / ETH≈20% / USDC≈15% / USDT≈10%) with no tool call
- P1-H-03 (H04) deBridge bridge misrouted as "supply" pool_link
- P1-H-04 intent-parser strips chain/wallet hints across H10/H14/H11
- P1-H-06 Follow-up turns emit prose-only "Please connect EVM wallet" instead of re-running deterministic builder
- P1-H-07 latency tail PARTIAL (H02 t1 45.05s TOOL_TIMEOUT, H07 t1 40.51s; no 90s collapses — improved vs wave 2)

## NEW (1 P0, 4 P1)

### P0-H-NEW-01 — Hallucinated transaction submission (CARDINAL ISSUE)
H02 t4 final: *"Retrying the swap execution now… **Transaction submitted:** 0x3a9f…c1e2 (Base) — Status: Pending (≈12s confirmation)"* with **ZERO tool calls** in the turn. Wave-2 P0-H-07 closure scoped to calldata/gas/fees prose; the "claim a tx hash" / "Top-up confirmed" / "no residual dust remains" variants slip through. See also H07 t2/t3 + H09 t3. **Must close before any RC** — telling user their tx is broadcast when no tool ran is the worst possible failure mode.

### P1 NEW (4)
- **P1-H-NEW-01** H08 t3 quotes wrong-chain Aave Pool spender (Ethereum 0x794a61358D6845594F94dc1DB02A252b5b4814aD for Base context; real Base spender 0xa238dd80c259a72e81d7e4664a9801593f98d1c5).
- **P1-H-NEW-02** H11 t1, H14 t1 intent-parser truncation (parsed-args debug strings cut mid-token `"stablecoin_onl."`, `"constraint_fit_then_risk_adjust."`) + inverted APY band (min_apy:0.5 > max_apy:0.48 on H11; FP residue 0.08000000000000002 on H14).
- **P1-H-NEW-03** Native-ETH V3 draft card carries placeholder ETH/WETH pair @ price 1.0. H03 t1/t2, H06 t1/t4 first-turn `pool_deposit_v3` shows pair:{ETH,WETH}, current_price:1.0, pool_address:"", no range_block. Continuation turn silently swaps in real WETH/USDC range_block, but first response is misleading.
- **P1-H-NEW-04** Cascade post-tool prose hallucinations broadened — H07 t2 "you already hold 50/50/50 USDC/USDT/DAI" (real 190/0/0), H07 t3 "no residual dust", H09 t3 "Top-up confirmed". Same root as NEW-01 but no tx hash fabricated.

## EXPECTED_BLOCKED

| Test | Wave 2 actual | Wave 3 actual |
|------|---------------|---------------|
| H07_S7 dust_mixing | NOT BLOCKED (1-sig Curve, dust untested) | NOT BLOCKED — same. MISMATCH stands. |
| H08_S8 partial_allowance | BLOCKED on BASE-parser bug | **NOT BLOCKED** (parser fixed) — builds normal 2-step approve+supply; partial-allowance detector never fires. MISMATCH still. |

## Verdict

err_envelope normalizer cleared the 2 wave-2 NEWs (parser regression + infra collapse) — clean wins. §7 per-scenario detectors (S6, S9, S10, S11, S12, S14, S15) unchanged from wave-2. Wave-2's closure of P0-H-07 (post-deterministic-timeout cascade) **regressed in a new shape**: refuse-pipe now blocks calldata/gas/fees prose but lets through (a) fabricated tx hashes (H02 t4), (b) fabricated portfolio state (H07 t2), (c) fabricated post-tx confirmations (H07 t3, H09 t3).

**Wave-4 priorities**: (a) tx-hash / portfolio-state / "confirmed" prose hallucination shields to BUG-M01's refuse-pipe; (b) chain-aware Aave Pool spender resolution; (c) parser-truncation + APY-band-validation guards; (d) ETH/WETH placeholder elimination in pool_deposit_v3 draft cards; (e) per-scenario §7 detectors for S6/S9/S10/S11/S12/S14/S15.
