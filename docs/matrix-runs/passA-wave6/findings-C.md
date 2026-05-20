# Matrix Pass A — Wave 6 — Category C findings

`SUMMARY: CLOSED=2 STILL=7 MUTATED=2 NEW=4 P0_REMAINING=3 P1_REMAINING=7`

## CLOSED (2)
- **P0-C-01 Velodrome "Approvals are already in place"** — zero hits across all 60 wave-6 turn files. Pattern guard held.
- **N-C-W5-01 C14 T4 truncated JSON over-scrub** — wallet JSON intact, body-scan no longer over-matches.

## STILL (7)

### P0
- **P0-C-W4-01 PancakeSwap V3 token0/token1 ADDRESS↔SYMBOL inversion** — C12 T4 still ships wrong-side mint calldata to BSC mainnet (token0="WBNB" with USDT address; token1="USDT" with WBNB address).
- **P0-C-04 verb/asset/calldata desync** — C07 T2 rocket-pool RETH labeled "Supply USDC"; C08 T2 4× "Supply USDC" into 2-asset LP; C09 T3 mezo chain="mainnet"; C10 T3 `target:"? · morpho-blue"`; C06 T4 single-sided USDC into LP pair.
- **P0-C-02 MUTATED Raydium freeform** — C14 T4 invents pool address `9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM` + fake $20/SOL price + fake Phantom-approval step (Solana SPL doesn't use ERC20-style approvals).

### P1
- **P1-C-01..03 degenerate V3 self-paired drafts** — C03/C04/C12 T1 still ship ETH/WETH, WETH/WETH, BNB/WETH self-pairs with empty pool_address.
- **P1-C-04 range_preset "narrow" ignored** — C12 T2 + C15 T2 still emit `balanced ±10%`.
- **P1-C-09 pool_id:null in every alloc step**.
- **N-C-01 / N-C-W5-02 *-fallback adapters still executable:true** — 44 wave-6 turn files; C05 T2, C08 T1+T2 instances confirmed.

## MUTATED (2)
- **N-C-W4-02 Plan-cache replay surfaces dispatchable card** — C05/C07/C08/C09/C15 T4 still re-emit broken cards.
- **P0-C-02 Raydium MUTATED** (also under STILL P0 above).

## NEW (4)
- **N-C-W6-01 (P1) C06 T2 90s outer-transport timeout** — C-category previously immune; now regressed.
- **N-C-W6-02 (P0) C10 T3 false footer "3 of 5 cannot be signed"** — all 5 alloc rows have `executable:true` deterministic; footer hard-coded stale count.
- **N-C-W6-03 (P2) C10 T3 stray "a" char in markdown table** — incomplete template fragment.
- **N-C-W6-04 (P1) C15 T1 usd_equivalent:1.0 for 1 SOL** — SOL≠$1 cached value could mislead downstream USD risk gate.

## Verdict
Velodrome approvals pattern and JSON over-scrub both CLOSED. PancakeSwap V3 inversion (P0-C-W4-01) confirmed STILL on BSC mainnet calldata. Raydium freeform now invents both pool address AND fabricated Phantom-approval step that contradicts Solana's SPL token model. NEW N-C-W6-02 reveals ungated UI-imperative pass missed footer-count templating.
