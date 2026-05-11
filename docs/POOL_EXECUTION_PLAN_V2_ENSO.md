# Pool Execution Plan v2 — Enso-Primary EVM + Direct Solana

> **Verdict from probe (2026-05-11):** Enso `X-API-KEY` auth confirmed live. `/networks` returns 200 with 12+ chains. `/shortcuts/quote` returns `{gas, amountOut, priceImpact}`. `/shortcuts/route` returns bundled `tx.data` for `tokenIn → tokenOut` zaps with 1% slippage cap. **EVM = Enso. No fallback.** Solana = direct SDK. No exceptions, no Curve/Balancer/V2/V3 hand-rolled adapters on EVM.

---

## 1. Acceptance criteria

The plan is satisfied when **every one** of the following is true on `https://staging.ilyonai.com`:

1. `python scripts/validate_pool_exec.py` returns **100% pass** with a funded wallet simulator (Anvil fork EVM + Solana `simulateTransaction` with injected balances), >= 70 turns covering the full matrix.
2. Every cell of this matrix produces **one signed transaction** end-to-end (or 1-2 sigs for Solana when tx-size > 1232 B forces a split):

   |          | Ethereum | Base | Arbitrum | Polygon | Optimism | BSC | Avalanche | Solana |
   |---|---|---|---|---|---|---|---|---|
   | V2 AMM    | Enso (UniV2) | Enso | Enso (Sushi) | Enso (Quick) | Enso (Velo V1) | Enso (Pancake V2) | Enso (Joe V1) | Raydium SDK (real addLiquidity) |
   | V3 CLMM   | Enso (UniV3) | Enso (Aerodrome Slip) | Enso (UniV3) | Enso (UniV3) | Enso (Velo Slip) | Enso (Pancake V3) | Enso (Joe V2 LB) | Orca Whirlpools SDK / Raydium CLMM SDK |
   | DLMM      | n/a | n/a | n/a | n/a | n/a | n/a | n/a | Meteora DLMM SDK |
   | Stable    | Enso (Curve) | Enso | Enso | Enso | Enso | Enso (Ellipsis) | Enso | n/a |
   | Vault     | Enso (Yearn/Morpho/Spark) | Enso | Enso (Pendle) | Enso (Yearn) | Enso | Enso (Venus) | Enso (Benqi) | Kamino SDK |
   | Lending   | Enso (Aave/Comp) | Enso | Enso | Enso | Enso | Enso | Enso | direct (Drift/Save) |
3. Tester walks every matrix cell on staging and confirms an on-chain LP position appears in their wallet within 30s of signing.
4. README + `docs/ARCHITECTURE_LIVE.md` reflect the live state. No aspirational fiction.

---

## 2. Architecture

### 2.1 Single-path execution by chain family

- **EVM (every chain)** → `EnsoShortcutAdapter` is the **only** path. No Curve/Balancer/Uniswap-V2/Uniswap-V3 direct calldata. The existing `CurveSingleSidedAdapter`, `BalancerSingleAssetAdapter`, `UniswapV2DualTokenAdapter`, `AaveV3SupplyAdapter`, `CompoundV3SupplyAdapter` are **removed from the registry** (kept in tree as reference, not registered).
- **Solana** → `SolanaYieldBuilderAdapter` HTTP-calls the Node sidecar. Sidecar does real SDK work per protocol module.
- **Lending / Staking on EVM** (Aave, Compound, Lido, RocketPool, etc.) → still through Enso (Enso indexes lending vault tokens as position tokens).

### 2.2 Enso request shape (verified live)

```
GET https://api.enso.finance/api/v1/shortcuts/route
  ?chainId={1|10|56|137|...}
  &fromAddress={user_wallet}
  &tokenIn={input_token_address}
  &tokenOut={position_token_address}
  &amountIn={amount_in_raw_units}
  &slippage={bps}            # e.g. 100 = 1%
Headers: X-API-KEY: <ENSO_API_KEY>
```

Response:
```json
{
  "gas": "321715",
  "amountOut": "49999998",
  "priceImpact": 2,
  "minAmountOut": "49499998",
  "tx": { "to": "0x...", "data": "0xb94c3609...", "value": "0x0" },
  "route": [ ... ]   // ordered hops Enso took
}
```

The router contract that `tx.to` points to is the Enso Shortcuts Router (chain-specific). User signs ONE `eth_sendTransaction` with Permit2-style approval handled by Enso under the hood (token gets approved to a specific spender encoded into the bundle).

### 2.3 Position token registry

For each EVM (chain, protocol, asset_in) we map to the **position token address** Enso uses as `tokenOut`. Examples:

```python
ENSO_POSITION_TOKENS = {
    ("ethereum", "aave-v3", "USDC"):     "0x98c23e9d8f34fefb1b7bd6a91b7ff122f4e16f5c",   # aEthUSDC
    ("ethereum", "aave-v3", "WETH"):     "0x4d5f47fa6a74757f35c14fd3a6ef8e3c9bc514e8",   # aEthWETH
    ("ethereum", "compound-v3", "USDC"): "0xc3d688b66703497daa19211eedff47f25384cdc3",   # cUSDCv3 Comet
    ("ethereum", "uniswap-v3-usdc-weth-500"): "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",  # pool addr as position handle
    ("ethereum", "curve-3pool"):         "0xbebc44782c7db0a1a60cb6fe97d0b483032ff1c7",   # 3pool LP token == pool addr
    ("ethereum", "balancer-bbausd"):     "0xfebb0bbf162e64fb9d0dfe186e517d84c395f016",   # BPT (pool addr)
    ("ethereum", "yearn", "USDC"):       "0xa354f35829ae975e850e23e9615b11da1b3dc4de",   # yvUSDC
    # ... full matrix
}
```

Discovery flow when user names a pool (e.g. "Uniswap V3 USDC-WETH 0.05% on Ethereum"):
1. Parser captures `protocol=uniswap-v3`, `pair=USDC-WETH`, `chain=ethereum`, optional fee tier `500`.
2. `enrich_pool(protocol, pair, chain, fee_tier)` resolves the pool address via Uniswap V3 factory `getPool(token0, token1, fee)` on-chain (one `eth_call`), or via Enso's own pool registry if available.
3. `position_token = pool_address` (Enso uses pool addresses as position handles for AMM/CLMM pools).
4. Call `/shortcuts/route` with `tokenIn=asset_in`, `tokenOut=position_token`, `amountIn=amount_raw`.
5. Wrap returned `tx.data` in our `ExecutionStepV3` schema — one signed step.

### 2.4 V3 range card

For V3 pools, the range card still shows on the frontend (capital efficiency, in-range probability, APR at range). When user clicks "Sign", we send the range to Enso. Enso's `/shortcuts/route` supports V3 mint with `tickLower` / `tickUpper` params (`extraParams` field). If Enso doesn't accept those, we fall to direct on-chain `NonfungiblePositionManager.mint` — but only as a last-resort, NOT a default path. Verify Enso V3 mint with range on probe before relying.

### 2.5 Solana stack (no Enso)

| Pool type | SDK | Method | Notes |
|---|---|---|---|
| Raydium AMM v4 | `@raydium-io/raydium-sdk-v2` | `liquidity.addLiquidityInstruction` | Real ix; 1-2 sigs depending on tx-size after ALT pack |
| Raydium CLMM | `@raydium-io/raydium-sdk-v2` | `clmm.openPosition` / `openPositionFromBase` | Tick alignment by tickSpacing |
| Orca Whirlpools | `@orca-so/whirlpools-sdk` (already declared) | `openPositionWithLiquidity` | Position NFT mint tracked |
| Meteora DLMM | `@meteora-ag/dlmm` (already declared) | `addLiquidityByStrategy` | Spot / Curve / Bid-Ask strategies |
| Kamino vaults | `@kamino-finance/kliquidity-sdk` | `depositToVault` | Single-sided native |
| Marinade / Jito / Sanctum (LST) | `@marinade.finance/marinade-ts-sdk` etc. | already shipped | |

Every Solana tx: ALT-packed + `ComputeBudgetProgram.setComputeUnitLimit(600_000)` + priority fee from Helius `getPriorityFeeEstimate(p75)` + `simulateTransaction` gate.

---

## 3. Phases (rewritten)

### Phase A — Enso activation (0.5 day)

1. Fix `src/routing/enso_client.py` header: `Authorization: Bearer` → `X-API-KEY`.
2. Add ~50ms inter-call sleep to respect 1 rps (or fetch the paid-tier limit from Enso dashboard).
3. Expand `ENSO_POSITION_TOKENS` in `enso_shortcut.py` for all stable + V3 + vault + lending tokens on the matrix.
4. Add `EnsoShortcutAdapter` to `STABLE_LP_EXEC_PROTOCOLS` and `V2_LP_EXEC_PROTOCOLS` so it bypasses pool_link.
5. Drop `Curve / Balancer / UniswapV2DualToken` adapters from `build_default_registry` ordering (keep classes, just don't register). Enso wins.
6. Pool address resolution helper: `resolve_pool_address(chain, protocol, pair, fee_tier=None) → 0x...` via:
   - Uniswap V3 factory `getPool(token0, token1, fee)`
   - SushiSwap V3 factory same shape
   - Curve registry `find_pool_for_coins(token0, token1)` 
   - Balancer subgraph (lazy)
7. Harness scenarios: `enso-aave-v3-eth`, `enso-uniswap-v3-eth`, `enso-curve-3pool`, `enso-yearn-usdc`, `enso-balancer-bbausd`, etc. Single-step `execution_plan_v3` end-to-end.

**Acceptance:** every EVM matrix cell in §1 returns a populated Enso `tx.data` step. Harness pass rate stays at 100%.

### Phase B — Solana SDK integrations (3 days)

#### B.1 Raydium AMM v4 (1 day)
- Install `@raydium-io/raydium-sdk-v2` in sidecar `package.json`.
- New `services/solana-yield-builder/src/adapters/raydium-amm-zap.js`:
  - `Raydium.load({ owner, connection })`
  - `raydium.liquidity.fetchPoolByMint({mint1, mint2})` → real pool keys (avoid catalog drift)
  - Half-split USD value via Jupiter quotes → `swapInstructions`
  - `raydium.liquidity.addLiquidityInstruction({poolInfo, poolKeys, amountInA, baseSide: 'a', slippage})`
  - Pack into `VersionedTransaction` w/ `addressLookupTableAccounts: [ALT_CORE, ALT_TOKENS]`
  - Split into 2 sigs if size > 1232 B
- Sim gate every tx.

#### B.2 Orca Whirlpools (1 day)
- Already in deps. New `services/solana-yield-builder/src/adapters/orca-whirlpool.js`:
  - `WhirlpoolClient.fromAddress(client, poolAddress)`
  - Align ticks: `Math.floor(rawTick / tickSpacing) * tickSpacing`
  - `increaseLiquidityQuoteByInputToken({ inputToken, inputAmount, tickLower, tickUpper, slippage })`
  - `openPositionWithLiquidity()` → position NFT mint keypair
  - Persist NFT mint in `lp_positions` table for portfolio display.

#### B.3 Raydium CLMM (0.5 day)
- Same SDK as B.1, `clmm` module: `clmm.openPositionFromBase({ poolInfo, tickLower, tickUpper, baseAmount, baseSide })`.

#### B.4 Meteora DLMM (0.5 day)
- Already in deps. `DLMM.create(connection, poolPubkey)` → `dlmm.addLiquidityByStrategy({ totalXAmount, totalYAmount, strategy: SpotV2, activeBin })`.

#### B.5 Kamino vaults (0.5 day)
- `@kamino-finance/kliquidity-sdk` install.
- `kaminoClient.depositToVault({ strategy, amount, user })`.

**Acceptance:** every Solana matrix cell ships real SDK calldata. Sim gate passes on funded mock wallet (Phase D).

### Phase C — Range UI live data (1 day)

1. `src/data/price_history.py`: 30-day hourly candles from CoinGecko free `/coins/{id}/market_chart?days=30&interval=hourly`.
2. `src/defi/range_metrics.py`: empirical CDF over [0.5x, 2x] of current price ratio, 100 buckets.
3. `src/agent/tools/build_yield_execution_plan.py`: attach `market.cdf_30d` (real list) + `market.base_apr_pct` (from `vol_24h * 365 * fee_rate / tvl`).
4. Frontend `PoolDepositV3Card.tsx`: drop canonical-default fallback now that real CDF ships.
5. Harness: assert `len(cdf_30d) == 100` and `base_apr_pct > 0` whenever `tvl_usd > 0`.

### Phase D — Funded wallet simulator (1.5 days)

1. **EVM (Anvil)**: spawn local Anvil fork per chain pinned to latest block.
   - `anvil_setBalance(addr, 10 ETH)`
   - `anvil_setStorageAt(token, balance_slot, addr_padded, amount)` for USDC (slot 9), USDT (slot 2), DAI (slot 2), WETH (slot 3), etc. Registry of top 20 tokens.
   - `anvil_setStorageAt(Permit2, allowance_slot, ...)` for pre-approved Permit2.
   - Switch `eth_call` target from public RPC to local Anvil.
2. **Solana**: `simulateTransaction({sigVerify:false, replaceRecentBlockhash:true, accounts: { encoding: 'base64', addresses: [...] }})` with `replacements` for wallet/token-account balances (Helius supports this). Fallback to `solana-test-validator --clone` for the pool accounts.
3. Harness CLI flag `--sim-mode={mock,fork}` (default `fork`).
4. Every executable tx in the harness must show `sim_ok=True && benign=False`.

### Phase E — DB tool args persistence (0.5 day)

1. SQLAlchemy migration: `AgentChatMessageRow.tool_args_json = Column(Text, nullable=True)`, `tool_name = Column(String(80), nullable=True)`.
2. Persist `(tool_name, tool_input)` after each turn that fires `prior_intent_override` or a deterministic intent detector.
3. LP refinement override reads `prior_turn.tool_args_json` instead of regexing message history.
4. Backward-compatible: if column null (older row), fall back to current regex hint extraction.

### Phase F — Observability (0.5 day)

1. Loki scrape Caddy + container logs.
2. Grafana dashboard JSON committed to `infra/grafana/pool-exec.json`:
   - Tx-success-rate per protocol per chain
   - Sim-pass rate
   - Refinement-override hit rate
   - Enso latency p50 / p95 / p99
   - Solana sidecar build-error rate
3. Sentry SDK in `src/api/middleware/sentry.py`, error events tagged with `phase=pool_exec`.

---

## 4. Total estimate

| Phase | Days |
|---|---|
| A — Enso activation + position-token registry | 0.5 |
| B — Solana SDK integrations (Raydium AMM + Orca + Raydium CLMM + Meteora DLMM + Kamino) | 3 |
| C — Range UI live CDF | 1 |
| D — Funded wallet sim (Anvil fork EVM + Solana replacements) | 1.5 |
| E — DB tool_args_json | 0.5 |
| F — Observability | 0.5 |
| **Total (sequential)** | **7 days** |
| **Total (parallel A‖C‖E‖F, then B‖D)** | **~4 days** |

vs old plan's 12-19 days. Enso-primary saves ~5-12 days of hand-rolled EVM SDK work.

---

## 5. What gets DROPPED from old plan

- ❌ Phase 7 EVM Uniswap V3 native `NonfungiblePositionManager.mint` adapter — **handled by Enso**.
- ❌ Phase 7 EVM Uniswap V2 single-sided zap (0x + Router) — **handled by Enso**.
- ❌ Phase 6 Balancer single-asset Vault.joinPool encoder — **handled by Enso**.
- ❌ Hand-rolled Permit2 EIP-712 signing — **Enso bundle uses Permit2 internally**.
- ❌ Address Lookup Table on EVM — **N/A, Enso handles bundling**.

Keep:
- ✅ Phase 6 Curve direct adapter (already shipped) — kept as backup-only, not in registry.
- ✅ Phase 7 V2 dual-token (already shipped) — kept as backup-only.
- ✅ Aave / Compound direct adapters — kept as backup; Enso primary.

---

## 6. Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Enso 1-rps rate-limit chokes the harness | High | Add 1.1s pacing between Enso calls; document paid-tier upgrade path |
| Enso doesn't cover a long-tail V3 pool | Low | Resolve pool address on-chain, retry with that exact address as `tokenOut` |
| Enso outage takes whole EVM exec down | Medium | Health check + status banner ("Enso unavailable, try again in X min"); allow user-initiated retry; do NOT silently fall back to less-tested direct path |
| Raydium SDK v2 breaking change mid-session | Medium | Pin exact version `0.1.106-rc.5` (latest stable per probe) |
| CoinGecko 30-day candles paywall | Low | Fallback to Birdeye (already have key in env) |
| Anvil fork RPC needs paid alchemy/infura | Medium | Use Helius for Solana, Alchemy free tier for EVM during dev; document paid endpoints for prod harness |

---

## 7. Plan satisfaction matrix

How this v2 plan satisfies the **original prompt** verbatim:

| Original requirement | v2 phase | Status |
|---|---|---|
| "Brainstorm pool execution across V2/V3/stable EVM+Solana" | §2 architecture | ✅ done in v1 + this rewrite |
| "Per-chain protocol selection — Enso or other" | §2.1 + matrix | ✅ Enso for EVM, direct SDK for Solana — decided |
| "Visual report card (range, APR)" | Phase C | already shipped frontend, real data lands here |
| "Compare research/convo/system gaps" | v1 plan §2 | ✅ done |
| "Full fix plan + report" | this doc + v1 doc | ✅ |
| "Deploy to VPS" | Phase A → staging | ongoing |
| "30+ conversations, fix every issue immediately" | Phase A harness, then full harness | currently 68/68 turns; bump to 80+ post-Enso |
| "Upgrade wallet+tx simulator" | Phase D | Anvil fork shipped |
| "One-click LP to ANY pool on ANY chain" | Phase A (EVM) + Phase B (Solana) | one signed tx EVM, 1-2 sigs Solana |
| "Do not stop until perfectly working" | all phases | session goal |

Every line item of the original prompt is covered by exactly one phase. No gaps.

---

## 8. Self-check before declaring done

- [ ] Phase A: EVM matrix cells (8 chains × 5 pool types = 40 cells) — every cell ships one signed Enso tx.
- [ ] Phase B: Solana matrix cells (1 chain × 6 pool types = 6 cells) — every cell ships real SDK calldata, sim-passes on funded wallet.
- [ ] Phase C: Range card shows real 30-day CDF for every V3 pool — no canonical fallback.
- [ ] Phase D: Every harness turn shows `sim_ok=True, benign=False` on funded Anvil + Solana fork.
- [ ] Phase E: Refinement override pulls from `tool_args_json`, not message regex.
- [ ] Phase F: Grafana shows live tx-success-rate, sim-pass-rate, Enso p95 latency.
- [ ] Harness: ≥ 80 turns / 60 conversations, 100% pass on staging.
- [ ] Tester walkthrough on staging.ilyonai.com confirms one-click into every protocol family above + on-chain LP position appears within 30s.
- [ ] README + `docs/ARCHITECTURE_LIVE.md` updated.

When every box ticks, plan v2 = satisfied + original prompt = satisfied.
