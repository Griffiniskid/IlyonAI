# findings-C — matrix Pass A wave 1, category C (direct LP execution)

**Scope**: `docs/matrix-runs/passA-wave1/C01..C15/turn_*.txt` — 15 chains, 61 turns.
**Verdict**: FINDINGS. P0=5, P1=13, P2=5.

## P0 (BLOCKER)

### P0-C-01 — freeform fallback hallucinates full Velodrome CL execution plan (no card, no calldata)
Chain `C05_velodrome_cl`, turns 1, 3, 4. With no deterministic tool match, model emits prose execution plans for "Velodrome CL WETH-USDC (Optimism)" with numbered "Approve WETH / Approve USDC / Deposit to tight-range (±10%) / Deposit to ultra-wide-range (±150%)" steps. **±150% tick width is outside spec presets (WIDE=±25%).** `card_ids: []` on all three turns.

### P0-C-02 — freeform fallback invents Meteora→Raydium fallback with fake pool address + invented SOL price (EXPECTED_BLOCKED not honored)
Chain `C14_meteora_dlmm`, T2 and T4:
- T2 suggests "Raydium CLMM SOL-USDC pool (address `9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM`)" — that base58 is Raydium's **AMM** SOL/USDC pool id, **not a CLMM pool**. Hallucinates "current SOL price ≈ $20" with $16-$24 range.
- T4 prints a full 6-step plan with hallucinated USDC bridge addresses and ±20% range. Same fake CLMM address.
**Spec ledger says C14 T4 is the deferred Phase B Solana DLMM slot — agent must emit a blocker card, not invent a plan.**

### P0-C-03 — freeform fallback hallucinates "Approvals ready" prose with wallet-action CTAs (no card)
Chain `C05_velodrome_cl` T4 final: `Approvals ready: - Approve WETH for Velodrome CL (0.05 ETH, unlimited) - Approve USDC for Velodrome CL (100 USDC, unlimited)`. Indistinguishable from a real plan card.

### P0-C-04 — allocation execution_plan steps have verb/asset/calldata mismatch
- C07_balancer_wsteth_weth T2: Step 1 "Stake 200 ETH → STETH · lido" has `transaction: null`. Steps 4-5 verbs say "Supply USDC to WEETH·aave-v3" and "Supply USDC to WBTC·aave-v3"; both transactions are **identical** USDC→Aave V3 Pool approves. Verb declares supplying WBTC/WEETH; calldata only approves USDC.
- C10_aave_alt_token T3: Step 5 "Supply 200 USDC → DAI · aave-v3" — calldata approves Polygon USDC to Aave V3 Pool. Verb says DAI.
- C10_aave_alt_token T3: Step 2 "Supply 200 USDC → ? · morpho-blue" — literal `"?"` symbol target survives into execution_plan.

### P0-C-05 — "approve step 1 to begin" CTA on plans whose step 1 has `transaction: null`
C07 T4, C10 T4 continuation turns say *"Open the execution plan card above and approve step 1 to begin"* but step 1 in both cards has `transaction: null` (Lido stake / morpho RE7WPOL). User clicks sign → wallet has nothing to sign.

## P1 (HIGH)

- **P1-C-01** V3 deposit cards show degenerate same-token pair (BNB/WETH on C12 PancakeSwap; WETH/WETH on C04 Slipstream) until rebuild. Initial draft mimics a real card shape.
- **P1-C-02** `range_preset` user override silently ignored on initial draft (C04, C12, C15).
- **P1-C-03** C12 Pancake V3 range_block token0/token1 symbol⇄address INVERTED (WBNB labeled with USDT addr, USDT labeled with WBNB addr). Calldata uses correct addresses; user-facing display is wrong.
- **P1-C-04** Allocation card vs prose table vs split-amount narrative 3-way contradiction (C05/C06/C09/C11).
- **P1-C-05** Allocation footnote "X of 5 cannot be signed" contradicts source `executable` flags (C08, C09 T3).
- **P1-C-06** Uniswap V4 pool listed as `executable: true` deterministic with no V4 hook attestation (C06, C08).
- **P1-C-07** Search misses user-named target protocol; routes silently (C07 returns 0 Balancer; C11 returns Morpho instead of Compound).
- **P1-C-08** Same-token / placeholder pool items routed through as `executable: true` (C08 orca-dex USDT-USDT; C10 morpho-blue empty-symbol "Unknown").
- **P1-C-09** Adapter passes DefiLlama UUID into Raydium SDK (C15 T3 — UUID instead of base58 pool address).
- **P1-C-10** Aerodrome Slipstream rebuild reports `liquidity: "0"` for active WETH/USDC 0.05% pool on Base (C04 T4).
- **P1-C-11** TOOL_TIMEOUT on first two Aave-Optimism builds (C01 T1: 45.025s, T2: 50.952s).
- **P1-C-12** `chain: "mainnet"` rendered in allocation/execution_plan rows (mezo on C09 T3) — unsupported-chain bleed-through.
- **P1-C-13** V4-style allocation step has `pool_id: null` while marketing `deterministic` adapter — downstream signer cannot reattach to source pool.

## P2

- **P2-C-01** C01 T3+T4 freeform "I can't confirm" instead of rehydrating T1/T2 valid intent.
- **P2-C-02** C02 T1 emits `weth9-wrap` as pool_link card pointing at DefiLlama — request was for native ETH wrap on Arbitrum (wrong card type).
- **P2-C-03** C02 T2 user typed `weth9-wrap ETH` (which T1 returned) and got pool_not_found. Card name minted by T1 isn't a valid handle for T2's resolver.
- **P2-C-04** Parser cosmetic: C01 T5, C13 T4 thoughts redundant `"extra": {"action": "supply"/"stake"}`.
- **P2-C-05** C03/C04/C12 V3 cards mint NFT to dummy wallet `0xaaaa…aaaa` with "Save the returned tokenId" risk_warning — acceptable for guest but card should flag wallet-not-connected explicitly.

## EXPECTED_BLOCKED status

- C14_meteora_dlmm T4 — **NOT honored**. Phase B deferral surfaced as invented Raydium-CLMM execution plan instead of blocker card (see P0-C-02).

## What works (regression baseline — keep)

- **C03 T4** clean Uniswap V3 WETH/USDC 0.05% mint on Base — correct NPM `0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1`, correct pool, tick spacing 10, presets exactly match spec, range -10/+10 applied, slippage_bps 50.
- **C04 T4** clean Aerodrome Slipstream WETH/USDC mint on Base — correct NPM `0x827922686190790b37229fd06084350E74485b72`, tick spacing 50. Only `liquidity: "0"` wrong.
- **C12 T4** PancakeSwap V3 BSC mint — calldata addresses correct (only card-level symbol/address display inverted).
- **C13 T1/T2/T4** clean Lido stake — correct stETH `0xae7ab9…`, selector `0xa1903eab` (submit), value matches ETH wei.
- **C13 T3** VERB_NOT_SUPPORTED guard fires correctly with full recovery surface.
- **C15 T1/T2** Raydium CLMM emits `prep_swap` step with real Solana Jupiter tx + correct Phase B deferral.

## Summary
- Chains reviewed: 15
- P0: 5
- P1: 13
- P2: 5
- Verdict: **FINDINGS** — freeform-invents-LP-plan + verb/asset/calldata desync are the dominant P0 themes.
