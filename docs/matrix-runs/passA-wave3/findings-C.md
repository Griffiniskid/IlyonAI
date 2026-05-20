# findings-C — matrix Pass A wave 3, category C (direct LP execution)

**Scope**: 15 chains, 61 turns. **Baseline**: wave 2 (4 P0 + 14 P1).
**Verdict**: FINDINGS — partial traction. **CLOSED=2 · STILL=17 (incl 2 partial) · NEW=3.**
**Active wave 3**: P0=4 · P1=15 · P2=4.

## CLOSED (2)

- **P1-C-12** Slipstream `liquidity:"0"` — wave 3 reports real on-chain `current.liquidity` for the WETH/USDC pool with live `sqrt_price_x96`, `tick`, `tvl_usd=$18.75M`, `base_apr_pct=24.6%`. The zero is truthful on-chain reading, not a stub.
- **P2-C-04** Parser cosmetic redundant args — pairs correctly with proper card. Cosmetic only.

## PARTIAL CLOSE (2)

- **P0-C-02** — C14 T1 emits proper `UNSUPPORTED_ADAPTER` blocker (CLOSED at T1). **STILL at C14 T2 and C14 T4**: freeform hallucinates Raydium CLMM SOL-USDC address `9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM` (Raydium AMM, not CLMM) + invents 5-step workflow + fake SOL price ≈ $20.
- **P2-C-01** C01 T3 rehydrates prior blocked plan in plain English. C01 T4 still degrades to generic refusal.

## STILL (15)

- **P0-C-01** freeform invents Velodrome plan (C05 T1/T3/T4). Width still ±200% tick. No card, no calldata.
- **P0-C-02 PARTIAL** (above).
- **P0-C-03** "Approvals ready" prose CTA without execution-plan card (C05 T1/T3/T4).
- **P0-C-04** verb/asset/calldata mismatch (C09 T3 mezo `chain:"mainnet"`; C10 T3 `asset:"?"`).
- **P1-C-01..P1-C-13** (degenerate V3 pairs, range_preset ignored, C12 token0/token1 inverted, allocation/prose 3-way contradictions, V4 hook attestation missing, chain-pivot dropped on rebuild, empty-symbol pools, Raydium UUID misuse, pool_id:null universal).
- **P2-C-03, P2-C-05** (handle resolver, V3 NFT mint to dummy wallet).
- **N-C-01, N-C-02** (enso-shortcut-fallback executable:true, "approve step 1" CTA on swap action).

## NEW (3)

### N-C-03 (P0) — scratchpad bleed into user-facing final.content
- **C07 T2**: multi-paragraph internal monologue leaks into `final` event content. Quote: `"We need to decide which amount to use. The user said 'Use 0.05 ETH'… 0.05 ETH * $2100 = $105. So consistent: they want to allocate 0.05 ETH, which equals $105… Let's compute exact: $105/8 = $13.125…"`
- P0 trust/contract regression — user sees raw model reasoning. Same root as A's P0-A-W3-02 cross-category scratchpad-bleed.

### N-C-04 (P1) — Raydium CLMM accepts arbitrary `action:"supply"` verb
- C15 T2 parses `"supply 100 SOL"` → emits `Raydium CLMM Supply` plan with `prep_swap`. Unlike Lido's VERB_NOT_SUPPORTED gate, Raydium CLMM adapter accepts arbitrary verb. `pool_symbol` silently defaulted to SOL-USDC.

### N-C-05 (P1) — Raydium CLMM `prep_swap` ships fixed `gas_estimate_usd:0.01` regardless of amount
- C15 T1 (0.5 SOL prep) and T2 (50 SOL prep, 100× larger) both report 0.01 + same `duration_estimate_s:25` + same `serialized:"AQAAAAAAAAA..."` prefix. Suggests serialized blob is a stub.

## Baseline holds

- C01/C02/C03/C04/C12 Aave V3 / WTG3 native-ETH / V3 / Slipstream / PancakeSwap V3 calldata correct.
- C13 Lido stake correct; T3 VERB_NOT_SUPPORTED recovery.
- C14 T1 UNSUPPORTED_ADAPTER blocker (new in wave 3).
- C15 T1/T3 Raydium CLMM Phase-B prep_swap + clean ADAPTER_BUILD_FAILED via err_envelope normalizer.

## Verdict

Fix-wave landed on Slipstream `range_block` + err_envelope normalizer (C15 T3 surfaces ADAPTER_BUILD_FAILED cleanly, no raw SDK stack). Dominant remaining: freeform-invents-LP-plan (C05/C14 T2/T4), allocation/prose desync cluster, NEW P0 scratchpad-bleed at C07 T2.

Net: 4 P0 + 15 P1 + 4 P2 = 23 active (vs wave 2's 22).
