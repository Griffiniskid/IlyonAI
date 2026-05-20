# Matrix Pass A — Wave 4 — Category C findings

`SUMMARY: CLOSED=4 STILL=12 MUTATED=3 NEW=3 P0_REMAINING=4 P1_REMAINING=11`

## CLOSED (4)
- P0-C-03 (Approvals-ready prose CTA): cosmetic shell only; no fabricated calldata anymore.
- N-C-03 (scratchpad bleed): verified clean across C05/C07/C13/C14/C15. CHOKEPOINT held in C.
- P2-C-03/P2-C-05 (handle resolver / NFT mint): test-wallet carve-out.
- P2-C-01 (C01 generic refusal): now substantive answers + verb asks.

## MUTATED (3)

### P1-C-08 → **P0-C-W4-01** — PancakeSwap V3 token0/token1 ADDRESS↔SYMBOL inversion in signable calldata
C12 T4 `range_block.pair`: `token0.symbol="WBNB"` paired with `address=0x55d398...` (which IS USDT on BSC). `token1.symbol="USDT"` paired with `0xbb4cdb...` (which IS WBNB). Pool `0x36696169c63e42cd08ce11f5deebbcebae652050` is the real USDT/WBNB pool but on-chain ordering is the inverse. Step 5 deposit_lp calldata has tokens in inverted order — mint will revert at best, wrong-side position at worst.
Severity: P1→P0 (real signable calldata reaches user with addresses not matching labeled symbols).
Fix: PancakeSwap V3 adapter must read token0/token1 from `IUniswapV3Pool.token0()/.token1()` not symbol→address map.

### P0-C-02 MUTATED — Meteora DLMM/Raydium clean at T1/T2, regresses at T4
C14 T4 still hallucinates Raydium address `9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM` + fake $20 SOL price + invented 5-step plan with ±20%.
Fix: freeform LP planner must reject Raydium/Meteora CLMM + numeric amount regardless of conversation history.

### N-C-01 MUTATED — `enso-shortcut-fallback executable:true` for unverified protocols
C05 T2 maple, ethena-usde, spark-savings, sparklend, ondo, usual-usd0 all `adapter_id:"enso-shortcut-fallback" executable:true` while footer admits "4 of 5 cannot be signed automatically".
Fix: when `adapter_id endswith "-fallback"`, force `executable:false`.

## STILL (12)

P0-C-01 (Velodrome CL freeform ±200%), P0-C-04 (verb/asset/calldata desync — C07 T2/T4 rocket-pool RETH labeled "Supply USDC", C09 T3 mezo chain="mainnet", C10 T3 empty-symbol "?" target, C08 T2 single-sided USDC into 2-asset LP), P1-C-01..03 (degenerate V3 drafts ETH/WETH self-paired), P1-C-04 (range_preset:"narrow" ignored — becomes balanced ±10%), P1-C-05 (alloc 3-way contradiction $1000/$200×5/100 DAI), P1-C-06 (chain pivot dropped on rebuild), P1-C-07 (empty-symbol pools accepted as "?"), P1-C-09 (pool_id:null in every step), P1-C-10 (top_k drift "5 of 8"), N-C-04 (Raydium CLMM accepts arbitrary verb), N-C-05 (Raydium prep_swap fixed gas + identical serialized blob prefix).

## NEW (3)

### N-C-W4-01 (P2) — Velodrome CL "Approvals are already in place" without verification
C05 T1/T3/T4 assert approvals set without prior approval tx in conversation.
Fix: freeform planner must not assert wallet/approval state without Sentinel tool observation.

### N-C-W4-02 (P1) — Plan-cache replay surfaces dispatchable card under "Continuing from prior plan"
C07/C09/C10/C13 T4 re-emit cached cards (some broken) without re-validation.
Fix: re-validate cached plans against current adapter manifest, not just replay JSON.

### N-C-W4-03 (P1) — Allocation reasoning prose contradicts card numerics
C10 T3 prose says "100 DAI" while card says `$1,000` while steps say `$200 USDC each`. Three units, three totals.
Fix: alloc-prose generator must template from card payload, not free LLM text.

## Verdict
4 closed, 12 still, 3 mutated, 3 new. CoT chokepoint HELD in C-category. Drain-guards untested (no withdraw turns). **Headline regression**: P1-C-08 mutated to P0-C-W4-01 — PancakeSwap V3 now generates signable calldata with token0/token1 address↔symbol swap.
