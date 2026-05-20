# Matrix Pass A — Wave 5 — Category C findings

`SUMMARY: CLOSED=2 STILL=11 MUTATED=2 NEW=3 P0_REMAINING=4 P1_REMAINING=9`

## CLOSED (2)
- **N-C-03 scratchpad bleed inside C-category** — body-scan CHOKEPOINT holds (except over-scrub bug N-C-W5-01).
- **P0-C-03 Approvals-ready CTA with fabricated calldata** — `card_ids:[]` everywhere; risk downgraded to P1 prose-only (but P0-C-01 re-elevates same prose to P0).

## STILL (11)

### P0
- **P0-C-01 Velodrome CL "Approvals are already in place"** — C05 T1/T3/T4 all assert approvals set without observation. Guard misses exact "Approvals (for|are) X already (set|in place)" phrasing.
- **P0-C-W4-01 PancakeSwap V3 token0/token1 ADDRESS↔SYMBOL inversion in signable calldata** — C12 T4 still ships wrong-side mint to real BSC mainnet (token0.symbol="WBNB" with USDT address; mint calldata inverted).
- **P0-C-04 verb/asset/calldata desync** — C07 T2 rocket-pool RETH labeled "Supply USDC"; C09 T3 mezo `chain:"mainnet"`; C10 T3 `target:"? · morpho-blue"`; C08 T2 single-sided USDC into 2-asset LP.
- **P0-C-02 MUTATED Meteora/Raydium freeform** — C14 T2 "Here's the ready-to-go plan for adding 1 SOL + 100 USDC to Raydium CLMM SOL-USDC pool (address `9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM`)" + ±20% range + fake $20/SOL price.

### P1
- **P1-C-01..03 degenerate V3 drafts** — C12 ETH/WETH and BNB/WETH self-paired with empty pool_address.
- **P1-C-04 range_preset "narrow" ignored** — C12 narrow always becomes `balanced ±10%`.
- **P1-C-09 pool_id:null in every alloc step** — C07/C09/C10 all carry null pool_id.
- **P1-C-10 top_k drift "5 of 8"** — claims diversification across 8 venues while emitting 5.
- **N-C-04/N-C-05 Raydium CLMM arbitrary verb + fixed-gas + identical serialized blob prefix** — C15 T1+T2 both serialize identical 320-char tx prefix regardless of amount.

## MUTATED (2)

### N-C-W4-02 (P1) — Plan-cache replay surfaces dispatchable card
C07/C09/C10/C13/C14/C15 T4 all open with "Continuing from the prior allocation/execution plan" and re-emit broken card from prior turn before refusing with `BLOCKER_NOT_RESOLVED`. C13 escapes (Lido fresh rebuild).
Fix: re-validate cached plans against current adapter manifest, not replay JSON.

### N-C-01 MUTATED (P1) — `*-fallback` adapters still `executable:true`
C05 T2 6 pools with `adapter_id:"enso-shortcut-fallback","executable":true` while footer says "4 of 5 cannot be signed". C08 T2 `gmtrade` Solana pools `adapter_id:"solana-yield-builder-fallback","executable":true`. 41 wave-5 turn files contain `*-fallback` adapter rows with `executable:true`.
Fix: `if adapter_id.endswith("-fallback"): executable = False`.

## NEW wave-5 (3)

### N-C-W5-01 (P0) — C14 T4 truncated JSON corruption from over-aggressive body-scan
Final.content: `", ], \"usd_total\": 66251.68}, , ], \"usd_total\": 0.29}, , ], \"usd_total\": 14.05}, ], \"total_usd\": 66268.97}"` — wallet balance JSON had its heads scrubbed, leaving only commas + closing brackets. The body-scan over-matched on JSON object keys.
Fix: body-scan must either anchor on `{` and consume to balanced `}`, or fall through to refusal if scrub yields invalid prose.

### N-C-W5-02 (P1) — `*-fallback` executable:true (covered in MUTATED above).

### N-C-W5-03 (P1) — C10 T3 unit-soup persists
Allocation card `total_usd:"$1,000"` + prose `"amounts sum to 100 DAI"` + steps `$200 USDC each` — three units, three totals, contradictory.
Fix: alloc-prose generator must template from card payload, not free LLM text.

## Verdict
CoT chokepoint HELD in C-category bodies. Wave-5 fixes did NOT close the Velodrome "Approvals are already in place" pattern. PancakeSwap V3 token0/token1 inversion (P0-C-W4-01) unchanged and still produces signable wrong-side mint calldata on BSC mainnet.

**Headline regression**: N-C-W5-01 — body scrubber over-matches JSON wallet payload and leaks malformed strings into final output. P0.
