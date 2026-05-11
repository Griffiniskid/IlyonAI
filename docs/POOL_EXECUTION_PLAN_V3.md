# Pool Execution Plan v3 — Enso-Primary EVM + Direct Solana

> **North star (verbatim from initial prompt):** "Deposit money and add liquidity in ONE CLICK to ANY POOL POSSIBLE." User says *"deposit $X into pool Y"* → one wallet popup → on-chain LP position appears within 30 seconds. Works for every pool family on every chain we support. Zero harness failures. Tester walks every cell and signs off.
>
> **Live-probe receipts (2026-05-11):**
> - Enso API key `ca917fd7-…` valid. Auth = `X-API-KEY` header (primary) or `Authorization: Bearer` (also accepted).
> - `/api/v1/networks` returns 12+ chains: Ethereum (1), Optimism (10), BSC (56), Gnosis (100), Unichain (130), Polygon (137), Monad (143), Sonic (146), zkSync (324), and more (Base/Arbitrum/Avalanche/Linea/Scroll/Polygon-zkEVM via continued list).
> - `/api/v1/shortcuts/quote?chainId=1&tokenIn=USDC&tokenOut=aEthUSDC&amountIn=50000000` returns `{"gas":"297571","amountOut":"50000000","priceImpact":2}` instantly.
> - `/api/v1/shortcuts/route?chainId=1&fromAddress=…&tokenIn=USDC&tokenOut=aEthUSDC&amountIn=50000000&slippage=100` returns 3281-byte bundle: `{gas, amountOut, priceImpact, minAmountOut, tx: {data, to, value}}` in <1 s.
> - Rate-limit: ~1 rps free tier. Spaced 1.2 s requests succeed 100 %. Upgrade path documented.

---

## 0. Why this plan is different from v1 / v2

| | v1 (12-19 days) | v2 (Enso outline, 4-7 days) | **v3 (this doc)** |
|---|---|---|---|
| Direct V3 mint adapter | Build from scratch | Drop | **Drop, lean on Enso** |
| Direct V2 zap adapter | Build from scratch | Drop | **Drop, lean on Enso** |
| Direct Curve / Balancer | Build from scratch | Keep as backup | **Reference-only, NOT registered** |
| EVM Aave / Compound supply | Direct calldata | Direct + Enso | **Enso primary, direct stays as belt-and-braces** |
| Solana | Phase 2/3/5 (5 days) | Phase B (3 days) | **Phase B (3 days, scoped) — same as v2** |
| Enso integration | Phase 7 mention | Phase A (0.5 d) | **Phase A — first-class citizen (0.75 d incl. position-token registry + pool address resolver)** |
| Anvil fork sim | Phase 9 (2 d) | Phase D (1.5 d) | **Phase D — same (1.5 d)** |
| Range UI live data | Phase 8 (1.5 d) | Phase C (1 d) | **Phase C — same (1 d)** |
| DB tool_args | Phase 10 (1 d) | Phase E (0.5 d) | **Phase E — same (0.5 d)** |
| Observability | Phase 12 (0.5 d) | Phase F (0.5 d) | **Phase F — same (0.5 d)** |
| Test coverage | 60 turns | 70 turns | **80+ turns / 60+ conversations** |
| Tester one-click sign-off | Aspirational | Aspirational | **Required acceptance #4** |

**v3 total: ~5 days sequential, ~3.5 days with the documented parallelism.** That fits inside one focused engineering session because Enso collapses the entire EVM matrix into one well-tested API call.

---

## 1. DeFi primer — what each pool family actually does on-chain

This section exists because the original prompt asked: *"explain all of this to me as if I were someone who understands DeFi but isn't entirely familiar with liquidity pools."* Every phase below depends on the reader internalizing these mechanics.

### 1.1 Three families of AMM

| Family | Math | Range | Typical APR source | Examples |
|---|---|---|---|---|
| **V2 / xy=k** | Constant product `x · y = k` | Full range (price 0 → ∞) | Swap fee (0.30 %) × volume / TVL | Uniswap V2, SushiSwap, PancakeSwap V2, Raydium AMM v4, QuickSwap, Camelot, Velodrome V1, BaseSwap, Trader Joe V1 |
| **V3 / Concentrated** | Liquidity bounded by `[P_lower, P_upper]` ticks | User-selected | (Swap fee × volume / TVL) × **capital_efficiency × in_range_probability** | Uniswap V3 + V4, Aerodrome Slipstream, Velodrome Slipstream, PancakeSwap V3, SushiSwap V3, Raydium CLMM, Orca Whirlpools |
| **DLMM / discrete-bin** | Liquidity bucketed into bins of constant binStep | User-selected bin range + bin-shape (Spot / Curve / Bid-Ask) | Volume × fee per active bin / liquidity in that bin | Meteora DLMM |
| **Stable** | StableSwap invariant `D ≈ Σ x_i + amp · prod x_i` (Curve), or weighted balancer formula | Effectively full | Swap fee + boost rewards (CRV / BAL) | Curve, Balancer Stable Pools, Saber, Mercurial, Velodrome stable, Ellipsis |
| **Auto-vault on top of CLMM** | Wraps V3 LP, auto-rebalances | Vault-managed | Same as V3 + rebalancing alpha | Kamino, Gamma, Arrakis, Steer |

### 1.2 What "single-sided" actually means (the bug from the screenshot)

The tester's screenshot showed `Raydium-Amm Deposit Lp 0.1111111111111111 WSOL` in a `WSOL-AURA` pool. Two layered bugs:

**Bug A — float precision leak.** `0.1111111111111111` is the IEEE-754 binary representation of `1/9` truncated to 16 digits. Somewhere a `float(x)` cast replaced the user's `0.1 WSOL` (9 decimals). Solution: **BigInt / Decimal end-to-end. No floats on the wire.** Already shipped (Phase 0 in v1 plan).

**Bug B — single token thrown into a two-token pool.** Raydium AMM v4 `deposit` instruction requires `maxCoinAmount` AND `maxPcAmount`. Sending only WSOL is guaranteed-revert. The screenshot called this "single-sided" but didn't implement the **zap-in** primitive (swap half the input into the other side, then deposit both). Solution: **zap-in algorithm per pool family** (see §1.3).

### 1.3 Single-sided zap-in math, per family

User provides `X` units of input token `T_in`. Pool has tokens `T_0 / T_1`. Algorithm:

**V2 (50 / 50 by value):**
```
half_usd = price(T_in) * X / 2
amount_to_T0 = swap_quote(T_in → T_0, half_usd)
amount_to_T1 = swap_quote(T_in → T_1, half_usd)
if T_in == T_0: skip first swap, use X/2 directly
if T_in == T_1: skip second swap
addLiquidity(amount_to_T0, amount_to_T1, slippage=1%)
```
Reality: after two swaps the ratio drifts off 50/50 due to price impact + slippage. Pass `min_amount_0` / `min_amount_1` to `addLiquidity` and let dust stay in the user's wallet. **Better:** use a "balanced zap" router (Enso, Beefy ZapRouter, Bento) that prices the swap against pool reserves so the post-swap ratio matches the pool exactly.

**V3 (range-aware optimal ratio):**

For a position spanning `[tick_lower, tick_upper]` with the current price at `P_current`:

```
sqrtP = sqrt(P_current)
sqrtL = sqrt(P_lower)   # P_lower from tickToPrice(tick_lower)
sqrtU = sqrt(P_upper)

if P_current < P_lower:
    # entire range above current price → 100% token1, 0% token0
    ratio_token0_to_token1 = 0
elif P_current > P_upper:
    # entire range below → 100% token0, 0% token1
    ratio_token0_to_token1 = ∞
else:
    # in-range: derived from Uniswap V3 liquidity math
    amount0_per_L = (sqrtU - sqrtP) / (sqrtP * sqrtU)
    amount1_per_L = sqrtP - sqrtL
    # value ratio in USD
    ratio_token0_to_token1 = (amount0_per_L * price(T0)) / (amount1_per_L * price(T1))
```

Don't write this from scratch — `@uniswap/v3-sdk` exports `Position.fromAmounts({ pool, tickLower, tickUpper, amount0, amount1 })` that returns the optimal split. For Orca Whirlpools the equivalent is `increaseLiquidityQuoteByInputToken`. **For EVM V3 we route through Enso, which does this math internally** — we only pass `tickLower` / `tickUpper` as extra params and Enso emits the swap+mint bundle.

**Stable (native single-sided):**

Curve `add_liquidity([0, X, 0], min_lp)` for a 3-coin pool: pass a zero in every slot except your input. The pool's internal StableSwap invariant rebalances and mints LP. Slippage on the imbalance fee (~0.04 %). Balancer V2 `Vault.joinPool` with `userData = abi.encode(EXACT_TOKENS_IN_FOR_BPT_OUT, [0, X, 0], minBPT)` does the same. **Both go through Enso on EVM**.

**DLMM (Meteora discrete bins):**

User picks a `bin_range = [activeBin - N, activeBin + N]` and a strategy:
- **Spot:** uniform liquidity across all bins
- **Curve:** concentrated near `activeBin` (best for stable pairs)
- **Bid-Ask:** bimodal far from `activeBin` (volatility farming)

SDK call: `dlmm.addLiquidityByStrategy({ totalXAmount, totalYAmount, strategy, activeBin })`. Single-sided requires a pair-aware prep swap via Jupiter for the missing side. **Solana-only — no Enso shortcut.**

**Auto-vault (Kamino / Gamma / Arrakis):**

User deposits one token. Vault contract owns a V3 position and rebalances automatically. SDK: `kaminoClient.depositToVault({ strategy, amount, user })`. Single-sided is native — the vault handles the math. **Recommended path** for $10-$1,000 deposits where gas-of-direct-V3 > value.

### 1.4 Where Enso fits

Enso is a **shortcut bundler**. Internally it:

1. Quotes the best swap route (Jupiter/0x/Curve/internal Curve registry) to convert `tokenIn` → underlying pool assets.
2. Constructs the protocol-specific deposit calldata (V3 mint, Curve add_liquidity, Balancer joinPool, Aave supply, etc.).
3. Bundles everything into one Permit2-aware `tx.data` that the user signs once.

The cost: ~5-15 % of returned value is locked behind their bundler contract during the multi-step (refunded at the end of the bundle if everything succeeds). One signed transaction. No approve dance. No tx-size limit on EVM (no equivalent to Solana's 1232 B). 

What Enso does NOT do:
- Solana (entirely out of scope — different stack).
- Compute V3 range / capital efficiency / in-range probability (math we do client-side).
- Index every long-tail / brand-new pool the day it deploys (fall back to direct V3 mint via the `NonfungiblePositionManager` for those — but that's the rare exception, not the default).

### 1.5 Range card UX — what the user actually sees on V3

(Lifted from the original prompt's example screenshot expectation.)

```
┌──────────────────────────────────────────────────────────────────────┐
│  Uniswap V3 USDC/WETH 0.05%   ⚡ Ethereum   Slippage 1%               │
├──────────────────────────────────────────────────────────────────────┤
│  Pool snapshot                                                       │
│    1 WETH = 3,142.50 USDC                                            │
│    TVL  $148M    Volume 24h  $42M    Fee tier  0.05%                 │
│    Base APR (full-range)  10.4%                                      │
├──────────────────────────────────────────────────────────────────────┤
│  Pick your range                                                     │
│                                                                      │
│   $2,650 ────[░░░░░░░|░|░░░░░░░░]──── $3,700                          │
│            P_low      P_curr         P_high                          │
│                                                                      │
│   [Narrow ±5 %] [Balanced ±10 %] [Wide ±25 %] [Full range]           │
│                                                                      │
│   Capital efficiency       7.2 ×                                      │
│   In-range probability     78 %  (30-day historical price band)      │
│   Expected APR             58 %  (= 10.4 % × 7.2 × 78 %)             │
├──────────────────────────────────────────────────────────────────────┤
│  Comparison                                                          │
│   ±5 %    →  APR 187 % · eff 14 ×   · in-range 52 %                  │
│   ±10 %   →  APR 124 % · eff  7.2 × · in-range 78 %   ← selected     │
│   ±25 %   →  APR  58 % · eff  2.9 × · in-range 94 %                  │
│   Full    →  APR  10 % · eff  1 ×   · in-range 100 %                 │
├──────────────────────────────────────────────────────────────────────┤
│  You deposit                                                         │
│    10.00 USDT                                                        │
│  Will become                                                         │
│    5.27 USDC  +  0.00307 WETH       (Enso optimal split)             │
│  Expected position                                                   │
│    $9.97  (incl. 0.30 % swap slippage)                               │
│  Estimated daily yield   $0.034                                      │
├──────────────────────────────────────────────────────────────────────┤
│  Ordered route                                                       │
│    1. Permit2 transfer 10 USDT                                       │
│    2. Swap 4.73 USDT → 4.73 USDC                                     │
│    3. Swap 5.27 USDT → 0.00307 WETH                                  │
│    4. Mint position [-10 % / +10 %] on Uniswap V3                    │
│       ↳ bundled into 1 Permit2 tx via Enso                           │
│                                                                      │
│  Advanced ▾ (slippage / priority fee / MEV protection)               │
│                                                                      │
│           ┌────────────────────────────────────┐                     │
│           │   Sign one transaction to deposit  │                     │
│           └────────────────────────────────────┘                     │
└──────────────────────────────────────────────────────────────────────┘
```

**Reactivity contract:** when the user drags the range handles, capital efficiency / in-range probability / Expected APR recompute in the browser using closed-form math on data we shipped with the card payload (sqrtPriceX96, current_tick, 30-day CDF). **No backend round-trip on drag.** When the user clicks Sign, the frontend POSTs `{tickLower, tickUpper, slippage}` to the API and we re-call Enso `/shortcuts/route` with those exact ticks to get the final bundle.

`PoolDepositV3Card.tsx` already implements this for the canonical default CDF; Phase C swaps in the real 30-day CDF.

### 1.6 Solana specifics

- **Transaction size limit:** 1232 B without Address Lookup Tables. A real zap (swap + addLiquidity) will overflow. Solution: **global ALTs** owned by us, pre-registered with the canonical program IDs (Jupiter, Raydium AMM v4, Raydium CLMM, Orca Whirlpool, Meteora DLMM, system / token program) and top 50 mints. Reference once in every tx via `addressLookupTableAccounts`. If still too big → split into 2 signed txs (visible to the user as "approve + open").
- **Compute Units:** default 200 k CU is not enough for a zap. Always `ComputeBudgetProgram.setComputeUnitLimit({ units: 600_000 })`.
- **Priority fee:** `getPriorityFeeEstimate` from Helius (`api.helius.xyz/v0/priority-fee?wallet=...&accounts=...`) targeting the 75th percentile. Hard floor 10 k microLamports during congestion.
- **WSOL wrapping:** native SOL needs a temporary token account. SDKs do this for us but the extra instructions bite into tx-size budget.
- **Token-2022 / Token Extensions:** some new mints (mostly memes) live on the Token-2022 program. Verify program owner before swap routing — Jupiter has Token-2022 support; older Raydium ix variants don't.
- **Confirmation strategy:** wait for `finalized` for final state. Show `submitted → confirmed → finalized` as progress in the UI.

### 1.7 EVM specifics

- **USDT classic approve quirk:** `approve(spender, X)` reverts if `allowance(spender) > 0`. **Workaround built into Enso bundle:** the Permit2-transfer skips ERC20 approve entirely on USDT. Direct adapters need to emit two approve calls (`approve(0)` → `approve(X)`) on USDT / KNC.
- **Permit2:** Uniswap's universal approval contract. User signs an off-chain EIP-712 permission, contract spends without an on-chain `approve`. Enso uses Permit2 natively. One-time `approve(Permit2, type(uint256).max)` per (chain, token, wallet) — then every later op is signature-only.
- **Position NFT (V3):** `NonfungiblePositionManager.mint` returns an `ERC721 tokenId`. We persist that in `lp_positions` (Phase E) for portfolio rendering.
- **Tick alignment:** `tickLower = floor(rawTick / tickSpacing) * tickSpacing`. Tick spacing per fee tier: 0.01 % → 1, 0.05 % → 10, 0.30 % → 60, 1 % → 200. Misaligned tick = revert. Enso handles this internally.
- **MEV:** for $10-$1,000 deposits, the price impact swamps any MEV gain — not worth the complexity. For >$10k swaps, route through Flashbots Protect or CoW Protocol. Out of scope this session.

---

## 2. Architecture

### 2.1 One execution path per chain family — no fallbacks

| Chain family | Primary path | Direct fallback |
|---|---|---|
| **EVM (every chain)** | `EnsoShortcutAdapter` → POST `https://api.enso.finance/api/v1/shortcuts/route` | **None.** If Enso doesn't index a specific pool (rare), the card returns a structured `unsupported_pool` blocker (no silent direct-adapter substitution). |
| **Solana** | `SolanaYieldBuilderAdapter` → Node sidecar → real SDK per protocol | **None.** Each Solana pool family has exactly one SDK path. |

This is the **"no fallback"** architecture the user asked for: every protocol-family / chain has a single, well-tested provider. Direct adapters (Curve / Balancer / V2-dual / Aave / Compound) remain in the tree as **reference only** — not registered, not invoked.

Tradeoff accepted: if Enso has a 5-minute outage, EVM exec returns a structured error ("Enso bundle service unavailable, please retry in X seconds"). No silent failover that could quietly drift to wrong pool / wrong protocol family.

### 2.2 Component diagram

```
            ┌────────────────────────────────────────────────────────┐
            │  Next.js web (staging.ilyonai.com)                     │
            │   ↳ PoolDepositV3Card.tsx (range slider, live APR)     │
            │   ↳ pool_link card (V2/stable/vault deeplink)          │
            │   ↳ execution_plan_v3 card (signed-step list + Sign)   │
            └─────────────────────────┬──────────────────────────────┘
                                      │ /api/v1/agent SSE
                                      ▼
            ┌────────────────────────────────────────────────────────┐
            │  aiohttp api (Python)                                  │
            │   ↳ simple_runtime.run_ephemeral_turn                  │
            │     ↳ _detect_pool_execute / _detect_add_liquidity     │
            │       ↳ execute_pool_position(pool, amount, asset_in)  │
            │         ↳ build_yield_execution_plan                   │
            │           ↳ AdapterRegistry.find(chain, protocol)      │
            │             ├─ chain in EVM →  EnsoShortcutAdapter     │
            │             │                  ↳ EnsoClient            │
            │             │                    POST /shortcuts/route │
            │             └─ chain == Solana → SolanaYieldBuilder    │
            │                                  ↳ HTTP /build         │
            └─────────────────────────┬──────────────────────────────┘
                                      │                       │
                                      ▼                       ▼
            ┌──────────────────────────┐    ┌─────────────────────────────┐
            │  Enso shortcuts API      │    │  solana-yield-builder Node  │
            │  api.enso.finance        │    │   ↳ raydium-amm-zap.js      │
            │                          │    │   ↳ orca-whirlpool.js       │
            │  Returns: tx.data        │    │   ↳ raydium-clmm.js         │
            │           gas / impact   │    │   ↳ meteora-dlmm.js         │
            │           minAmountOut   │    │   ↳ kamino-clmm.js          │
            └──────────────────────────┘    │   ↳ jupiter.js (swap leg)   │
                                            └─────────────────────────────┘
```

### 2.3 Enso integration contract

`src/routing/enso_client.py` (Phase A rewrites):

```python
class EnsoClient:
    base = "https://api.enso.finance/api/v1"
    rate_limit_interval_s = 1.1  # global throttle, 1 rps free tier
    _last_call_at: float | None = None

    async def route(self, *, chain_id: int, token_in: str, token_out: str,
                    amount_in: str, from_addr: str, slippage_bps: int = 100,
                    extra_params: dict | None = None) -> dict:
        await self._respect_rate_limit()
        params = {
            "chainId": chain_id,
            "fromAddress": from_addr,
            "tokenIn": token_in,
            "tokenOut": token_out,
            "amountIn": amount_in,
            "slippage": slippage_bps,
        }
        if extra_params:
            params.update(extra_params)
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{self.base}/shortcuts/route",
                params=params,
                headers={"X-API-KEY": settings.enso_api_key},
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                body = await resp.json()
                if resp.status != 200:
                    raise EnsoError(resp.status, body)
                return body
```

`EnsoShortcutAdapter` is the only thing in `build_default_registry` for EVM:

```python
return AdapterRegistry(adapters=[
    EnsoShortcutAdapter(),       # EVM — primary, no fallback
    SolanaYieldBuilderAdapter(), # Solana — primary, no fallback
    WalletAssistantAdapter(),    # swaps / bridges / stake (legacy path)
])
```

### 2.4 Position-token registry

Enso routes by `tokenOut = position token address`. For each `(chain, protocol, asset_in)` we maintain a deterministic resolver:

```python
POSITION_TOKEN_RESOLVERS: dict[str, callable] = {
    "aave-v3":       resolve_aave_v3_atoken,       # known map per chain × asset
    "compound-v3":   resolve_compound_v3_comet,    # known map
    "uniswap-v3":    resolve_uniswap_v3_pool,      # eth_call to factory.getPool
    "sushiswap-v3":  resolve_sushiswap_v3_pool,
    "pancakeswap-v3": resolve_pancake_v3_pool,
    "aerodrome-slipstream": resolve_aerodrome_slip_pool,
    "curve":         resolve_curve_lp_token,       # pool address == LP token for stable
    "balancer":      resolve_balancer_bpt,         # pool address == BPT
    "yearn":         resolve_yearn_vault,
    "morpho":        resolve_morpho_market,
    "pendle":        resolve_pendle_market,
    "lido":          lambda chain, _: STETH_ADDRESS[chain],
    "rocket-pool":   lambda chain, _: RETH_ADDRESS[chain],
    # ... full matrix, ~70 entries
}
```

`resolve_uniswap_v3_pool` is a one-line `eth_call`:
```python
factory.getPool(token0, token1, fee_bps)  # returns address or 0x0
```
Cached in Redis for 24 h (pool addresses never change).

### 2.5 Solana sidecar contract

`services/solana-yield-builder/src/index.js` registers one adapter per protocol family:

```js
const adapters = {
  "raydium-amm":      require("./adapters/raydium-amm-zap"),       // Phase B.1
  "raydium-clmm":     require("./adapters/raydium-clmm"),          // Phase B.3
  "orca-whirlpools":  require("./adapters/orca-whirlpool"),        // Phase B.2
  "meteora-dlmm":     require("./adapters/meteora-dlmm"),          // Phase B.4
  "kamino-liquidity": require("./adapters/kamino-clmm"),           // Phase B.5
  "marinade":         require("./adapters/marinade"),              // shipped
  "jito":             require("./adapters/jito"),                  // shipped
  "sanctum":          require("./adapters/sanctum"),               // shipped
};
```

Each adapter exposes `async build({ asset, amount, user, extra }, { connection })` → returns `{ transactions: [{ b64, summary, simulation, warnings, protocolUrl }] }`.

### 2.6 ALT registry (Solana)

Deploy three address-lookup-tables once, hard-code in env:

- `ALT_CORE` (~50 entries): Jupiter program, Raydium AMM v4 program, Raydium CLMM program, Orca Whirlpool program, Meteora DLMM program, Kamino program, Token program, Token-2022 program, ATA program, System program, Compute budget program, sysvar accounts.
- `ALT_TOKENS_TOP50`: top 50 SPL mints (SOL, USDC, USDT, JitoSOL, mSOL, JLP, JTO, PYTH, W, JUP, BONK, WIF, ORCA, RAY, …).
- `ALT_TOKENS_TAIL` (refreshed weekly): next 200 by market cap.

Every Solana tx packs `addressLookupTableAccounts: [ALT_CORE, ALT_TOKENS_TOP50, ALT_TOKENS_TAIL]` into `TransactionMessage.compileToV0Message`. Wallets cache the ALT after the first signed tx — subsequent txs decode without RPC round-trips.

---

## 3. Phases (with code-level detail)

### Phase A — Enso activation + position-token registry (0.75 day)

**A.1 Fix EnsoClient header + pacing**

```python
# src/routing/enso_client.py
import asyncio, time, aiohttp
from src.config import settings

class EnsoClient:
    BASE = "https://api.enso.finance/api/v1"
    RATE_INTERVAL_S = 1.15
    _lock = asyncio.Lock()
    _last_call_at: float = 0.0

    async def _respect_rate_limit(self):
        async with self._lock:
            now = time.monotonic()
            wait = self.RATE_INTERVAL_S - (now - self._last_call_at)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call_at = time.monotonic()

    async def route(self, *, chain_id, token_in, token_out, amount_in,
                    from_addr, slippage_bps=100, extra_params=None):
        await self._respect_rate_limit()
        params = {
            "chainId": chain_id, "fromAddress": from_addr,
            "tokenIn": token_in, "tokenOut": token_out,
            "amountIn": str(amount_in), "slippage": slippage_bps,
        }
        if extra_params:
            params.update(extra_params)
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{self.BASE}/shortcuts/route", params=params,
                             headers={"X-API-KEY": settings.enso_api_key},
                             timeout=aiohttp.ClientTimeout(total=60)) as r:
                body = await r.json()
                if r.status != 200:
                    raise EnsoError(r.status, body)
                return body
```

**A.2 Position-token registry**

`src/defi/execution/adapters/enso_position_tokens.py` — 70+ entries covering the matrix. Stable / lending / vault tokens hardcoded; V3 pools resolved on-chain.

**A.3 On-chain pool resolver for V3**

```python
# src/data/v3_pool_resolver.py
UNISWAP_V3_FACTORY = {
    1: "0x1F98431c8aD98523631AE4a59f267346ea31F984",   # Ethereum
    8453: "0x33128a8fC17869897dcE68Ed026d694621f6FDfD", # Base
    42161: "0x1F98431c8aD98523631AE4a59f267346ea31F984", # Arbitrum
    137: "0x1F98431c8aD98523631AE4a59f267346ea31F984",   # Polygon
    10: "0x1F98431c8aD98523631AE4a59f267346ea31F984",    # Optimism
}
PANCAKE_V3_FACTORY = {56: "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865"}
AERODROME_SLIPSTREAM_FACTORY = {8453: "0x420DD381b31aEf6683db6B902084cB0FFECe40Da"}

async def resolve_v3_pool(*, chain_id, factory, token0, token1, fee_bps) -> str:
    selector = "0x1698ee82"  # getPool(address,address,uint24)
    data = selector + _addr32(token0) + _addr32(token1) + _u256(fee_bps)
    w3 = web3_for(chain_id)
    raw = w3.eth.call({"to": factory, "data": data})
    addr = "0x" + raw.hex()[-40:]
    if int(addr, 16) == 0:
        raise PoolNotFound(f"V3 factory {factory} has no pool for {token0}/{token1} fee={fee_bps}")
    return Web3.to_checksum_address(addr)
```

Cached in Redis (key = `v3_pool:{chain}:{factory}:{t0}:{t1}:{fee}`, TTL = 24 h).

**A.4 EnsoShortcutAdapter rewrite**

```python
# src/defi/execution/adapters/enso_shortcut.py
@dataclass
class EnsoShortcutAdapter:
    chains = frozenset({"ethereum", "polygon", "arbitrum", "optimism", "base",
                        "avalanche", "bsc", "linea", "gnosis", "zksync", "scroll"})
    protocols = frozenset({
        # AMMs
        "uniswap-v2", "uniswap-v3", "uniswap-v4",
        "sushiswap", "sushiswap-v3",
        "pancakeswap", "pancakeswap-v2", "pancakeswap-v3",
        "aerodrome", "aerodrome-slipstream",
        "velodrome", "velodrome-v1", "velodrome-slipstream",
        "camelot", "camelot-v3",
        "quickswap", "quickswap-v3",
        "trader-joe-v1", "trader-joe-v2",
        "baseswap",
        # Stables
        "curve", "curve-dex", "balancer", "balancer-v2", "balancer-v3",
        # Lending
        "aave-v3", "aave-v2", "aave", "compound-v3", "compound",
        "morpho", "morpho-blue", "spark", "moonwell", "venus",
        # Vaults / yield
        "yearn-finance", "yearn", "beefy", "convex-finance", "pendle",
        # LSTs (single-step deposits via Enso wrap path)
        "lido", "rocket-pool", "ether.fi-stake", "ether-fi", "frax-ether",
        "swell-network", "stader",
        # Auto-vault CLMM
        "gamma", "arrakis", "steer-protocol",
    })
    actions = frozenset({"supply", "deposit", "deposit_lp", "add_liquidity",
                         "provide_liquidity", "stake", "lend"})

    async def build(self, request: YieldBuildRequest) -> list[ExecutionStepV3]:
        token_out = await resolve_position_token(
            chain=request.chain, protocol=request.protocol,
            asset_in=request.asset_in, extra=request.extra or {},
        )
        client = EnsoClient()
        bundle = await client.route(
            chain_id=CHAIN_IDS[request.chain.lower()],
            token_in=ASSETS[request.chain.lower()][request.asset_in.upper()][0],
            token_out=token_out,
            amount_in=str(to_units(request.amount_in,
                                  ASSETS[request.chain.lower()][request.asset_in.upper()][1])),
            from_addr=request.user_address,
            slippage_bps=request.slippage_bps,
            extra_params=_v3_extra(request.extra),  # tickLower / tickUpper for V3
        )
        return [_step_from_bundle(bundle, request, token_out)]
```

**A.5 Drop direct adapters from registry**

```python
# src/defi/execution/capabilities.py
return AdapterRegistry(adapters=[
    EnsoShortcutAdapter(),
    SolanaYieldBuilderAdapter(),
    WalletAssistantAdapter(),
])
```
(`AaveV3SupplyAdapter`, `CompoundV3SupplyAdapter`, `CurveSingleSidedAdapter`,
`BalancerSingleAssetAdapter`, `UniswapV2DualTokenAdapter` remain in the tree as
reference, NOT registered.)

**A.6 `is_pool_link_action` whitelist update**

```python
EVM_ENSO_EXEC_PROTOCOLS = EnsoShortcutAdapter().protocols
# is_pool_link_action returns False for any (action in deposit-family, protocol in EVM_ENSO_EXEC_PROTOCOLS, chain in EVM_CHAINS)
```

**A.8 Any-token resolver (the "ANY tokens" requirement)**

The hardcoded `ASSETS` registry covers only ~30 tokens per EVM chain. To satisfy "ANY token", every code path that needs a token address / decimals / price MUST fall back to live on-chain or registry lookup. New module:

```python
# src/data/token_resolver.py
@dataclass(frozen=True)
class TokenInfo:
    address: str
    symbol: str
    decimals: int
    is_token_2022: bool = False        # Solana only
    price_usd: float | None = None

async def resolve_token(*, chain: str, ref: str) -> TokenInfo:
    """Resolve a token reference (symbol OR address) on any chain.

    Resolution order:
      1. In-process registry (KNOWN_TOKENS) — fast path for top ~30 / chain.
      2. Jupiter token list cache (Solana, ~3k mints) refreshed every 30 min.
      3. Coingecko `/coins/{chain}/contract/{address}` — symbol + decimals + price.
      4. On-chain ERC20.decimals() + ERC20.symbol() via eth_call (EVM).
         For Solana: getAccountInfo on the mint, decode SPL Mint layout for decimals,
         + check owner program for Token-2022 flag.
      5. If still unresolved → raise UnknownToken(ref, chain), card emits a
         structured `unknown_token` blocker rather than silent failure.

    Cached in Redis 24 h by (chain, address). Token symbol-only lookups also
    cached but invalidated when a swap fails decimals validation (sanity check).
    """
```

ERC20 calldata (no SDK needed):
```python
ERC20_DECIMALS_SELECTOR = "0x313ce567"   # decimals() -> uint8
ERC20_SYMBOL_SELECTOR   = "0x95d89b41"   # symbol()   -> string

async def erc20_decimals(w3, address: str) -> int:
    raw = await w3.eth.call({"to": address, "data": ERC20_DECIMALS_SELECTOR})
    return int(raw.hex(), 16) & 0xff
```

For Solana Token-2022 detection:
```python
async def is_token_2022(connection, mint: str) -> bool:
    info = await connection.get_account_info(PublicKey(mint))
    return str(info.owner) == "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
```

Plumbing:
- `EnsoShortcutAdapter.build` resolves `tokenIn` and `tokenOut` via this module — accepts a bare symbol or a `0x…` address.
- Solana sidecar's `pairAware.js` calls Jupiter's `/tokens` endpoint for unknown mints.
- Card preview shows resolved (symbol, decimals, price) so the user can verify the token before signing.

**Harness coverage:** add scenarios with long-tail tokens (`PEPE`, `SHIB`, `JUP`, `BONK`, `WIF`) and Token-2022 mints, asserting the resolver returns a valid `TokenInfo` and Enso / sidecar builds a real bundle.

**A.7 Harness scenarios — Phase A acceptance**

12 new conversations covering:
- `enso-aave-v3-eth`, `enso-aave-v3-base`, `enso-aave-v3-arbitrum`, `enso-aave-v3-polygon`
- `enso-compound-v3-eth`
- `enso-uniswap-v3-eth-usdc-weth-005`, `enso-uniswap-v3-base`, `enso-uniswap-v3-arbitrum`, `enso-aerodrome-slip-base`, `enso-pancake-v3-bsc`
- `enso-curve-3pool-eth`, `enso-balancer-bbausd-eth`
- `enso-yearn-usdc-eth`
- multi-turn `enso-refine-amount`, `enso-refine-chain`

Each turn asserts `card_type == execution_plan_v3` AND `steps[0].action == "enso_bundle"` AND `steps[0].transaction.to == bundle.tx.to` AND `sim_ok=True` against the funded Anvil fork (Phase D).

### Phase B — Solana SDK integrations (3 days, two parallel branches)

#### B.1 Raydium AMM v4 zap (1 day)

```js
// services/solana-yield-builder/src/adapters/raydium-amm-zap.js
const { Raydium } = require("@raydium-io/raydium-sdk-v2");
const { halfUsdValue, jupiterSwap, ALT_CORE, ALT_TOKENS } = require("../shared");

module.exports.build = async ({ asset, amount, user, extra }, { connection }) => {
  const raydium = await Raydium.load({ owner: new PublicKey(user), connection });
  const pool_info = await raydium.api.fetchPoolById({ ids: extra.pool_address });
  const pool_keys = await raydium.liquidity.getAmmPoolKeys(extra.pool_address);

  // pair-aware prep swap
  const half = halfUsdValue(amount);
  const swap_a = (asset === pool_info.mintA.address)
    ? null
    : await jupiterSwap(asset, pool_info.mintA.address, half, user);
  const swap_b = (asset === pool_info.mintB.address)
    ? null
    : await jupiterSwap(asset, pool_info.mintB.address, half, user);

  // build addLiquidity ix using SDK's computePairAmount + addLiquidityInstruction
  const { builder } = await raydium.liquidity.addLiquidity({
    poolInfo: pool_info, poolKeys: pool_keys,
    amountInA: new TokenAmount(/* from swap_a quote */),
    otherAmountMin: new TokenAmount(/* from swap_b quote * (1 - slippage) */),
    fixedSide: "a",
    txVersion: TxVersion.V0,
  });

  // pack everything: swap_a.instructions, swap_b.instructions, addLiquidity ixs
  const all_ixs = [
    ComputeBudgetProgram.setComputeUnitLimit({ units: 600_000 }),
    ComputeBudgetProgram.setComputeUnitPrice({ microLamports: await heliusPriorityFee() }),
    ...(swap_a?.instructions ?? []),
    ...(swap_b?.instructions ?? []),
    ...builder.instructions,
  ];

  const message = new TransactionMessage({
    payerKey: new PublicKey(user),
    recentBlockhash: (await connection.getLatestBlockhash()).blockhash,
    instructions: all_ixs,
  }).compileToV0Message([ALT_CORE, ALT_TOKENS]);

  const tx = new VersionedTransaction(message);
  // size check; split if > 1232 B
  if (tx.serialize().length > 1232) return splitIntoTwoSigs(/* … */);

  const sim = await connection.simulateTransaction(tx, { sigVerify: false });
  if (sim.value.err) throw new Error(`Raydium AMM sim failed: ${JSON.stringify(sim.value.err)}`);

  return { transactions: [{
    b64: Buffer.from(tx.serialize()).toString("base64"),
    summary: `Raydium AMM zap: ${asset} → ${pool_info.symbolA}-${pool_info.symbolB} LP`,
    description: `Single signed tx: prep-swap + addLiquidity, ALT-packed, sim-passed.`,
    receiptToken: pool_info.lpMint.address,
    feeUsd: 0.005,
    durationS: 25,
    warnings: ["Single-tx zap on Raydium AMM v4. Slippage cap 1%."],
    simulation: { ok: true, unitsConsumed: sim.value.unitsConsumed },
  }]};
};
```

#### B.2 Orca Whirlpools (1 day, parallel to B.1)

```js
// services/solana-yield-builder/src/adapters/orca-whirlpool.js
const { buildWhirlpoolClient, IncreaseLiquidityQuoteParam, alignTickToSpacing }
  = require("@orca-so/whirlpools-sdk");

module.exports.build = async ({ asset, amount, user, extra }, { connection }) => {
  const client = buildWhirlpoolClient(/* ctx */);
  const whirlpool = await client.getPool(extra.pool_address);
  const tickSpacing = whirlpool.getData().tickSpacing;
  const tickLower = alignTickToSpacing(extra.tick_lower, tickSpacing);
  const tickUpper = alignTickToSpacing(extra.tick_upper, tickSpacing);

  const quote = await whirlpool.getOpenPositionWithLiquidityQuote({
    inputToken: new PublicKey(asset === whirlpool.tokenAInfo.mint ? whirlpool.tokenAInfo.mint : whirlpool.tokenBInfo.mint),
    inputAmount: new BN(amount),
    tickLower, tickUpper,
    slippage: Percentage.fromFraction(1, 100),
  });

  const { positionMint, tx: openTxBuilder } = await whirlpool.openPositionWithLiquidity(quote, user);
  // optional prep-swap leg via Jupiter if input != either side
  // …
  // pack with ALT + ComputeBudget + priorityFee
  // …
  // persist positionMint in lp_positions (Phase E)
};
```

Position NFT mint persisted in `lp_positions` table for portfolio display.

#### B.3 Raydium CLMM (0.5 day, sequential after B.1)

Same SDK as B.1, `clmm` module. `raydium.clmm.openPositionFromBase` with tick alignment.

#### B.4 Meteora DLMM (0.5 day, parallel to B.3)

```js
// services/solana-yield-builder/src/adapters/meteora-dlmm.js
const DLMM = require("@meteora-ag/dlmm");

module.exports.build = async ({ asset, amount, user, extra }, { connection }) => {
  const dlmm = await DLMM.default.create(connection, new PublicKey(extra.pool_address));
  const { activeBin } = await dlmm.getActiveBin();
  const N = extra.bin_range ?? 30;
  const minBinId = activeBin - N;
  const maxBinId = activeBin + N;

  const strategy = chooseStrategy(extra.pool_type, extra.volatility); // Spot / Curve / Bid-Ask

  // pair-aware prep swap via Jupiter (asset → token X or Y as needed)
  // …

  const { instructions } = await dlmm.addLiquidityByStrategy({
    positionPubKey: extra.position ?? Keypair.generate().publicKey,
    user: new PublicKey(user),
    totalXAmount: new BN(/* from swap quote */),
    totalYAmount: new BN(/* from swap quote */),
    strategy: { strategyType: strategy, minBinId, maxBinId },
    slippage: 100,  // 1%
  });

  // pack + ALT + ComputeBudget + sim gate
};
```

#### B.5 Kamino vaults (0.5 day, parallel to B.3 / B.4)

```js
// services/solana-yield-builder/src/adapters/kamino-clmm.js
const { Kamino } = require("@kamino-finance/kliquidity-sdk");

module.exports.build = async ({ asset, amount, user, extra }, { connection }) => {
  const kamino = new Kamino("mainnet", connection);
  const strategy = await kamino.getStrategyByAddress(extra.strategy_address);
  const ix = await kamino.singleSidedDepositTokenA(strategy, user, new BN(amount));
  // single-sided is native — Kamino vault rebalances internally
  // pack + ALT + sim
};
```

#### B.6 ALT registry (parallel during whole Phase B)

`services/solana-yield-builder/src/alt-registry.js`:
- Boot script deploys 3 ALTs on first run.
- Stores PDAs in `services/solana-yield-builder/src/alt-addresses.json`.
- Production env vars: `ALT_CORE`, `ALT_TOKENS_TOP50`, `ALT_TOKENS_TAIL`.

#### B.7 Position tracking schema

```python
# src/storage/lp_positions.py
class LpPositionRow(Base):
    __tablename__ = "lp_positions"
    id = Column(Integer, primary_key=True)
    wallet_address = Column(String(64), nullable=False, index=True)
    chain = Column(String(20), nullable=False)
    protocol = Column(String(40), nullable=False)
    pool_address = Column(String(64), nullable=False)
    position_id = Column(String(80), nullable=False)   # tokenId or position-mint
    nft_contract = Column(String(64))                  # null on Solana
    tick_lower = Column(Integer)
    tick_upper = Column(Integer)
    liquidity_raw = Column(String(80))
    opened_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
```

**Acceptance:** every Solana matrix cell ships real SDK calldata. Sim-gate passes on funded mock wallet (Phase D). Position NFT / position-mint persists in `lp_positions`.

### Phase C — Range UI live data (1 day, parallel to A / B)

**C.1 Historical price fetcher**

```python
# src/data/price_history.py
COINGECKO_IDS = {"USDC": "usd-coin", "WETH": "ethereum", "WBTC": "wrapped-bitcoin", ...}

async def fetch_30d_hourly(symbol: str) -> list[tuple[int, float]]:
    cg_id = COINGECKO_IDS.get(symbol.upper())
    if not cg_id:
        return await birdeye_30d_hourly(symbol)  # Solana fallback
    url = f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart"
    async with aiohttp.ClientSession() as s:
        async with s.get(url, params={"vs_currency": "usd", "days": 30, "interval": "hourly"}) as r:
            data = await r.json()
            return [(int(p[0] / 1000), float(p[1])) for p in data["prices"]]
```

Cached in Redis 1 h.

**C.2 Empirical CDF over [0.5x, 2x]**

```python
# src/defi/range_metrics.py
def cdf_30d(token0_prices: list[float], token1_prices: list[float]) -> list[float]:
    ratios = [a / b for a, b in zip(token0_prices, token1_prices)]
    current = ratios[-1]
    lo, hi = 0.5 * current, 2.0 * current
    buckets = [0.0] * 100
    for r in ratios:
        if r < lo or r > hi:
            continue
        idx = int((r - lo) / (hi - lo) * 99)
        buckets[idx] += 1
    total = sum(buckets) or 1
    cumulative = []
    acc = 0
    for b in buckets:
        acc += b / total
        cumulative.append(round(acc, 4))
    return cumulative
```

**C.3 Base APR from real fee/TVL**

```python
def base_apr_pct(pool: EnrichedPool) -> float:
    if not pool.vol_24h_usd or not pool.tvl_usd:
        return pool.apy_base_pct
    fee_rate = pool.fee_tier_bps / 1e4
    daily_fee_usd = pool.vol_24h_usd * fee_rate
    return (daily_fee_usd * 365) / pool.tvl_usd * 100
```

**C.4 Plumb through to V3 card**

`build_yield_execution_plan` attaches:
```python
v3_card["market"] = {
    "base_apr_pct": base_apr_pct(pool),
    "reward_apr_pct": pool.apy_reward_pct or 0.0,
    "cdf_30d": await cdf_30d(token0_30d, token1_30d),  # length 100
}
```

Frontend `PoolDepositV3Card.tsx` already consumes `cdf_30d` — drop the canonical-default fallback now that real data ships.

**Harness assertion:** every `pool_deposit_v3` card has `len(market.cdf_30d) == 100` and `base_apr_pct > 0` whenever `tvl_usd > 0`.

### Phase D — Funded wallet simulator (1.5 days, parallel to B)

**D.1 EVM Anvil fork**

```python
# tests/adversarial/anvil_fork.py
import subprocess, atexit
class AnvilFork:
    def __init__(self, chain_id, fork_url, port):
        self.proc = subprocess.Popen([
            "anvil",
            "--fork-url", fork_url,
            "--chain-id", str(chain_id),
            "--port", str(port),
            "--block-time", "1",
            "--no-cors",
        ], stdout=subprocess.DEVNULL)
        self.rpc = f"http://127.0.0.1:{port}"
        atexit.register(self.proc.terminate)

    async def fund_wallet(self, addr, eth_wei, erc20_tokens: dict[str, int]):
        # anvil_setBalance
        await self._rpc("anvil_setBalance", [addr, hex(eth_wei)])
        # anvil_setStorageAt per ERC20 balance slot
        for token, amount_raw in erc20_tokens.items():
            slot = BALANCE_SLOT_REGISTRY[token]
            key = keccak256(encode(["address", "uint256"], [addr, slot]))
            await self._rpc("anvil_setStorageAt", [token, hex_pad(key), hex_pad(amount_raw)])
```

`BALANCE_SLOT_REGISTRY` maps top 30 ERC20s per chain to their storage slot (Foundry's `forge inspect` finds these; we hardcode).

**D.2 Sim runner**

```python
# tests/adversarial/wallet_simulator.py
class WalletSimulator:
    def __init__(self, mode="fork"):
        self.mode = mode  # "fork" | "mock"
        self.forks: dict[int, AnvilFork] = {}

    async def simulate_evm(self, step):
        if self.mode != "fork":
            return await self._eth_call_public(step)
        fork = self._fork_for(step.chain_id)
        await fork.fund_wallet(self.evm_address, ETH_10, {USDC: USDC_10K, USDT: USDT_10K, ...})
        # eth_call against fork
        try:
            fork.web3.eth.call({"to": step.to, "data": step.data, "value": step.value, "from": self.evm_address})
            return StepSimResult(ok=True, sim_ok=True, benign=False)
        except Exception as e:
            return StepSimResult(ok=False, error=str(e))
```

**D.3 Solana simulateTransaction with account replacements**

Helius `simulateTransaction` accepts `accounts: { encoding: "base64", addresses: [...] }` and `replacements` to inject fake balances. Use that for funded sim. Fallback: `solana-test-validator --clone <pool_addresses>` for the harness when Helius is unavailable.

**D.4 Harness CLI flag**

```bash
python scripts/validate_pool_exec.py --sim-mode=fork
```

`--sim-mode=fork` (default) requires every executable tx to show `sim_ok=True && benign=False`. `--sim-mode=mock` keeps the existing public-RPC + benign-revert tolerance for quick smoke runs.

**Acceptance:** every harness turn that builds a tx shows `sim_ok=True, benign=False`.

**D.5 Error decoder module**

```python
# src/defi/execution/error_decoder.py
EVM_ERROR_MAP = {
    "STF":                       "Insufficient balance — your wallet doesn't hold enough of the input token.",
    "TF":                        "Transfer failed — token contract refused the transfer.",
    "InsufficientLiquidity":     "Pool liquidity too thin for this size.",
    "PriceSlippageCheckFailed":  "Price moved beyond your slippage tolerance. Refresh quote and try again.",
    "STE":                       "Sweep token failed — Universal Router couldn't refund leftover dust.",
    "0x6f6e6c79":                "OnlyOwner — caller is not authorized for this admin function.",
    # … 4byte.directory lookup at runtime for unknown selectors
}
SOLANA_ANCHOR_ERRORS = {
    6000: "Slippage check failed; price moved during the transaction window.",
    6001: "Pool is paused for upgrades.",
    6002: "Tick range invalid (must align to pool tickSpacing).",
    6003: "Insufficient liquidity in the chosen range.",
    # … per-protocol Anchor error catalogs
}

def decode_evm_error(raw: str | Exception) -> str:
    text = str(raw).lower()
    for code, msg in EVM_ERROR_MAP.items():
        if code.lower() in text:
            return msg
    if "0x" in text:
        # 4byte.directory async lookup for the bare selector
        return f"On-chain revert (decoder will surface code shortly): {text[:120]}"
    return f"Transaction would revert: {text[:160]}"
```

Wired into both the sim path (Phase D failures) and into the live `receipt_watcher` so that a tx that lands but reverts surfaces a human reason in the card instead of a hex blob.

### Phase E — DB tool args persistence (0.5 day, parallel to A / B)

**E.1 Migration**

```python
# alembic migration: add tool_args_json + tool_name to AgentChatMessageRow
op.add_column("agent_chat_messages", sa.Column("tool_args_json", sa.Text, nullable=True))
op.add_column("agent_chat_messages", sa.Column("tool_name", sa.String(80), nullable=True))
```

**E.2 Persist after each turn**

```python
# in simple_runtime.run_ephemeral_turn after dispatch:
if matched_intent:
    await db.add_agent_message(
        chat_id=..., role="assistant",
        content=card_summary, tool_args_json=json.dumps(tool_input),
        tool_name=intent_name,
    )
```

**E.3 LP refinement reads from tool_args_json**

```python
last_args = await db.last_agent_tool_args(chat_id)
if last_args:
    prior_intent_override = (last_args["tool_name"], _merge_delta(last_args["args"], delta))
```

Drops the regex-on-card-summary hack. Backward-compatible: if column is null (older row), fall back to current regex extraction.

**Acceptance:** every refinement turn ("make it $X", "actually use USDT", "try Base") rebuilds via `tool_args_json` lookup; harness adds a `multi-turn-replay-with-tool-args` scenario asserting the rebuild matches the original intent.

### Phase F — Observability (0.5 day, parallel to anything)

**F.1 Loki scrape**

`/etc/promtail/promtail.yml` on VPS reads `journalctl -u caddy` + container logs, ships to Grafana Cloud Loki (free tier).

**F.2 Grafana dashboard**

`infra/grafana/pool-exec.json` panels:
- Tx-success-rate per protocol per chain (last 24 h / 7 d)
- Sim-pass rate (funded fork)
- Enso `/shortcuts/route` latency p50 / p95 / p99
- Solana sidecar build-error rate
- Refinement-override hit rate
- Top 10 most-deposited pools (by sig-count)

**F.3 Sentry**

`src/api/middleware/sentry.py` initializes Sentry SDK. Errors tagged `phase=pool_exec`, `protocol=<slug>`, `chain=<name>`.

**F.4 Realtime card update via receipt watcher**

`src/agent/receipt_watcher.py` already polls signature confirmations. Wire its updates into the SSE stream so the open execution card transitions through `pending → confirmed → finalized` states in real time:

- On `tx.submitted` → patch card `status: "submitted"`, show explorer link.
- On `getSignatureStatuses` returns `confirmed` → patch card `status: "confirmed"`, decode logs.
- On `finalized` → patch card `status: "completed"`, attach position-NFT mint / tokenId, store row in `lp_positions`.
- On revert / Anchor error → `error_decoder.decode_evm_error()` populates `card.error_human`.

Frontend SSE handler in `web/lib/sse-client.ts` already merges card-patch events; just need to emit them from receipt_watcher (currently only the initial card is sent — patch events are dropped).

---

## 4. Roll-out order and parallelism

```
  Phase A (Enso) ─┐
                  ├─ Phase D (Anvil) ─┐
  Phase C (CDF)  ─┤                   │
  Phase E (DB)   ─┤                   ├─ Harness expansion → Phase F → Final tester
  Phase F (Obs)  ─┘                   │
                                      │
  Phase B.1 (Raydium AMM) ────┐       │
  Phase B.2 (Orca)            ├─ B.6 ─┘
  Phase B.4 (Meteora DLMM)    │
  Phase B.5 (Kamino)          │
                              │
  Phase B.3 (Raydium CLMM)  ──┘  (sequential after B.1 uses same SDK init)
```

**Sequential total: 5 days.** Parallel pairs `(A, C, E, F)` ‖ `(B.1, B.2, B.4, B.5)` ‖ B.3 ‖ D → **~3.5 days**.

---

## 5. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Enso 1 rps free-tier chokes harness | High | Medium | 1.15 s pacing in `EnsoClient` global mutex; document paid-tier upgrade if production load > 10 rps |
| Enso doesn't index a brand-new pool | Low | Medium | Card emits structured `unsupported_pool` blocker with deep-link to protocol app (no silent fallback) |
| Enso outage > 5 min during tester walkthrough | Medium | High | Health-check at `/shortcuts/route` with simple ping every 30 s; surface as a banner on staging; do NOT silently route to direct adapters |
| Raydium SDK v2 breaking change mid-session | Medium | Medium | Pin exact version `0.1.106-rc.5`; mock SDK in unit tests |
| Solana tx exceeds 1232 B even with ALT | Medium | Low | Detect at build, split into 2 sigs, surface as a 2-signature flow in the card preview |
| CoinGecko 30-day candles rate-limited | Low | Low | Birdeye fallback (key already in env); cache in Redis 1 h |
| Anvil fork crashes mid-harness | Low | Medium | Auto-restart in `WalletSimulator._fork_for`; retry once |
| Alchemy / Infura free tier hits 100k call cap | Medium | Low | Helius for Solana, Alchemy paid bound to staging only; production uses dedicated infra RPC |
| Tester finds a long-tail pool we didn't index | Medium | Medium | Pool resolver (Phase A.3) handles arbitrary V3 / Curve / Balancer addresses; sidecar Solana adapters accept arbitrary pool_address |
| Position NFT confusion ("where's my LP?") | Low | Low | Card explains: "Your position is NFT ID #1234 in your wallet — needed for close/withdraw" |

---

## 6. Original-prompt satisfaction matrix

Every line of the initial prompt mapped to exactly one phase. No requirement uncovered.

| Original prompt line | Phase that satisfies it |
|---|---|
| "I want you to describe in maximum detail how pool execution should work" | §1 DeFi primer + §2 architecture in this doc |
| "in different scenarios (V2/V3/stable, single-sided, EVM+Solana)" | §1.1-§1.6, Phase A (EVM matrix), Phase B (Solana matrix) |
| "technical part — which protocol — Enso or another" | §2.1 single-path decision: Enso for EVM, direct SDK for Solana |
| "visual part of report cards — range selector, APR change with range" | §1.5 wireframe + Phase C live CDF + already-shipped `PoolDepositV3Card.tsx` |
| "compare research, the other conversation, and our system" | v1 plan §2 gap table + this doc's §0 "why v3" |
| "write full plan and report on what should be fixed" | This document |
| "deploy onto our main VPS — ilyonai.com domain" | Per user revision: pool-exec on staging.ilyonai.com, no-exec on ilyonai.com |
| "run strict turn-to-turn verification, 30+ conversations" | Phase A.7 + harness expansion (80+ turns target) |
| "if one shows the issue — fix it immediately. Do not stop until perfect" | Continuous deploy loop already in place; harness re-runs after every commit |
| "upgrade transaction and wallet simulation" | Phase D Anvil fork EVM + Helius `simulateTransaction` Solana |
| "100% confirm tester will get right results" | Phase D acceptance: every executable tx shows `sim_ok=True && benign=False` |
| "deposit money and add liquidity in one click to ANY pool possible" | Phase A (every EVM pool family via Enso, one Permit2 sig) + Phase B (every Solana pool family via SDK, 1 sig when fits 1232 B, else 2 sigs after ALT) |
| **"ANY token" — long-tail / memes / Token-2022** | **Phase A.8 any-token resolver: ERC20.decimals() + Coingecko / Jupiter token list + Token-2022 detection** |
| "Please DO NOT STOP until everything is perfectly working" | Plan's self-check §8 has zero exceptions |

---

## 7. Acceptance gate (the bar for "satisfied")

The plan is satisfied when **every one** of the following is true on `https://staging.ilyonai.com`:

1. `python scripts/validate_pool_exec.py --sim-mode=fork` returns **100 % pass**, ≥ 80 turns, ≥ 60 conversations, every executable sim showing `sim_ok=True && benign=False`.
2. Every cell of the matrix in §1 (8 chains × 5 EVM pool families + 1 Solana chain × 6 Solana pool families = ~46 cells) returns a single signed Enso bundle (or 1-2 Solana sigs after ALT pack).
3. Tester walks `staging.ilyonai.com` through every cell: Raydium AMM, Raydium CLMM, Orca Whirlpools, Meteora DLMM, Kamino, Marinade/Jito/Sanctum LSTs (Solana); Uniswap V2 + V3 + V4, SushiSwap V2 + V3, Pancake V2 + V3, Aerodrome Slipstream, Velodrome V1 + Slipstream, Curve 3pool + crvUSD, Balancer bb-aUSD + wstETH/WETH, Aave V3, Compound V3, Yearn, Morpho, Pendle, Lido, RocketPool (EVM). For each cell, the tester signs ONE transaction (or 1-2 Solana sigs when tx-size forces a split) and confirms an on-chain LP position appears in their wallet within 30 seconds.
4. README + `docs/ARCHITECTURE_LIVE.md` updated to describe the live execution surface (no aspirational fiction).
5. Grafana dashboard live with per-protocol tx-success-rate, sim-pass-rate, Enso p95 latency. Sentry capturing real errors tagged `phase=pool_exec`.

---

## 8. Self-check before declaring done

- [ ] Phase A: `EnsoClient` uses `X-API-KEY`, 1.15 s pacing, position-token registry covers full matrix.
- [ ] Phase A: `is_pool_link_action` returns False for every (EVM chain, Enso-supported protocol, deposit-family action).
- [ ] Phase A: direct adapters (Curve / Balancer / V2-dual / Aave / Compound) NOT registered in `AdapterRegistry`.
- [ ] Phase A.8: any-token resolver returns valid `TokenInfo` for arbitrary ERC20 address / Solana mint / Token-2022; resolves symbol, decimals, price; card preview shows resolved metadata before sign.
- [ ] Phase B.1-B.5: every Solana adapter ships real SDK calldata, sim-passes on funded mock.
- [ ] Phase B.6: `ALT_CORE` / `ALT_TOKENS_TOP50` deployed on mainnet; addresses in staging env.
- [ ] Phase B.7: `lp_positions` rows created on every successful V3/CLMM mint.
- [ ] Phase C: real `cdf_30d` (len 100) ships in every `pool_deposit_v3` card. Canonical fallback removed from frontend.
- [ ] Phase D: `WalletSimulator(mode="fork")` runs every harness turn against Anvil; `sim_ok=True && benign=False`.
- [ ] Phase E: `tool_args_json` column live; refinement reads from it; older rows fall back to regex hint.
- [ ] Phase F: Grafana dashboard live; Sentry tagging real errors.
- [ ] Phase D.5: error decoder maps every observed EVM revert + Solana Anchor error to a human sentence; the card shows it (not a hex blob) on failure.
- [ ] Phase F.4: receipt-watcher patches the open card with `submitted → confirmed → finalized` events in real time; position NFT mint persisted on finalized.
- [ ] Harness: ≥ 80 turns / ≥ 60 conversations, **100 % pass** on staging.
- [ ] Tester walkthrough on `staging.ilyonai.com`: every cell signs in one click, position appears on-chain.
- [ ] README + `docs/ARCHITECTURE_LIVE.md` reflect the live state.

When every box ticks, the original prompt is verbatim satisfied and the plan is done.
