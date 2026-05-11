# Pool Execution → 100% Satisfaction Plan

> **North star:** A user says "deposit $X into pool Y" — one wallet popup, on-chain LP position appears. Works for every pool family on every supported chain. Zero harness failures. Production-deployed and tester-verified.

This plan is a self-contained execution spec for the agent. Every phase has explicit input artifacts, output artifacts, file targets, acceptance criteria, and harness scenarios. The agent executes phases in the documented dependency order using the skill invocations listed at the end. Each phase ends with a deploy + harness loop and only marks complete when its scenarios all pass against `https://ilyonai.com` with the funded wallet simulator.

---

## 1. Acceptance criteria (definition of done)

The plan is satisfied when **every one** of the following is true on `https://ilyonai.com`:

1. `python scripts/validate_pool_exec.py` returns **60/60 turns pass**, **31+/31 conversations pass**, with the funded wallet simulator (real `sim_ok=True`, not benign revert).
2. A user prompt `"Add liquidity to <protocol> <pair> on <chain> with $X"` produces exactly **one signed transaction** end-to-end (Solana) or **one signed transaction via Permit2 + Universal Router** (EVM V3 / V2) — no protocol-app redirects — for every cell in the matrix below:

   |           | Solana | Ethereum | Base | Arbitrum | Polygon | Optimism | BSC | Avalanche |
   |---|---|---|---|---|---|---|---|---|
   | V2 AMM    | Raydium | Uniswap V2 | Uniswap V2 | Camelot | Quickswap | Velodrome V1 | PancakeSwap V2 | Trader Joe V1 |
   | V3 CLMM   | Orca / Raydium CLMM | Uniswap V3 | Uniswap V3, Aerodrome Slipstream | Uniswap V3 | Uniswap V3 | Uniswap V3, Velodrome Slipstream | PancakeSwap V3 | Trader Joe V2 LB |
   | Stable    | Saber (link only — thin market) | Curve, Balancer | Curve, Balancer | Curve | Curve | Velodrome stable | Ellipsis | Curve |
   | Vault     | Kamino | Yearn, Morpho, Spark | Moonwell | Pendle | Yearn | Velodrome | Venus | Benqi |

3. Wallet simulator runs every tx through a forked-state RPC (Anvil for EVM, Solana RPC `simulateTransaction` with account replacements for Solana) with the wallet pre-funded so reverts are **real**, not "benign empty wallet".
4. Tester walks through every cell of the matrix above on ilyonai.com and confirms an LP position appears in their wallet within 30s of signing.
5. README + `docs/ARCHITECTURE_LIVE.md` updated to reflect the live state with no aspirational fiction.

---

## 2. Why current state ≠ 100%

| Gap | Root cause | Phase |
|---|---|---|
| Solana AMM (Raydium WSOL-AURA): prep-swap signs, but `addLiquidity` finalize happens on Raydium app | Sidecar does Jupiter swap only, no Raydium SDK addLiquidity ix | 2 |
| Solana CLMM (Orca Whirlpool, Raydium CLMM): no in-chat mint | Whirlpool SDK declared in `package.json` but unused | 3 |
| Kamino vault single-sided: REST tried, no fallback to Kamino SDK | REST endpoint shape unstable | 4 |
| Meteora DLMM bin distribution: prep only | DLMM SDK declared in `package.json` but unused | 5 |
| EVM Curve / Balancer single-sided: redirected to pool_link | No `add_liquidity([0,X,0])` adapter | 6 |
| EVM Uniswap V2 / V3 / Pancake / Aerodrome: redirected to pool_link | No `NonfungiblePositionManager.mint` builder; no V2 zap composer; no Permit2 plumbing | 7 |
| Range card APR / probability uses fallback defaults when `cdf_30d=[]` | No historical-price fetcher | 8 |
| Wallet simulator reports `benign_revert` for every real path | Test wallets empty; no forked-state injection | 9 |
| Multi-turn refinement uses summary regex fallback | Tool args not persisted alongside cards | 10 |
| Kind classifier still heuristic | No explicit per-protocol registry | 1 |
| DefiLlama paid-only outage cascades | No GeckoTerminal live integration | 1 |

---

## 3. Architecture additions

These five primitives unblock every downstream phase. Build them first; every adapter consumes them.

### 3.1 `EnrichedPool` + Pool Enrichment Layer (`src/data/pool_enrichment.py`)

Replaces the current ad-hoc `_fetch_pool_meta`. Returns a fully populated dataclass regardless of which upstream is up.

```python
@dataclass(frozen=True)
class EnrichedPool:
    pool_id: str
    chain: str
    protocol_slug: str          # normalised: "uniswap-v3", "raydium-amm", "raydium-clmm", ...
    pool_type: PoolType         # V2_AMM | V3_CLMM | DLMM | STABLE | VAULT | AUTO_VAULT_CLMM
    pool_address: str           # on-chain address / AMM id
    pair: tuple[TokenRef, TokenRef] | tuple[TokenRef, ...]  # 2-N tokens for stable
    apy_base_pct: float
    apy_reward_pct: float
    tvl_usd: float
    vol_24h_usd: float | None
    # V3 / CLMM only
    fee_tier_bps: int | None = None
    tick_spacing: int | None = None
    current_tick: int | None = None
    sqrt_price_x96: int | None = None
    # V2 only
    reserve0_raw: int | None = None
    reserve1_raw: int | None = None
    lp_total_supply_raw: int | None = None
    # Stable only
    A_param: int | None = None
    # Provenance
    source: Literal["protocol_api", "rpc", "geckoterminal", "defillama", "catalog"]
    fetched_at: int
```

Source fallback order (first non-empty wins):

1. **Per-protocol API** — Raydium `api-v3.raydium.io/pools/info/ids`, Orca SDK `getWhirlpool`, Meteora `lb-pair`, Uniswap V3 subgraph, Curve `api.curve.fi`, Aerodrome subgraph, PancakeSwap subgraph.
2. **Direct RPC** — `eth_call` for V3 `slot0` / V2 reserves / Curve coins; `getAccountInfo` + Anchor decode for Solana programs.
3. **GeckoTerminal** — `https://api.geckoterminal.com/api/v2/networks/{chain}/pools/{address}` (live, returns 200).
4. **DefiLlama** — `yields.llama.fi/pools` if it returns 200 (currently paid-only — keep but don't rely on).
5. **Static catalog** — the 15-pool snapshot already shipped (`_FALLBACK_POOL_CATALOG`).

Cache `EnrichedPool` in Redis: 30s TTL for v3 fields (`current_tick`, `sqrt_price_x96` change every block), 5min TTL for everything else.

### 3.2 Type Registry (`src/agent/pool_types.py`)

```python
class PoolType(str, Enum):
    V2_AMM = "v2_amm"
    V3_CLMM = "v3_clmm"
    DLMM = "dlmm"
    STABLE = "stable"
    VAULT = "vault"
    AUTO_VAULT_CLMM = "auto_vault_clmm"

POOL_TYPE_REGISTRY: dict[str, PoolType] = {
    # Solana
    "raydium-amm": PoolType.V2_AMM,
    "raydium-cp": PoolType.V2_AMM,
    "raydium-clmm": PoolType.V3_CLMM,
    "raydium-amm-v3": PoolType.V3_CLMM,
    "orca": PoolType.V2_AMM,
    "orca-dex": PoolType.V2_AMM,
    "orca-whirlpools": PoolType.V3_CLMM,
    "meteora-amm": PoolType.V2_AMM,
    "meteora-dlmm": PoolType.DLMM,
    "kamino-liquidity": PoolType.AUTO_VAULT_CLMM,
    "saber": PoolType.STABLE,
    "mercurial": PoolType.STABLE,
    # EVM
    "uniswap-v2": PoolType.V2_AMM,
    "uniswap-v3": PoolType.V3_CLMM,
    "uniswap-v4": PoolType.V3_CLMM,
    "pancakeswap-v2": PoolType.V2_AMM,
    "pancakeswap-v3": PoolType.V3_CLMM,
    "pancakeswap-amm-v3": PoolType.V3_CLMM,
    "sushiswap": PoolType.V2_AMM,
    "sushiswap-v3": PoolType.V3_CLMM,
    "aerodrome": PoolType.V2_AMM,
    "aerodrome-slipstream": PoolType.V3_CLMM,
    "velodrome-v1": PoolType.V2_AMM,
    "velodrome-slipstream": PoolType.V3_CLMM,
    "camelot": PoolType.V2_AMM,
    "trader-joe-v2": PoolType.V3_CLMM,
    "quickswap": PoolType.V2_AMM,
    "curve-dex": PoolType.STABLE,
    "balancer-v2": PoolType.STABLE,
    "balancer-v3": PoolType.STABLE,
    "yearn-finance": PoolType.VAULT,
    "morpho-blue": PoolType.VAULT,
    "spark": PoolType.VAULT,
    "moonwell": PoolType.VAULT,
    "pendle": PoolType.VAULT,
    "venus": PoolType.VAULT,
    "benqi-liquid-staking": PoolType.VAULT,
    "gamma": PoolType.AUTO_VAULT_CLMM,
    "arrakis": PoolType.AUTO_VAULT_CLMM,
    "steer-protocol": PoolType.AUTO_VAULT_CLMM,
}

def lookup_pool_type(protocol_slug: str) -> PoolType:
    """Explicit registry first; substring heuristic only for unknowns."""
    norm = protocol_slug.lower().strip()
    if norm in POOL_TYPE_REGISTRY:
        return POOL_TYPE_REGISTRY[norm]
    # Substring fallback for new protocols
    if any(h in norm for h in ("v3", "v4", "clmm", "slipstream", "concentrated")):
        return PoolType.V3_CLMM
    if any(h in norm for h in ("curve", "balancer", "saber")):
        return PoolType.STABLE
    if any(h in norm for h in ("yearn", "morpho", "spark", "beefy", "ichi")):
        return PoolType.VAULT
    if "dlmm" in norm:
        return PoolType.DLMM
    return PoolType.V2_AMM
```

### 3.3 Address Lookup Table Registry (Solana, `services/solana-yield-builder/src/alt.js`)

Deploy three global ALTs once, hard-code their addresses in env:

- `ALT_CORE` — Jupiter program, Raydium AMM v4 program, Raydium CLMM program, Orca Whirlpool program, Meteora program, system / token program.
- `ALT_TOKENS_50` — top 50 SPL mints by market cap (SOL/USDC/USDT/JLP/JTO/PYTH/W/JUP/ etc.).
- `ALT_TOKENS_TAIL` — top 200 long-tail mints (refreshed weekly).

Every sidecar-built tx passes `addressLookupTableAccounts: [ALT_CORE, ALT_TOKENS_50, ALT_TOKENS_TAIL]` to `TransactionMessage.compileToV0Message`. Wallets cache the ALT after first use → subsequent txs decode them locally without RPC.

### 3.4 Permit2 plumbing (EVM, `src/defi/execution/permit2.py`)

Permit2 contract `0x000000000022D473030F116dDEE9F6B43aC78BA3` is deployed on every EVM chain we support. Flow:

1. One-time per (chain, token, wallet): user signs `approve(Permit2, type(uint256).max)`. After that, Permit2 is the only ERC20 approver they need across our entire app.
2. Per action: user signs an EIP-712 `PermitTransferFrom` off-chain. Backend includes the signature in calldata. Spender pulls tokens via Permit2.
3. Universal Router (Uniswap), Enso, 0x v2 all accept Permit2 signatures natively.

Where Permit2 isn't supported (Curve, Aerodrome non-Slipstream), fall back to classic approve.

### 3.5 NFT position tracker (`src/storage/lp_positions.py`)

New SQLAlchemy model:

```python
class LpPositionRow(Base):
    __tablename__ = "lp_positions"
    id = Column(Integer, primary_key=True)
    wallet_address = Column(String(64), nullable=False, index=True)
    chain = Column(String(20), nullable=False)
    protocol = Column(String(40), nullable=False)
    pool_address = Column(String(64), nullable=False)
    position_id = Column(String(80), nullable=False)  # ERC721 tokenId / Whirlpool position mint
    nft_contract = Column(String(64))                 # null on Solana
    tick_lower = Column(Integer)
    tick_upper = Column(Integer)
    liquidity_raw = Column(String(80))
    opened_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
```

Frontend portfolio page reads this to render open positions, claim fees, and close.

---

## 4. Phases

Dependency graph: 1 → (2, 6, 9, 10) → (3, 7) → (4, 5, 8) → 11 → 12.

### Phase 1 — Enrichment + Type Registry (2 days, blocking)

Build `EnrichedPool` + `pool_enrichment.py` + `pool_types.py`. Refactor `execute_pool_position._fetch_pool_meta` to call the new enrichment.

**Files:**
- new `src/data/pool_enrichment.py`
- new `src/agent/pool_types.py`
- modify `src/agent/tools/execute_pool_position.py`
- modify `src/agent/protocol_urls.py` (`classify_pool_kind` reads registry)
- new `src/data/geckoterminal_client.py`

**Unit tests:** one `EnrichedPool` per cell of the matrix in §1 (32 cells).

**Harness scenarios added:** explicit-pool-id intents — `"deposit $100 into pool <uuid>"` — must return a fully populated `EnrichedPool` or a structured `unsupported_protocol` blocker. No `pool_not_found` fall-through.

**Acceptance:** harness `phase1` suite green; every cell has a usable enrichment.

### Phase 2 — Solana Raydium AMM zap (1.5 days)

Real `Raydium.liquidity.addLiquidityInstruction` after pair-aware Jupiter prep swap.

**Files:**
- new `services/solana-yield-builder/src/adapters/raydium-amm-zap.js`
- modify `raydium.js` to switch on `extra.pool_type === "v2_amm"`
- new `services/solana-yield-builder/src/sol_tx.js` (ALT + ComputeBudget + priority fee helpers)

**Stack:** `@raydium-io/raydium-sdk-v2` (install). Confirmed working with Jupiter quote shape (mainnet).

**Flow:**

1. Receive `{ pool: EnrichedPool, asset_in, amount_in_human, user }`.
2. Compute target ratio (V2 = 50/50 by value).
3. Build two Jupiter swap quotes: `asset_in → token0` and `asset_in → token1` (skip leg where `asset_in == tokenN`).
4. Use Raydium SDK `Raydium.load({ owner: user, connection })` → `raydium.liquidity.computePairAmount` → `raydium.liquidity.addLiquidityInstruction`.
5. Pack everything into one `VersionedTransaction` with `addressLookupTableAccounts: [ALT_CORE, ALT_TOKENS_50]`. If size > 1232 B, split into 2 txs (swaps first, deposit second) and surface as a 2-signature flow.
6. `simulateTransaction` gate per tx.

**Harness scenarios:**

- `"Execute raydium-amm SPACEX-WSOL with 10 USDC"` → 1-2 VersionedTx, sim pass, post-state shows LP token in user wallet.
- `"Execute raydium-amm USDC-SOL with 0.5 SOL"`
- `"Add liquidity to Raydium AMM USDC-USDT with 50 USDC"`

**Acceptance:** funded wallet sim shows LP token balance > 0 in post-state on every scenario.

### Phase 3 — Solana CLMM (Orca Whirlpools + Raydium CLMM) (3 days)

In-chat range mint with position NFT.

**Files:**
- new `services/solana-yield-builder/src/adapters/orca-whirlpool.js`
- new `services/solana-yield-builder/src/adapters/raydium-clmm.js`
- modify `services/solana-yield-builder/src/adapters/orca.js` to switch on pool type
- modify `services/solana-yield-builder/src/adapters/raydium.js` to switch on pool type

**Stack:** `@orca-so/whirlpools-sdk` (already declared) + `@raydium-io/raydium-sdk-v2` clmm module.

**Flow (Orca):**

1. Read `EnrichedPool.sqrt_price_x96`, `current_tick`, `tick_spacing`, `fee_tier_bps`.
2. Build `Whirlpool.fromAddress(client, pool_address)`.
3. Align `tickLower` and `tickUpper` from user's selected range:

   ```js
   function alignTick(rawTick, tickSpacing) {
     return Math.floor(rawTick / tickSpacing) * tickSpacing;
   }
   ```

4. `increaseLiquidityQuoteByInputToken({ inputToken, inputAmount, tickLower, tickUpper, slippage })` → optimal ratio.
5. Two Jupiter prep swaps to reach the ratio (skip side already held).
6. `openPositionWithLiquidity` returns instructions + the position NFT mint keypair.
7. Pack: ComputeBudget 600k + priority fee from Helius `getPriorityFeeEstimate` (75th percentile) + ALTs.
8. `simulateTransaction` gate.

**Flow (Raydium CLMM):** identical pattern using `raydium.clmm.openPositionFromBase`.

**Harness scenarios:** Orca Whirlpool USDC/SOL, Raydium CLMM mSOL/SOL, multiple range presets (Narrow/Balanced/Wide).

**Acceptance:** funded sim shows position NFT mint in user wallet + tickLower/tickUpper match selected range.

### Phase 4 — Kamino single-sided CLMM fallback (1 day)

When user picks "Kamino vault" path (recommended for small deposits and risk-averse users).

**Files:**
- new `services/solana-yield-builder/src/adapters/kamino-clmm.js`

**Stack:** `@kamino-finance/kliquidity-sdk` (install). Single-sided deposit is native.

**Flow:**

1. `kaminoClient.depositToVault({ strategy, amount, user })` → one instruction sequence.
2. ALT pack.
3. Sim gate.

**Harness scenarios:** Kamino USDC-SOL vault, Kamino JLP vault.

### Phase 5 — Meteora DLMM (2 days)

Bin distribution strategies (Spot, Curve, Bid-Ask).

**Files:**
- new `services/solana-yield-builder/src/adapters/meteora-dlmm.js`
- modify `services/solana-yield-builder/src/adapters/meteora.js` to switch on pool type

**Stack:** `@meteora-ag/dlmm` (already declared).

**Flow:**

1. `DLMM.create(connection, poolPubkey)` → pool state.
2. Read `activeBin`, `binStep`, `totalLiquidity`.
3. Map user range preset → bin range `[minBinId, maxBinId]`.
4. Pick strategy: Spot (uniform) by default; Curve (concentrated around active) for stable pairs; Bid-Ask for volatile.
5. `addLiquidityByStrategy({ user, positionPubKey, totalXAmount, totalYAmount, strategy, slippage })`.
6. Pair-aware Jupiter prep swap if `asset_in` isn't already a side.

**Harness scenarios:** Meteora SOL/USDC DLMM with each strategy.

### Phase 6 — EVM Curve + Balancer native single-sided (1 day)

**Files:**
- new `src/defi/execution/adapters/curve.py`
- new `src/defi/execution/adapters/balancer.py`

**Stack:** direct `web3.py` contract calls. Curve `add_liquidity([0, X, 0], min_lp)` and Balancer `joinPool` with single-asset are native.

**Flow:**

1. Enrich pool — get coin index, decimals, pool contract.
2. If `asset_in` is in pool: `add_liquidity(amounts_with_only_input_filled, min_lp)`.
3. If not: one 0x swap into the cheapest pool coin, then add.
4. Slippage: 0.5% default for stable pools.
5. Use Permit2 for approval where Curve/Balancer support it; classic approve fallback.
6. Pre-sign sim via Anvil fork.

**Harness scenarios:** Curve 3pool USDC, Curve crvUSD/USDC, Balancer rETH/WETH single-sided WETH.

### Phase 7 — EVM Uniswap V2 / V3 + forks (3 days)

The big one. One signed tx via Universal Router + Permit2 for the happy path.

**Files:**
- new `src/defi/execution/adapters/uniswap_v3_mint.py`
- new `src/defi/execution/adapters/uniswap_v2_zap.py`
- new `src/defi/execution/adapters/pancake_v3.py` (Uniswap V3 fork)
- new `src/defi/execution/adapters/aerodrome_slipstream.py` (Uniswap V3 fork on Base)
- new `src/defi/execution/adapters/sushiswap_v3.py`
- new `src/defi/execution/adapters/velodrome_slipstream.py`

**Stack:** `@uniswap/v3-sdk`, `@uniswap/universal-router-sdk`, 0x v2 swap API, Permit2.

**Flow V3 (single-sided):**

1. Enrich pool: `sqrt_price_x96`, `current_tick`, `tick_spacing`, `fee_tier_bps`, `token0`, `token1`.
2. Align user range → `tickLower`, `tickUpper`.
3. `Position.fromAmounts({ pool, tickLower, tickUpper, amount0, amount1, useFullPrecision: true })` → optimal `amount0Desired`, `amount1Desired`.
4. Convert user's `input_amount_usd` into the two amounts by ratio.
5. Two 0x swap quotes: `input_token → token0` (size = `amount0Desired_value`), `input_token → token1` (size = `amount1Desired_value`). Skip the leg where `input_token == tokenN`.
6. `Permit2.permitTransferFrom` signature for the input token.
7. Build Universal Router calldata that batches: Permit2 transfer → 0x swap × 2 → `NonfungiblePositionManager.mint(MintParams{ tickLower, tickUpper, amount0Min, amount1Min, recipient: user, deadline })`. Single user signature.
8. `eth_call` simulate against Anvil fork with user balance funded.
9. Record minted `tokenId` in `lp_positions` after broadcast.

Edge cases:

- If `current_tick < tickLower`: 100% `token1` side; skip token0 swap.
- If `current_tick > tickUpper`: 100% `token0` side; skip token1 swap.
- USDT/KNC classic approve: `approve(Permit2, 0)` → `approve(Permit2, max)` two-step (only first time per (chain, token, wallet)).

**Flow V2 (single-sided):**

1. Two 0x swap quotes by `input_amount_usd / 2` each.
2. Universal Router multicall: Permit2 transfer → 0x swap × 2 → `Router.addLiquidity(token0, token1, amount0, amount1, amount0Min, amount1Min, to, deadline)`.

**Harness scenarios:**

- Uniswap V3 USDC/WETH 0.05% on Ethereum / Base / Arbitrum.
- PancakeSwap V3 USDT/BNB on BSC.
- Aerodrome Slipstream USDC/WETH on Base.
- Uniswap V2 USDC/WETH on Ethereum.
- Velodrome V1 / Slipstream on Optimism.
- Multi-turn refinement: change range → rebuild tx with new ticks.

**Acceptance:** funded Anvil fork sim shows position NFT minted with correct ticks.

### Phase 8 — Range UI live data + APR math (1.5 days)

Real historical CDF and real APR breakdown.

**Files:**
- new `src/defi/range_metrics.py`
- new `src/data/price_history.py`
- modify `src/agent/tools/build_yield_execution_plan.py` to attach `market.cdf_30d` + real `base_apr_pct` + `reward_apr_pct`
- modify `web/components/agent/cards/PoolDepositV3Card.tsx` to read real CDF without fallback

**Backend:**

```python
def base_apr_pct(pool: EnrichedPool) -> float:
    if not pool.vol_24h_usd or not pool.tvl_usd:
        return pool.apy_base_pct
    fee_rate = pool.fee_tier_bps / 1e4
    daily_fee_usd = pool.vol_24h_usd * fee_rate
    return (daily_fee_usd * 365) / pool.tvl_usd * 100
```

```python
async def cdf_30d(token0: TokenRef, token1: TokenRef) -> list[float]:
    """Return CDF over 100 buckets in [0.5x, 2x] of current ratio.
    Source: Birdeye (Solana) / CoinGecko (EVM) 30d hourly candles → ratio
    series → empirical CDF.
    """
```

**Frontend:** the existing `PoolDepositV3Card.tsx` already consumes `cdf_30d`; remove the canonical-default fallback now that real data ships.

**Harness scenario:** assert every `pool_deposit_v3` card has `cdf_30d.length == 100` and `base_apr_pct > 0` whenever `tvl_usd > 0`.

### Phase 9 — Wallet Simulator funded-balance upgrade (2 days)

The simulator must confirm **real** success, not benign revert.

**Files:**
- modify `tests/adversarial/wallet_simulator.py`
- new `tests/adversarial/anvil_fork.py`
- new `tests/adversarial/solana_fund.py`

**EVM (Anvil):**

1. Spawn local Anvil fork pinned to current mainnet block per chain.
2. For each test wallet on each chain:
   - `anvil_setBalance(addr, eth_amount)` — give 10 ETH.
   - For ERC20: write the balance storage slot directly via `anvil_setStorageAt`. Slot resolver per token (USDC = 9, WETH = 3, USDT = 2, etc.). Maintain a `BALANCE_SLOT_REGISTRY` for top 100 tokens.
   - `anvil_setStorageAt` for Permit2 allowance state.
3. Switch `eth_call` target from public RPC to local Anvil URL.
4. Run tx through Anvil. Real revert => real failure. No more benign-revert mask.

**Solana:**

1. Use `simulateTransaction` with `accounts: { encoding: "base64", addresses: [...] }` + `replacements` (Helius supports this). Inject fake SOL + SPL balances in the simulation context.
2. Fallback: spin a local `solana-test-validator` with `--clone` for the pools' accounts.

**Harness wiring:**

- New CLI flag: `--sim-mode={mock,fork}`. Default `fork`.
- All `expect_solana_sim_ok` / `expect_evm_sim_ok` turns must now pass with **non-benign** sim. Existing `benign_revert` codepath stays for the "is calldata structurally valid" check but doesn't count toward turn-level pass.

**Acceptance:** every executable tx in the harness shows `sim_ok=True` and `benign=False`.

### Phase 10 — Multi-turn refinement: persist tool args (1 day)

Replace the summary-regex hack with real tool-arg recall.

**Files:**
- modify `src/storage/agent_chats.py` add `tool_args_json` column on `AgentChatMessageRow`
- modify `src/agent/simple_runtime.py` to persist `(tool_name, tool_input)` after each turn that fires `prior_intent_override` OR a deterministic intent
- modify the LP refinement override to read tool args from the last assistant turn rather than parsing the card summary
- migration `alembic upgrade head`

**Schema:**

```python
class AgentChatMessageRow(Base):
    ...
    tool_args_json = Column(Text, nullable=True)   # JSON of last tool call
    tool_name = Column(String(80), nullable=True)
```

Override reads `prior_turn.tool_args_json` and merges deltas. No more regex on `summary`.

**Harness scenarios:** every "make it $X", "try CHAIN", "switch to TOKEN", "what if I use $X" turn pass with exact prior-intent rebuild.

### Phase 11 — Harness expansion (parallel with every phase, 1 day total)

Expand `scripts/validate_pool_exec.py` to **60+ turns** covering every cell of the matrix in §1. Each phase ships its scenarios on landing.

**New conversation classes:**

- One-tx end-to-end deposit per (chain, family) cell (24+ scenarios).
- Multi-turn refinement on every executable family.
- Range-refine on every V3 cell (drag handle → new ticks → re-sim).
- Failure scenarios: insufficient balance, slippage breach, expired quote, USDT classic approve.
- Recovery scenarios: tx fails → user retries with adjusted slippage → succeeds.

**Acceptance:** 60/60 turns, every executable scenario shows `sim_ok=True` on funded fork.

### Phase 12 — Production deploy + observability (0.5 day)

**Files:**
- `deploy/prod/app.env` — `ANVIL_FORK_RPC_*` URLs, `BIRDEYE_API_KEY`, `KAMINO_API_BASE`, `ALT_CORE`, `ALT_TOKENS_50`.
- Caddy log scraping → Loki.
- Grafana dashboard: tx success rate per protocol, per chain, per pool family; sim-pass rate; refinement-override hit rate.
- Sentry / structured-error logging on every adapter throw.

**Acceptance:** live ilyonai.com green for 24h; tester walks through every cell and reports one-click success.

---

## 5. Cross-cutting infra (use across every phase)

### 5.1 Decimal-precision discipline

- Every amount on every wire is `Decimal` (Python) or `BigInt`/`bigint` string (JS).
- Lint rule: any `float()` cast in adapter code → CI fail.
- Atom conversion is BigInt-only (`humanToAtoms` in jupiter.js — already shipped).

### 5.2 Tick alignment helper

```python
def align_tick(raw_tick: int, tick_spacing: int) -> int:
    return (raw_tick // tick_spacing) * tick_spacing
```

Mandatory in every V3 adapter. Misalignment → guaranteed revert.

### 5.3 Stale quote refresh

Every card payload carries `expires_at: now+60s`. Frontend disables Sign at expiry with a Refresh button that rebuilds the tx with fresh quotes.

### 5.4 Failure decoder

`src/defi/execution/error_decoder.py`. Maps known revert codes / Anchor errors to human strings:

```
InsufficientLiquidity → "Pool depth too low for this size."
PriceSlippageCheckFailed → "Price moved beyond your slippage tolerance."
0x... (custom error sig) → look up in 4byte.directory
```

### 5.5 Reasonable defaults

| Param | Default | Source |
|---|---|---|
| V3 range | ±10% | Auto-tighten to ±0.5% for stable/stable pairs |
| Slippage | 0.5% stables / 1% blue chips / 2-3% long-tail | Detect by token classification |
| Priority fee (Solana) | Helius `getPriorityFeeEstimate` 75th pct | Re-fetch every 30s |
| Gas (EVM) | EIP-1559, 1.2× `eth_maxPriorityFeePerGas` | |
| In-range target | 70-80% probability | Auto-pick range when user didn't specify |

---

## 6. Validation methodology

Every phase ends with this loop:

1. Unit tests pass locally (`pytest tests/phaseN/`).
2. `python scripts/validate_pool_exec.py --suite=phaseN --sim-mode=fork` passes on the laptop with Anvil fork.
3. Deploy to `staging.ilyonai.com`. `python scripts/validate_pool_exec.py --base=https://staging.ilyonai.com --sim-mode=fork` passes.
4. Deploy to `ilyonai.com`. `python scripts/validate_pool_exec.py --base=https://ilyonai.com --sim-mode=fork` passes.
5. On any failure: fix → redeploy → rerun. Do not advance phases until clean.

Plan-level done = §1 acceptance criteria all true.

---

## 7. Skill invocations

| Phase | Skill | Why |
|---|---|---|
| Each | superpowers:writing-plans | Per-phase mini-plan before code |
| 2-7 | superpowers:test-driven-development | Harness scenario → red → green |
| 2-7 | superpowers:using-git-worktrees | Each phase in isolated worktree off `main` so prod stays stable |
| 1, 3, 7, 9 | superpowers:systematic-debugging | When fork sim fails or SDK throws |
| Each | superpowers:verification-before-completion | Before claiming any phase done |
| Each | ilyonai-deploy-and-validate | Staging → prod gate per phase |
| Each | ilyonai-tool-mastery | GitNexus + codebase-memory before grep |
| Each | ilyonai-independent-decisions | Decide unless genuinely blocked |
| 7, 8 | caveman:cavecrew-investigator | Locate Uniswap V3 SDK / Birdeye API integration points |
| 12 | superpowers:requesting-code-review | Before final production deploy |

---

## 8. Roll-out order (with parallelism)

```
Phase 1 ─┐
         ├─► Phase 2 ─┐
         ├─► Phase 6 ─┤
         ├─► Phase 9 ─┤
         └─► Phase 10 ┘
                      ├─► Phase 3 ─┐
                      ├─► Phase 7 ─┤
                                   ├─► Phase 4 ─┐
                                   ├─► Phase 5 ─┤
                                   └─► Phase 8 ─┘
                                                ├─► Phase 11 ─► Phase 12
```

**Parallel pairs** (different sidecars / different layers, no shared state):

- Phase 2 (Solana sidecar) ‖ Phase 6 (Python EVM) ‖ Phase 9 (sim) ‖ Phase 10 (DB).
- Phase 3 (Solana sidecar) ‖ Phase 7 (Python EVM).
- Phase 4 ‖ Phase 5 ‖ Phase 8 (all touch different files).

Use `superpowers:using-git-worktrees` to run each parallel branch in an isolated worktree.

---

## 9. Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Raydium SDK v2 breaking change | Medium | Pin exact version; mock SDK responses in unit tests; vendor a minimal subset if upstream churn intolerable. |
| Solana tx exceeds 1232 B even with ALT | Medium | Split into 2 sigs; document the UX flow ("approve + open" two clicks); make ALT cover every program + every common mint. |
| Permit2 not supported by Aerodrome Slipstream / Velodrome | High | Fallback to classic two-step approve; surface the extra signature in the card preview. |
| Anvil fork rate-limit on public RPC | Medium | Use Helius / Alchemy paid endpoints; rotate keys. |
| Helius `getPriorityFeeEstimate` returns 0 during congestion | Low | Add hard floor of 10k microlamports for zaps. |
| Birdeye historical candles paywall | Medium | Cache aggressively (Redis 1h); fallback to CoinGecko free tier; if neither, ship empty `cdf_30d` and the frontend falls back to the canonical default table already shipped. |
| Tester finds a long-tail pool we didn't index | Medium | Enrichment layer's GeckoTerminal fallback handles arbitrary `pool_address`; harness adds the failing pool as a regression test. |
| Position NFT custody confusion | Low | Card explains: "Your position is an NFT in your wallet. Selling/closing requires the NFT — keep it." |

---

## 10. Total estimate

| Phase | Days |
|---|---|
| 1 — Enrichment + Type Registry | 2 |
| 2 — Raydium AMM zap | 1.5 |
| 3 — Solana CLMM | 3 |
| 4 — Kamino fallback | 1 |
| 5 — Meteora DLMM | 2 |
| 6 — EVM Curve + Balancer | 1 |
| 7 — EVM Uniswap V2 + V3 + forks | 3 |
| 8 — Range UI live data | 1.5 |
| 9 — Sim funded-balance upgrade | 2 |
| 10 — DB tool-args persistence | 1 |
| 11 — Harness expansion | 1 (rolling) |
| 12 — Production deploy + observability | 0.5 |
| **Total (sequential)** | **~19.5 days** |
| **Total (with parallel pairs)** | **~12 days** |

---

## 11. Self-check before declaring done

Before the agent stops, all of the following must be true:

- [ ] §1 acceptance criteria checklist green.
- [ ] `git log --oneline origin/main..HEAD` shows commits per phase with the documented format.
- [ ] `python scripts/validate_pool_exec.py --base=https://ilyonai.com --sim-mode=fork` returns 60/60 turns + 31+/31 conversations, every executable sim showing `sim_ok=True benign=False`.
- [ ] Live walkthrough by tester: every cell of the matrix in §1 produces a one-click LP deposit ending in an on-chain position.
- [ ] README + `docs/ARCHITECTURE_LIVE.md` reflect the live state, no aspirational content.
- [ ] Grafana dashboard live with per-protocol tx success rate.

If any box is unchecked, the plan is not done. The agent does not stop until every box is checked.
