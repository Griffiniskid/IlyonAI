# findings-A — matrix Pass A wave 1, category A (research + filter + execute)

**Scope**: `docs/matrix-runs/passA-wave1/A01..A20/turn_*.txt` — 20 chains, 84 turns.
**Verdict**: FINDINGS.

> **Aggregator triage note (main thread)**: P0-A-03/04/05 below flag `0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa` as a placeholder address. That is the **matrix test wallet** hardcoded at `tests/harness/v4_runner.py:35` (`EVM_WALLET = "0xaaaa…aaaa"`). The plan correctly substitutes it as the recipient / onBehalfOf / referral param. **These are FALSE POSITIVES** — the reviewer wasn't told about the test-wallet convention. Real P0s are limited to P0-A-01 (chain mismatch) and P0-A-02 (3 approves, no supply).

## P0 findings

### P0-A-01 — Allocation card declares chain "op" but transaction uses Ethereum-mainnet chain_id:1 + mainnet token/router addresses
- **Chain**: A01_aave_base_usdc, turn 3
- **Spec ref**: §5 calldata-vs-chain consistency · sanitizer S{1-15} cross-chain force
- **Quote**: `"chain":"op",..."transaction":{"chain_kind":"evm","chain_id":1,"to":"0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48","data":"0x095ea7b300000000000000000000000087870bca3f3fd6335c3f4ce8392d69350b4fa4e2..."}`
- **Root cause hint**: alloc_step transaction emits Ethereum mainnet USDC + Aave V3 Pool addresses under chain_id:1 while every label says Optimism. Signing this would deposit USDC into Aave on Ethereum mainnet. Cross-chain-force sanitizer (RC6-upstream) should have rejected.

### P0-A-02 — A01 allocation emits three identical approve calldata steps with no supply step
- **Chain**: A01_aave_base_usdc, turn 3
- **Spec ref**: §5 ExecutionPlanV3 steps · approve→supply ordering
- **Quote**: Steps 3, 4, 5 all carry `"data":"0x095ea7b300000000000000000000000087870bca3f3fd6335c3f4ce8392d69350b4fa4e20000000000000000000000000000000000000000000000000000000002faf080"` despite targeting WETH/USDC/USDT pools.
- **Root cause hint**: alloc_step builder emits only the approve calldata (`0x095ea7b3`) for each pool and never emits the per-pool `supply()` call. Three "Supply" buttons would broadcast three identical approves and zero deposits — funds left as allowance, no shares minted.

### P0-A-03/04/05 — `0xaaaa...` in onBehalfOf / receiver / referral slots — **FALSE POSITIVE** (test wallet)
- Reviewer flagged A02 t5 (Renzo submit referral), A07 t4, A08 t2 (Sky deposit receiver), A10 t3/t4 (Aave supply onBehalfOf), A11 t2 (WrappedTokenGatewayV3.depositETH onBehalfOf), A12 t4.
- All hits resolve to `0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa` which IS the matrix test wallet (`tests/harness/v4_runner.py:35`). Plans correctly substitute it; sanitizer correctly does not refuse a valid hex address.
- **Dismissed.**

## P1 findings

### P1-A-01 — Final event reports TOOL_TIMEOUT (real backend hang)
- **Chains**: A01 (t1, t5), A09 (t4)
- **Spec ref**: KNOWN_BLOCKER_CODES · TOOL_TIMEOUT (real)
- **Quote**: `"content":"I couldn't complete that — **TOOL_TIMEOUT**: Tool 'build_yield_execution_plan' exceeded its 45s SLO. Upstream call (RPC / Enso / DefiLlama / aggregator) hung — no execution plan emitted.","elapsed_ms":45012`
- **Root cause hint**: `build_yield_execution_plan` for aave-v3 supply USDC on Base/Arbitrum consistently exceeds 45s SLO. Backend RPC/Enso path is the bottleneck.

### P1-A-02 — Leaked LLM scratchpad/internal reasoning shipped as user-facing final.content
- **Chain**: A06_morpho_blue, turn 3
- **Spec ref**: §4 final-output hygiene
- **Quote**: `"...We need to allocate $150 across the same pools... We must output markdown with sections... We must not promise returns... Let's compute precisely.\n\n153.7 + 144.1 = 297.8\n+167.2 = 465.0... So blended APY ≈ 121.1%... We must not include the warning about unsupported positions unless we want to add as a note after Next steps..."`
- **Root cause hint**: Final renderer concatenated the LLM thinking trace into the published `final.content` field. Significant prompt-leak / UX regression.

### P1-A-03 — Duplicated and mid-sentence-truncated allocation tables in final output
- **Chain**: A07_spark_dai, turn 4
- **Quote**: First table claims 5×$50 ($250). Second header `## Allocation` repeats with 12.5%/$31.25 weights and ends mid-row: `| 6 | Tonco · TSTON-USD₮ (\n\n_⚠ 5 of 5 positions cannot be signed automatically...`
- **Root cause hint**: Two allocation tables emitted in one final.content, second truncated.

### P1-A-04 — GAS_TOPUP_REQUIRED math: 70.573 MATIC ≠ $6.30 (off by ~5–10×)
- **Chain**: A10_aave_polygon_dai, turns 3+4
- **Spec ref**: §3 gas estimator · KNOWN_BLOCKER_CODES.GAS_TOPUP_REQUIRED
- **Quote**: `"detail":"Need ~70.573323 MATIC (~$6.30 at 1.5× headroom), wallet has 0.410000 MATIC."`
- **Root cause hint**: 70.57 MATIC at any realistic price is $20–$70. Either gas units 10× too high OR USD conversion uses stale/wrong price.

### P1-A-05 — INSUFFICIENT_BALANCE fires for WETH when route accepts native ETH
- **Chain**: A11_aave_opt_weth, turn 2
- **Quote**: `"blockers":[{"code":"INSUFFICIENT_BALANCE","title":"Not enough WETH","detail":"Need 0.1 WETH, wallet has 0 WETH."}],...,"description":"WrappedTokenGatewayV3.depositETH(...) at 0x60eE...0710. Gateway wraps 0.1 ETH and supplies to Aave V3 Pool atomically."`
- **Root cause hint**: Plan picks WrappedTokenGatewayV3.depositETH (accepts native ETH) but preflight asks for ERC-20 WETH balance. User with ETH and no WETH wrongly told to swap.

### P1-A-06 — weth9-wrap routed to `pool_link` `exec_status:link_only`
- **Chain**: A11_aave_opt_weth, turns 3+4
- **Quote**: `"protocol":"weth9-wrap","exec_status":"link_only","notice":"Weth9-Wrap V2 pool — finalize on the protocol app..."`
- **Root cause hint**: WETH9 `deposit()` is a fixed 4-byte selector with no parameters. Falling back to `link_only` pointing at defillama.com/protocol/weth9-wrap (non-existent page) is a regression.

### P1-A-07 — A19 t3: "Marinade Stake Plan" narrated in final.content but card_ids:[]
- **Chain**: A19_marinade_sol, turn 3
- **Quote**: `"content":"**Marinade Stake Plan** — Stake 1.0 SOL via Marinade on Solana.\n\n**Step**\n1. Stake 1.0 SOL on Solana via Marinade (verb: \`stake\`)...","card_ids":[],"elapsed_ms":11645,"steps":3` — preceded by "No deterministic DeFi tool matched the request; switching to contextual reasoning mode."
- **Root cause hint**: Intent classifier failed to route `stake 1 SOL on Marinade` to the solana-yield-builder-fallback adapter. LLM freeform narrated a fake "plan" but produced no signable card — exact "narrative-only execution claim" S1–S15 was built to prevent.

### P1-A-08 — A02 t5: plan routes to Renzo (ezETH) despite Lido filter from prior turns
- **Chain**: A02_steth_lido_filter, turn 5
- **Quote**: `"args":{"chain":"ethereum","protocol":"renzo","action":"stake","asset_in":"ETH","amount_in":"0.5"}` in a chat whose research card was titled "STETH / Lido filter".
- **Root cause hint**: Protocol resolver picked renzo despite user's prior turns explicitly filtering on lido/stETH.

### P1-A-09 — $1,000 placeholder allocation rendered after AMOUNT_NOT_CONFIRMED warning
- **Chain**: A02_steth_lido_filter, turn 3
- **Quote**: `"step_index":3,"content":"No amount detected in this turn — using narrative without hard $ totals."` followed by allocation card with `"total_usd":"$1,000"` and four positions at `$250` each.
- **Root cause hint**: AMOUNT_NOT_CONFIRMED guard fires in A02-t1 and A06-t4 (both correctly produce no card) but A02-t3 still emits a fully-populated card at the $1,000 placeholder.

## Summary
- Chains reviewed: 20 (A01–A20)
- Total turns: 84
- P0 (real): 2 (chain-mismatch, approves-no-supply)
- P0 (false positive, test wallet): 3 (dismissed by aggregator)
- P1: 9
- Verdict: **FINDINGS** — 2 real P0s + 9 P1s. A01 has the most concentrated badness.
