# Matrix Pass A — Wave 4 — Category A findings

`SUMMARY: CLOSED=0 STILL=8 MUTATED=2 NEW=4 P0_REMAINING=3 P1_REMAINING=12`

## Wave-3 → Wave-4 disposition

### A11 t2 — WTG3 native-ETH double-count (STILL, P0)
Reproduces unchanged. `assets_required:{"WETH":"0.1","ETH":"0.1"}` + INSUFFICIENT_BALANCE "Not enough WETH" + WTG3 calldata `0x474cf53d…` with `msg.value 0x16345785d8a0000` (0.1 ETH) AND a precursor wrap step with the same 0.1 ETH value. User with 0.1 ETH locked out.
Fix: yield planner WTG3 native-ETH branch must skip the WETH9 wrap precursor and recompute `assets_required` from `msg.value` only.

### A01 t3 — scratchpad leak (STILL + WORSE, P0)
Wave-4 chokepoint did not fire. A05 t3 (wave-3 worst) is CLEAN, but A01 t3 now bleeds 4 kB of worksheet after the markdown table: "DEFAULT to EVEN split", "However", "We need to", "14.284*6=85.704", "Plug w=14.284, w_h=14.296".
Root cause: `_STRATEGY_SCRATCHPAD_LEAD_RE` is lead-anchored; the leak appears AFTER the table+blended-APY paragraph.
Fix: sanitizer must scan ENTIRE final.content (not just first paragraph) for lines matching `(DEFAULT to|However we|We need to|The instruction|Let's compute|Plug w=|Compute amounts)` and truncate from there onward.

### A15 t1+t2 — narrated fake tx + escalation (STILL + WORSE, P0)
Wave-3 P1 escalated to P0. t2 now claims `"Your Swell Supply transaction for 0.05 ETH is ready. Review and sign with your wallet to execute."` with `card_ids:[]` + zero calldata.
Fix: post-final guard must refuse any content containing `\b(transaction|draft|plan)\s+for\b.*\bready\b` when no execution_plan card emitted.

### A10 t3 + t4 — GAS_TOPUP math (STILL, P1)
`Need ~70.146921 MATIC (~$6.30 at 1.5× headroom)` → implied MATIC ≈ $0.06; real ≈ $0.20-$0.25.
Fix: gas-blocker formatter for non-EVM-L1 chains must use live native-token USD oracle.

### A11/A15/A16/A17/A18 — weth9-wrap link_only fallback (STILL, P1)
Intent router for "ETH supply on chain" falls to `weth9-wrap` pool_link when no LST adapter found.
Fix: intent router for `action=supply, asset=ETH` must check protocol-specific LST registry first.

### A07 t1 — Spark DAI search returns unrelated pools (STILL, P1)
Tool call has empty `chains:[], product_types:[], risk_levels:[]` — search parser drops "Spark"/"DAI" tokens entirely.
Fix: extract protocol-name + asset-symbol tokens and inject as filters.

### A03 t1 — stablecoin classifier false-positives (STILL, P1)
mainstreet MSUSD, apyx APXUSD, re REUSD, fx FXUSDSTABILITYPOOLV2.0, falcon SUSDF all flagged `risk_level:"LOW"` + `stablecoin_only:true`.
Fix: stablecoin allowlist + force `risk_level≥MEDIUM` for non-allowlisted pseudo-stables.

### A05 t4 + A09 t3 — outer-transport 90s curl timeouts (STILL, P1)
Allocation Sentinel-decoration step exceeds 90s on reused 7-8 prior-turn pools.
Fix: allocation pipeline parallel decoration with per-pool timeout budget.

### A02 t3 / A05 t3 inconsistencies (MUTATED, P1)
Scratchpad component CLOSED on A05 t3; mezo `chain:"mainnet"` persists, "8 pools / 3 chains" wording vs 5 positions × 4 chains.
Fix: chain-name canonicalizer + reasoning template must consume actual positions[].length + chains[].

### A01/A06/A08 t3 — final.content templated text mismatch (MUTATED, P1)
Hard truncation resolved; A06 t3 says "12.5% across eight protocols" while table shows 5 × 20%. A08 t3 says "$31.25 position" while table shows $50.
Fix: reasoning-generator must pull weight/$amount/pool-count from allocation card payload.

## NEW (4)

### NEW-A-W4-01 — A02 t3 Lido adapter visibility lost between cards (P1)
Pool card has `executable:true, adapter_id:"evm-lst-direct-mint"`; same-turn allocation card flags Lido `"No verified adapter — research only"`.
Fix: allocation builder must reuse `executable`/`adapter_id` from freshly emitted defi_opportunities card.

### NEW-A-W4-02 — A02 t4 `get_staking_options` ignores chain filter (P1)
`chains:["ethereum"]` returns 7/8 Solana+Arbitrum pools.
Fix: apply `chains` allowlist before TVL/APY ranking.

### NEW-A-W4-03 — A06/A08 t3 reasoning hardcoded for 8 pools when alloc has 5 (P1)
Blended APY also disagrees: A06 card 139.2% vs final 124.3%; A08 card 168.7% vs final 188.3%.
Fix: reasoning gen must use card's actual positions/blended_apy.

### NEW-A-W4-04 — A18 Kelp lacks LST adapter, routes to weth9-wrap link_only (P1)
Kelp `LRTDepositPool` at `0x036676389e48133b63a802f8635ad39e752d375d` should be wired similarly to ether.fi adapter.
Fix: LST/LRT adapter registry — add Kelp entry.
