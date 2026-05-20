# findings-C — matrix Pass A wave 2, category C (direct LP execution)

**Scope**: 15 chains, 60 turns (2 infra timeouts ignored). **Baseline**: wave 1 (5 P0 + 13 P1 + 5 P2).
**Verdict**: FINDINGS — partial fix-wave success.
**Active counts wave 2**: P0=4 · P1=14 · P2=4. **CLOSED=3, STILL=17 (incl. 2 partial), NEW=2**.

## CLOSED (3)

- **P0-C-05** "approve step 1 to begin" CTA on null-tx step 1 — gone (continuations now correctly say "BLOCKER_NOT_RESOLVED").
- **P1-C-11** TOOL_TIMEOUT on Aave builds (C01) — gone. C01 T1=14.5s, T2=61ms, T4=13s, T5=12s.
- **P2-C-02** C02 weth9-wrap pool_link — now emits proper `execution_plan_v3` with WETH9 wrap + WrappedTokenGatewayV3 native deposit.

## PARTIAL CLOSE (2)

- **P0-C-02** — C14 T4 (spec Phase B blocker slot) now emits proper blocker (CLOSED at T4). C14 T2 still hallucinates fake Raydium CLMM pool address (STILL at T2).
- **P2-C-01** — C01 T3 now rehydrates T2 blocked plan in plain English. C01 T4 still degrades to generic refusal.

## STILL (17)

- P0-C-01 freeform fallback invents Velodrome plan (C05 — wider now: ±200% width vs wave-1 ±150%)
- P0-C-02 PARTIAL (C14 T2 still hallucinates)
- P0-C-03 "Approvals ready" prose CTAs no card (C05 T4)
- P0-C-04 verb/asset/calldata mismatch persists (C05 T2 / C09 T3 / C10 T3 incl. literal `?` asset)
- P1-C-01..P1-C-10, P1-C-12, P1-C-13 (degenerate V3 pairs, range_preset ignored, C12 token0/token1 inverted, allocation/prose contradictions, footer wrong, V4 hook attestation missing, search misses target, empty-symbol pools, Raydium SDK UUID misuse, Slipstream liquidity=0, mezo chain="mainnet", pool_id:null)
- P2-C-03, P2-C-04, P2-C-05 (handle resolver, parser cosmetic, V3 NFT mint to dummy wallet)

## NEW (2)

- **N-C-01 (P1)** `enso-shortcut-fallback` rows marked `executable: true` despite "No verified adapter — research only" flag (C05 T2 positions 2-5).
- **N-C-02 (P1)** CTA prose says "approve step 1" but step 1 action is `swap` (no separate ERC-20 approve). Affects C03 T4, C04 T4, C12 T4.

## What works (baseline holds)

- C01 T1/T2/T5 Aave V3 supply Optimism with correct selectors + INSUFFICIENT_BALANCE blocker.
- C02 T1 NEW WTG3 native-ETH plan with selector `0x474cf53d`, value 0.05 ETH.
- C03 T4 Uniswap V3 mint Base + C04 T4 Slipstream Base mint correct.
- C12 T4 PancakeSwap V3 BSC calldata correct (only display inverted).
- C13 Lido VERB_NOT_SUPPORTED recovery surface.
- C14 T4 NEW BASELINE: proper Phase B Solana DLMM blocker.
- C15 T1 Raydium CLMM `prep_swap` with real Solana Jupiter tx.

## EXPECTED_BLOCKED

- C14 T4 NOW HONORED. C14 T2 invented-plan hole persists.

## Verdict

FINDINGS — fixes landed for null-tx-step CTA, C14 T4 invented plan, C02 weth9-wrap pool_link, Aave build timeouts. Dominant remaining themes: freeform-invents-LP-plan (C05 Velodrome + C14 T2 Meteora→Raydium), verb/asset/calldata desync, allocation-card pathology cluster.
