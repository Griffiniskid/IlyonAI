# findings-E — matrix Pass A wave 1, category E (cross-chain composed plans)

**Scope**: `docs/matrix-runs/passA-wave1/E01..E15/turn_*.txt` — 15 chains × 4 turns = 60 transcripts.
**Verdict**: FINDINGS. P0=4, P1=4. **0 of 15 chains produce a fully signable cross-chain composed plan.**

## Per-chain verdict

| Chain | x-chain intent? | Composed plan? | PENDING_DST_FILL? | Real bridge calldata? | Verdict |
|---|---|---|---|---|---|
| E01 eth→base aave | NO (misrouted) | NO (pool_link link_only) | n/a | n/a | P0 routing |
| E02 eth→arb compound | NO (misrouted) | NO (pool_link link_only) | n/a | n/a | P0 routing + P0 hallucination t3 |
| E03 eth→polygon aave | YES | FAILED (composed_plan_bridge_quote_failed) | n/a | n/a | P0 bridge |
| E04 eth→opt aave usdt | NO (cross-chain dropped) | NO (single-chain dst) | n/a | n/a | P0 routing |
| E05 arb→base compound | NO (built on SRC) | NO (built supply on arbitrum) | n/a | n/a | P0 routing + P0 hallucination t2 |
| E06 base→arb yearn | NO (continuation discovery) | NO | n/a | n/a | P0 routing |
| E07 eth→base curve | YES t4 only | PARTIAL skeleton | YES (t4) | NO — transaction:null | P0 calldata + P1 totals |
| E08 eth→base balancer | YES | FAILED (composed_plan_bridge_build_failed 400) | n/a | n/a | P0 bridge + P0 hallucination t3/t4 |
| E09 eth→arb morpho | NO (cross-chain dropped) | NO | n/a | n/a | P0 routing (EXPECTED_BLOCKED note STALE) |
| E10 eth→base eth-native | NO (weth9-wrap misroute) | NO | n/a | n/a | P0 routing + P0 hallucination t2 |
| E11 eth→arb yearn weth | YES | FAILED (400) | n/a | n/a | P0 bridge (EXPECTED_BLOCKED still legit) |
| E12 eth→polygon aave usdt | NO | NO | n/a | n/a | P0 routing |
| E13 eth→polygon aave dai | NO | NO | n/a | n/a | P0 routing + P1 hallucination t3 |
| E14 eth→avax aave | NO | NO | n/a | n/a | P0 routing |
| E15 eth→arb balancer weth | YES | FAILED (400) | n/a | n/a | P0 bridge + P0 hallucination t3/t4 |

## P0 (4)

### BUG-E-001 — Cross-chain intent silently collapsed to dest-only single-chain plan
Affected: E01, E02, E04, E05, E06, E09, E10, E12, E13, E14 (10 of 15).
"supply 200 USDT to Aave V3 on Optimism (from Ethereum)" parses to `{chain: optimism, ...}` with NO `extra.source_chain`. Downstream `build_yield_execution_plan` takes the single-chain branch, emits dst-only plan with `chains_touched=["optimism"]` + INSUFFICIENT_BALANCE blocker "Bridge or swap into USDT on optimism before signing". User told to bridge out-of-band, defeating the composed-plan feature. The 5 chains that DO set `extra.source_chain` (E03, E07, E08, E11, E15) are exactly the chains that take the composed-plan branch. E05 is worst — parses arbitrum as target (the source).

### BUG-E-002 — deBridge `/create-tx` fails with `senderAddress=guest` for unconnected wallets
Affected: E03 (quote_failed), E08, E11, E15 (build_failed 400).
Composed plan builder at `src/agent/tools/build_yield_execution_plan.py:336-344` calls `bridge.create_order_encoded(sender=user_address, recipient=user_address)`. When session has no connected wallet, `user_address == "guest"` (default at `src/api/routes/agent.py:126: wallet=wallet or "guest"`) and the literal `"guest"` is passed to DLN's `senderAddress=` / `dstChainTokenOutRecipient=`. DLN rejects with HTTP 400. Error surfaced verbatim including mozilla.org docs URL.

**Fix**: Gate `create_order_encoded` on a real EVM address. If `user_address == "guest"`, build the bridge step with `transaction=null` and attach `BLOCKER_WALLET_NOT_CONNECTED` (the BUG-011 `pending.py` infrastructure already supports this).

### BUG-E-003 — E07 turn 4 composed plan has bridge `transaction:null` and broken totals
E07 turn 4 (only chain producing any composed plan output): card carries `steps[0].transaction: null` on the bridge leg, `totals.signatures_required: 0`, `totals.chains_touched: []`, `totals.assets_required: {}`. NO `COMPOSED_PLAN_INCOMPLETE_TX` blocker (builder at `build_yield_execution_plan.py:354-380` is supposed to attach this when bridge_to/bridge_data missing). Plan rendered `status: "ready"` yet nothing to sign.

### BUG-E-004 — Freeform fallback hallucinates bridge fees, slippage, UI workflows
Affected: E01 t3/t4, E02 t3/t4, E05 t2, E08 t3/t4, E10 t2, E13 t3, E15 t3/t4.
Examples:
- E02 t3: *"The slippage band for the Arbitrum Gateway bridge is set to 0.5%."* — fabricated.
- E05 t2: *"Bridge fee estimate for 200 USDC (Arbitrum → Base via deBridge DLN): Protocol fee ~0.10% → ≈0.20 USDC, Gas on Arbitrum ~0.0004 ETH → ≈0.70 USDC (≈$1,750/ETH), Total ≈0.90 USDC (≈0.45%)."* — full hallucinated fee breakdown with fake ETH price.
- E08 t3: invents Hop → Lido-on-Base → Balancer workflow (Lido does NOT deploy wstETH on Base).
- E10 t2: *"Approve ETH for the deBridge spender in your wallet"* — invents approval-of-native-ETH flow.

## P1 (4)

- **BUG-E-005** MATIC gas-topup oracle returns ~$0.09 price (real ~$0.20). E12 t1, E13 t1, E13 t4. **Same root as P1-A-04**.
- **BUG-E-006** Bridge-step fields null in E07 t4: `slippage_bps: null`, `gas_estimate_usd: null`, `duration_estimate_s: null` even though builder sets defaults. Replay path strips fields.
- **BUG-E-007** Parser drops source chain unless "from <chain>" is explicit. E04, E09, E12, E14 (likely E01, E02). Related to BUG-E-001 but isolated to parser layer.
- **BUG-E-008** Persistent `190.132 USDC` mock balance leaking across distinct chains (E05, E09, E14). Test fixture leaking — recommend `(test wallet)` suffix when wallet is `"guest"`.

## EXPECTED_BLOCKED status

| Test | Brief status | Actual |
|------|--------------|--------|
| E09 eth→arb morpho | EXPECTED_BLOCKED (Morpho Blue MetaMorpho USDC on Arb needs verified addr) | **STALE** — registry NOW has `0x7c574174DA4b2be3f705c6244B4BfA0815a8B3Ed` (Gauntlet USDC Prime) at `src/defi/execution/adapters/erc4626.py:78`. EXPECTED_BLOCKED entry should be retired. |
| E11 eth→arb yearn weth | EXPECTED_BLOCKED (Yearn yvWETH Arb needs verified addr) | Still legit — builder never reached vault resolution due to BUG-E-002. |

## AI-unavailable / TOOL_TIMEOUT: zero occurrences across all 60 turns

## Roll-up
- Chains: 15 | Turns: 60
- Fully-working composed plans: **0**
- Partial composed plan: 1 (E07)
- Cross-chain intent dropped at parser: 10
- Reaches `create_order_encoded`, fails on `"guest"`: 4
- P0: 4 (BUG-E-001..004)
- P1: 4 (BUG-E-005..008)
- EXPECTED_BLOCKED to retire: 1 (E09)
- Sentinel-principle violations (hallucinated bridge data): 8 turns / 7 chains

**Verdict**: BLOCKING for production. Single highest-impact fix: BUG-E-002 (don't shell `"guest"` to DLN) — unblocks the 4 chains that try. BUG-E-001 blocks the other 10. BUG-E-004 is the largest user-trust risk and must be gated before any external demo.
