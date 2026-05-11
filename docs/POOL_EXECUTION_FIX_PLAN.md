# Pool Execution — Deep Diagnosis & Fix Plan

**Date:** 2026-05-11
**Branch:** `main` (with-exec)
**Scope:** Liquidity-pool deposits across EVM + Solana
**Audience:** Tester confirms LP execution is completely broken — wrong tokens, wrong amounts, no successful deposits across any chain.

---

## 0. TL;DR

LP execution is broken because the system treats pool deposits as if they were swaps. There is no zap pipeline (single-token → multi-token split → LP add), no V3 range handling, no decimals discipline, and no pre-flight simulation. Six interlocking defects cause every observed failure:

1. **EVM LP builder calls Enso with one token** and lets Enso "figure it out." Enso cannot mint Uniswap V3 positions (NFTs) for arbitrary pools and silently routes the deposit to an Aave aUSDC reserve or rejects, depending on the pool. The user sees a "deposit" card but the on-chain reality is wrong.
2. **Solana LP "deposits" are only prep swaps.** The Raydium and Orca adapters swap half the input into USDC or SOL and tell the user to finish in the protocol UI. The card is labeled `Deposit Lp` even though no LP add tx exists.
3. **The prep-swap assumes every pool is USDC/SOL.** For `WSOL-AURA` it swaps half the WSOL into USDC — user ends up with WSOL + USDC, not WSOL + AURA, and cannot deposit.
4. **Amounts flow as Python `float` end-to-end.** `int(amount) / 10**decimals` produces IEEE-754 floats which JSON-serialize as `0.1111111111111111`. The display is broken and the precision is lost — same float that goes into the tx.
5. **No V3 range selection exists.** Uniswap V3 / Raydium CLMM / Orca Whirlpool positions require `tickLower`, `tickUpper`, `tickSpacing`, fee tier, and sqrtPriceX96 math. None of this exists in our code. V3 LPs are hardcoded to route to aUSDC instead.
6. **No pre-flight simulation.** No `eth_call`, no `simulateTransaction`. The user signs blind. Reverts only surface when the tx is already on-chain and gas is burned.

This document specifies the system that should exist, what to build, in what order, and how we will validate it.

---

## 1. How Pool Deposits Should Work — The Canonical Pipeline

Every deposit, regardless of protocol or chain, must traverse seven stages. Today we skip three of them entirely.

### Stage 1 — Typed Intent (LLM layer)

The LLM emits a strict JSON tool call. No string parsing. No regex slop. The schema:

```json
{
  "action": "lp_deposit",
  "pool_id": "c2f18cd1-...",
  "input_token": "USDT",
  "input_amount_usd": 10,
  "preferred_range": { "kind": "balanced" | "narrow" | "wide" | "full" | { "lower_pct": -10, "upper_pct": 10 } },
  "preferred_slippage_bps": 50
}
```

Status today: partially exists via `execute_pool_position` / `build_yield_execution_plan`. The tool args do not carry range preference. Range must be added as a first-class field.

### Stage 2 — Pool Resolution & Enrichment

Pool ID → full on-chain state. DefiLlama provides ranking metadata but not the fields we need to build a transaction:

| Field | Source |
|---|---|
| `token0.address`, `token0.decimals`, `token0.symbol` | On-chain (`getAccountInfo` / `eth_call` `decimals()`) |
| `token1.address`, `token1.decimals`, `token1.symbol` | On-chain |
| `pool_address` | On-chain or DefiLlama metadata |
| `pool_type` | V2 / V3 / DLMM / stable / weighted (must be classified) |
| `fee_tier_bps` (V3 only) | On-chain |
| `tick_spacing` (V3 only) | On-chain |
| `current_tick`, `sqrt_price_x96` (V3 only) | On-chain |
| `current_price` (human) | Derived from sqrtPriceX96 + decimals |
| `reserve0`, `reserve1`, `lp_total_supply` (V2 only) | On-chain |
| `serum_market_id` (Raydium AMM only) | Raydium API |
| `vault_token_accounts` (Solana pools) | Raydium / Orca API |

Status today: this layer **does not exist**. Pool data is read from DefiLlama and passed downstream without on-chain enrichment.

### Stage 3 — Strategy Router

Decide what kind of transaction(s) to build:

| Pool type | Single-sided strategy |
|---|---|
| V2 (Raydium AMM, Uniswap V2, Sushi V2, Pancake V2) | Two swaps (input → token0 half, input → token1 half), then `addLiquidity` with slippage cap. |
| V3 / CLMM (Uniswap V3, Pancake V3, Raydium CLMM, Orca Whirlpools) | Compute optimal token0:token1 ratio for the chosen range, two swaps, then `mint` position with tickLower/tickUpper aligned to tickSpacing. |
| DLMM (Meteora) | Compute bin distribution, deposit per-bin (defer to phase 5 — niche). |
| Stable (Curve, Balancer weighted, Saber) | Single-sided supported natively by the pool. `add_liquidity([0, X, 0])` — no internal swap needed. |
| Auto-vaults (Kamino, Gamma, Arrakis, Beefy) | Single-token deposit handled by the vault. One tx. Preferred for low-value deposits. |

Status today: no such router exists. Every protocol is treated identically via the `_build_deposit_lp_tx` Enso wrapper or the Solana sidecar's prep-swap stub.

### Stage 4 — Quote & Route

Get firm quotes for each swap leg, compute exact amount-in / amount-out per step, calculate slippage caps, gas estimates, priority fees.

- EVM swap leg: Enso quote, 0x quote, or 1inch — pick the cheapest with depth check.
- Solana swap leg: Jupiter quote.
- V3 LP math: `@uniswap/v3-sdk` `Position.fromAmounts()` or Orca `increaseLiquidityQuoteByInputToken`.
- V2 LP math: read reserves, compute optimal pair using `getAmountsIn` on the router.
- Stable pool: read pool `get_dy` for sanity, use `add_liquidity` with `min_lp` slippage cap.

### Stage 5 — Simulation (mandatory, blocking)

Before any card with a `Sign` button reaches the user, every transaction must be simulated:

- **EVM:** `eth_call` against pending block with the from-address override. If revert: extract the reason string from the trace and surface it on the card. Use `eth_estimateGas` for the gas number, not a hardcoded default.
- **Solana:** `simulateTransaction` with `sigVerify: false`, `commitment: 'processed'`, `replaceRecentBlockhash: true`, `accounts: { encoding: 'base64', addresses: [...] }`. Inspect `err`, log decoded program errors, surface to user.

If any step fails simulation, the card shows a clear error and does **not** offer a sign button.

Status today: only post-signature `verify` exists for Solana. No EVM simulation at all. **This is the single most damaging gap** because the user finds out the tx is broken after they paid gas.

### Stage 6 — Report Card

A typed, structured card the frontend renders deterministically. Not a markdown blob. Not a JSON dump. A specific component tree per pool type — see section 4.

### Stage 7 — Sign → Submit → Track

- For Solana zaps that don't fit in one tx (typical), produce a sequence and let the wallet sign each in order, gating step N+1 on step N's finalization.
- For EVM, use Permit2 where supported (Uniswap, Universal Router, Aave V3) to collapse approve+deposit to one signature. Fall back to legacy approve flow with the classic-USDT zero-reset for tokens that need it.
- Track via WebSocket (Solana signature subscribe, EVM `eth_subscribe newHeads` + receipt poll) and update the card in real time.

---

## 2. Scenarios — Exactly What Should Happen

### Scenario A: User has USDT, wants liquidity in USDC/SOL on Solana via Raydium AMM

```
Intent: deposit_lp { pool=raydium-amm USDC/SOL, input=USDT, input_usd=10 }

Stage 2 — Enrich:
  token0 = USDC (6 dec, EPjFW...)
  token1 = SOL  (9 dec, So111...)
  pool   = USDC/SOL AMM v4
  type   = V2 (full-range AMM)
  ratio  = 50/50

Stage 3 — Strategy: V2 single-sided zap
  amount_to_token0 = 5 USD worth of USDT → USDC (Jupiter quote)
  amount_to_token1 = 5 USD worth of USDT → SOL  (Jupiter quote)
  addLiquidity(amount0_actual, amount1_actual, min_lp = expected * 99.5%)

Stage 4 — Quotes:
  Jupiter quote 1: 5 USDT → ~5.0 USDC
  Jupiter quote 2: 5 USDT → ~0.032 SOL
  Raydium addLiquidity: expect ~10 USD of LP tokens

Stage 5 — Simulate:
  Pack: [swap1 ix, swap2 ix, addLiquidity ix] under ALT
  If size > 1232 bytes -> split into 2 txs (swaps bundled, LP add second)
  simulateTransaction -> verify all succeed

Stage 6 — Card:
  Header: "Add liquidity to Raydium USDC/SOL"
  Snapshot: current price 1 SOL = 152.34 USDC, TVL $X, 24h vol $Y, fee 0.25%
  Position preview:
    You deposit: 10.00 USDT (~$10.00)
    Will become:
      5.27 USDC
      0.0307 SOL
    Expected LP tokens: 0.000142 RLP
    Daily yield estimate: $0.0098 (APY 35.7%)
  Route:
    1. Jupiter swap 5 USDT → 5.00 USDC
    2. Jupiter swap 5 USDT → 0.0307 SOL
    3. Raydium addLiquidity → 0.000142 RLP
    [pack to 1 tx via ALT if size allows]
  Sign button -> Phantom prompt for 1 or 2 signatures
```

### Scenario B: User has USDT, wants liquidity in USDC/WETH on Uniswap V3 Ethereum, narrow range

```
Intent: deposit_lp { pool=uni-v3 USDC/WETH 0.05%, input=USDT, input_usd=1000, range=narrow }

Stage 2 — Enrich:
  fee_tier = 500 (0.05%)
  tick_spacing = 10
  current_tick = 195420
  sqrt_price_x96 = ...
  current_price = 1 ETH = 3210.45 USDC

Stage 3 — Strategy: V3 zap
  range narrow = ±5% => price band [3050, 3372]
  Compute tickLower, tickUpper from price band, aligned to tick_spacing
  Compute optimal token0/token1 ratio for that range vs current price
    -> e.g. 47% USDC, 53% WETH (typical for slightly skewed range)

Stage 4 — Quotes:
  Permit2 sign for USDT spend
  Universal Router:
    swap 470 USDT -> ~470 USDC
    swap 530 USDT -> ~0.1652 WETH
    NonfungiblePositionManager.mint(
      token0=USDC, token1=WETH, fee=500,
      tickLower=193410, tickUpper=197430,  -- aligned
      amount0Desired=470e6, amount1Desired=0.1652e18,
      amount0Min=, amount1Min= (1% slippage),
      recipient=user, deadline=now+5min
    )
  Or call Enso /shortcuts/route with positionManager target
  Or use the Permit2-aware Universal Router multicall

Stage 5 — Simulate:
  eth_call full multicall, capture revert reason if any
  eth_estimateGas

Stage 6 — Card:
  Header: "Add liquidity to Uniswap V3 USDC/WETH 0.05%"
  Range selector:
    Quick presets: Narrow ±5% | Balanced ±10% | Wide ±25% | Full
    Slider with two handles, current price marker
    Live recompute on slider drag (no backend round-trip):
      Capital efficiency: 7.2x
      In-range probability (7d): 68%
      Expected APR @ this range: 47.3%
      Comparison table (other ranges)
  Position preview:
    Deposit: 1000 USDT
    Becomes: 470 USDC + 0.1652 WETH
    Expected daily yield: $1.30
    Expected position NFT id: (issued after mint)
  Route:
    1. Permit2 sign USDT spend (off-chain signature, no gas)
    2. Universal Router multicall (swap + swap + mint)
  Sign button -> MetaMask single signature for the multicall
```

### Scenario C: User has USDC, wants 3pool on Curve (stable)

```
Intent: deposit_lp { pool=curve-3pool, input=USDC, input_usd=500 }

Stage 3 — Strategy: stable single-sided NATIVE
  Curve 3pool accepts add_liquidity([0, X, 0], min_lp) -- swap internal
  No external swap needed

Stage 4:
  approve(3pool, 500e6 USDC)
  3pool.add_liquidity([0, 500_000_000, 0], min_lp = 498.5e18)

Stage 5: eth_call both calls succeed

Stage 6 — Card:
  Simple "Supply 500 USDC to Curve 3pool"
  Position preview: ~498.7 3CRV tokens, APR 4.2%
  Two steps: approve, add_liquidity (or single Permit2-style if supported)
```

### Scenario D: User has SOL, wants Orca Whirlpool USDC/SOL with default range

```
Intent: deposit_lp { pool=orca-whirlpool USDC/SOL, input=SOL, input_usd=100, range=balanced }

Strategy: V3 CLMM zap on Solana
  Use @orca-so/whirlpools SDK:
    pool_state = await whirlpool.fetch(poolAddress)
    quote = increaseLiquidityQuoteByInputToken(
      inputToken=SOL,
      inputAmount=lamports,
      tickLower, tickUpper,
      slippageTolerance=Percentage.fromFraction(5, 1000),
      pool_state
    )
  This returns required amount0 and amount1.
  swap half via Jupiter into USDC up to quote.tokenMaxA
  open position via Whirlpools SDK

Pack: swap ix + open_position_with_metadata ix + increase_liquidity ix into ALT-using tx
If > 1232 bytes -> 2 txs (Phantom shows 2 prompts)

Card: like Scenario B but with Solana visuals + position NFT.
```

### Scenario E: User has USDC, wants single-token deposit, doesn't want to manage range — Kamino vault

```
Intent: deposit_lp { pool=kamino-usdc-sol-vault, input=USDC, input_usd=200 }

Strategy: Auto-vault single-sided (real)
  Use Kamino's signable transaction REST OR @kamino-finance/kliquidity-sdk
  vault.deposit(USDC, 200_000_000, user)
  Vault internally handles the swap + position management

One tx, one signature, no range to pick.
```

### Scenario F: Range comparison table (V3 card UX)

Show this in every V3 card so the user understands the trade-off:

```
±5%    APR 187%   eff 14.0x  in-range(7d) 52%
±10%   APR 124%   eff  7.2x  in-range(7d) 78%   ← selected
±25%   APR  58%   eff  2.9x  in-range(7d) 94%
Full   APR  18%   eff  1.0x  in-range(7d) 100%
```

Clicking a row reconfigures the slider and recomputes the position preview.

---

## 3. Provider Matrix — Which API for Which Pool

| Chain | Pool type | Primary provider | Fallback | Why |
|---|---|---|---|---|
| Ethereum / L2 | V2 (Uni V2 forks) | 0x for swap leg + direct Router contract | 1inch | Universal, no LP-specific provider needed |
| Ethereum / L2 | V3 / CLMM | **Enso** for bundled mint | `@uniswap/v3-sdk` direct call to `NonfungiblePositionManager` + Universal Router for swaps | Enso bundles approve+swap+mint; SDK as fallback when Enso pool unsupported |
| Ethereum / L2 | Stable | Direct Curve / Balancer contracts | — | Native single-sided, no aggregator needed |
| Ethereum / L2 | Auto-vault | Gamma, Arrakis, Steer SDKs | Beefy ZapRouter | Single-sided handled by vault |
| Solana | AMM v2 (Raydium AMM) | Jupiter swap legs + `@raydium-io/raydium-sdk-v2` `liquidity.addLiquidity()` | Raydium REST `/transactions/add-liquidity` if available | Native pair-tokens deposit |
| Solana | CLMM (Raydium CLMM) | `@raydium-io/raydium-sdk-v2` `clmm.openPosition` | — | Range NFT, no aggregator covers |
| Solana | Whirlpool | `@orca-so/whirlpools` SDK | `@orca-so/whirlpools-sdk` legacy | Native CLMM |
| Solana | Kamino vault | **Kamino REST `/transactions/deposit`** | `@kamino-finance/kliquidity-sdk` | Real auto-vault, single-sided |
| Solana | DLMM (Meteora) | `@meteora-ag/dlmm` SDK | — | Niche, phase 5 |

We replace the current "everything routes through Enso" pattern with one builder per pool family. The Solana sidecar already has the file structure; it needs real LP-add logic, not prep-swap stubs.

---

## 4. Report Card Specification (V3 reference design)

### Sections

1. **Header strip:** action title (`Add liquidity to <protocol> <pair> <fee%>`), status pill, risk pill (low/medium/high), gas estimate, chain.
2. **Pool snapshot:** current price (human), TVL, 24h volume, fee tier, current APR baseline.
3. **Range selector (V3 only):**
   - Bar chart of historical price (7d or 30d) as backdrop.
   - Two draggable handles for `lower_pct` / `upper_pct`.
   - Current-price marker (vertical line) clamped to bar center.
   - Quick presets: `Narrow ±5%` / `Balanced ±10%` / `Wide ±25%` / `Full`.
   - **Live metrics** recomputed on every drag (frontend only):
     - Capital efficiency (closed-form)
     - In-range probability (precomputed 7d cumulative distribution sent by backend; frontend interpolates)
     - APR @ range = base_apr × capital_efficiency × in_range_probability + reward_apr
     - Comparison table (four rows)
4. **Position preview:** input → token0 + token1 split, expected LP/position id, expected daily/30d yield, slippage absorbed.
5. **Ordered route:** numbered steps with per-step status (`pending` / `simulated` / `signed` / `confirmed` / `failed`). Each step shows source asset, destination asset, router, wallet, gas. V3 steps show tickLower/tickUpper.
6. **Advanced (collapsed):** slippage override, priority fee override, MEV protection toggle (EVM), deadline.
7. **Sign button** with all-or-nothing semantics; disabled while simulation pending, errored if simulation failed, with clear error text.

### Frontend math (no backend round-trip)

```ts
// All math on the frontend so slider feels instant
function capitalEfficiency(pLower: number, pCurrent: number, pUpper: number) {
  if (pCurrent <= pLower || pCurrent >= pUpper) return 1; // out of range -> 1x
  return 1 / (1 - Math.sqrt(pLower / pUpper));
}

function inRangeProbability(pLower: number, pUpper: number, cdf: number[]) {
  // cdf: precomputed 100-bucket CDF of historical price ratio
  return cdfLookup(pUpper, cdf) - cdfLookup(pLower, cdf);
}

function expectedAPR(base: number, ratio: { lower: number; current: number; upper: number }, probability: number, rewards = 0) {
  const eff = capitalEfficiency(ratio.lower, ratio.current, ratio.upper);
  return base * eff * probability + rewards;
}
```

Backend ships `base_apr`, `current_price`, `cdf[]`, and `rewards_apr` once when the card mounts. Slider drags never round-trip.

### Card payload schema (new card type `pool_deposit_v3`)

```ts
type PoolDepositV3Card = {
  card_type: "pool_deposit_v3";
  protocol: string;          // "uniswap-v3"
  chain: string;             // "ethereum"
  pair: { token0: TokenRef; token1: TokenRef };
  fee_tier_bps: number;      // 500
  tick_spacing: number;
  pool_address: string;
  current: {
    price_human: string;     // "3210.45 USDC per WETH"
    sqrt_price_x96: string;  // raw, for math sanity
    tick: number;
    tvl_usd: string;
    vol_24h_usd: string;
  };
  market: {
    base_apr_pct: number;          // fees-only, full range
    reward_apr_pct: number;
    cdf_30d: number[];             // 100 buckets, ratio buckets [0.5x, 2x]
  };
  input: { token: TokenRef; amount_raw: string; amount_human: string; amount_usd: number };
  initial_range: { lower_pct: number; upper_pct: number; preset: "narrow"|"balanced"|"wide"|"full"|"custom" };
  initial_route: ExecutionStepV3[];  // server's best-guess plan, replaced when user picks final range
  rebuild_endpoint: string;          // POST here with chosen range -> get final plan + simulation
};
```

---

## 5. Single-Sided Zap Math — The Reference

### V2

```
input_value_usd = U
half = U / 2
swap1: input -> token0 for $half (slippage_bps applied)
swap2: input -> token1 for $half
read post-swap balances a0, a1
addLiquidity(a0, a1, min_lp = expected_lp * (1 - slippage))
```

Edge: leftover dust from imbalanced swaps -> use a balance-aware zap contract (Beefy ZapRouter, Bento) if available, else return dust to user.

### V3 — the critical math

```
Given pCurrent, pLower, pUpper:
  if pCurrent <= pLower:
    100% token1 (sub-range, acts like limit order up)
  elif pCurrent >= pUpper:
    100% token0
  else:
    sqrt_lower = sqrt(pLower)
    sqrt_upper = sqrt(pUpper)
    sqrt_curr  = sqrt(pCurrent)
    ratio_token0_per_L = (sqrt_upper - sqrt_curr) / (sqrt_curr * sqrt_upper)
    ratio_token1_per_L = (sqrt_curr  - sqrt_lower)
    # convert to USD weights using token prices
    weight0_usd = ratio_token0_per_L * price_token0
    weight1_usd = ratio_token1_per_L * price_token1
    total = weight0_usd + weight1_usd
    swap_to_token0_usd = input_usd * (weight0_usd / total)
    swap_to_token1_usd = input_usd * (weight1_usd / total)
```

Tick alignment is mandatory: `tickLower = floor(rawTickLower / tickSpacing) * tickSpacing`. Misaligned ticks revert immediately.

### Stable (Curve, Balancer)

```
if input_token in pool.tokens:
  add_liquidity(amounts=[0, ..., input_amount, ..., 0], min_lp)
else:
  swap input -> any pool_token, then add_liquidity
```

---

## 6. Gaps — Their Conversation × My Analysis × Our System

### Six top gaps

| Gap | Conversation (Claude#1) | My analysis (Claude#2) | Our system |
|---|---|---|---|
| **Decimals discipline** | Says: BigInt everywhere, convert only at display | Confirms: floats in `int(amount)/10**decimals` produce IEEE-754 garbage | Floats throughout `wallet_lp.py` and `crypto_agent.py`; `amount_in_display` is a Python float that JSON-serializes as `0.1111111111111111` |
| **Single-sided zap** | Says: V2 needs split+swap+deposit; V3 needs range-aware split | Confirms: no zap exists for non-Enso EVM; Solana sidecar prep-swap assumes USDC/SOL | `_build_deposit_lp_tx` passes one token to Enso; Solana adapters swap into USDC or SOL regardless of pool pair |
| **V3 range handling** | Says: SDK provides `Position.fromAmounts`, must align ticks | Confirms: zero V3 range code; Uniswap V3 routed to aUSDC instead | No tick math, no sqrtPriceX96, no range UI; CLMM pools routed by accident |
| **Pre-flight simulation** | Says: simulate before sign, parse revert reason | Confirms: only post-sign verify on Solana; no EVM simulation | `preflight.py` checks balance only; no `eth_call`, no `simulateTransaction` |
| **Pool resolution / enrichment** | Says: pull on-chain state (decimals, ticks, reserves, market id) | Confirms: DefiLlama-only, no on-chain enrichment | `execute_pool_position._fetch_pool_meta` returns DefiLlama row, passes through unchanged |
| **Report card with range UI** | Says: interactive slider, live APR recompute, range comparison table | Adds: live math fully on frontend, no round-trip per drag | We have `ExecutionPlanCard` and `ExecutionPlanV3Card` with no range UI; the LP deposit card is the same as a swap card |

### Three gaps I add (not in the other conversation)

7. **Auto-vault first for low-value deposits.** Kamino on Solana, Gamma/Arrakis on EVM. The other conversation lists these as options — we should make them the default for `input_usd < 100` to remove range complexity entirely. The current Kamino adapter fakes this by swapping into JLP/JitoSOL; we need the real Kamino REST integration.

8. **Strict CardType validation at the API boundary.** The Pydantic `ExecutionStepV3.amount_in` is typed `str`, but the wallet-assistant returns a Python float that pydantic happily coerces to string `"0.1111111111111111"`. We need a `StrictStr` and an upstream `Decimal -> str` formatter that strips trailing zeros and forbids float pass-through. This catches the bug at the schema layer.

9. **Solana transaction-size aware planner.** Single-tx zaps frequently exceed 1232 bytes. We need a pre-build estimator that decides up front whether the zap fits as one tx with an Address Lookup Table or must be split into two txs (and the card must show "Phantom will prompt 2 times"). Today the sidecar produces one tx and hopes for the best.

---

## 7. Phased Plan — What We Build, In Order

### Phase 0 — Stop-the-bleed hotfixes (≤4 hours, ship today)

Goal: prevent users from signing broken txs. No new features, just guardrails.

- **Float kill switch.** In `wallet_lp.py` and `crypto_agent.py`, any `amount_in_display` / `amount_out_display` must be a `Decimal` formatted to a fixed precision string. `int(raw) / 10**decimals` -> `(Decimal(raw) / Decimal(10) ** decimals).quantize(...)`. Forbid passing floats through `dict` payloads.
- **Disable broken LP path with a clear error.** If `pool_type == "v3"` and we can't build a real range-aware tx, the card returns a `pool_link` redirect (as we already do on the no-exec branch) with a banner: "Concentrated-liquidity execution is being rebuilt — finalize in the protocol app." This protects users from the silent aUSDC routing.
- **Solana sidecar pair-aware prep-swap.** Replace the hardcoded USDC/SOL assumption in `raydium.js` and `orca.js` with the real pool's `token0` / `token1` (already passed via `extra.underlying_tokens`). If the user already holds one of the pool tokens, swap into the other. Otherwise swap half into each.
- **Pre-sign Solana simulation.** In the sidecar, after `buildSwap`, call `connection.simulateTransaction(tx, {sigVerify:false, replaceRecentBlockhash:true})` and reject the build with a clear error if `result.value.err` is non-null.
- **Pre-sign EVM simulation.** In the wallet-assistant `_build_enso_swap_tx`, `eth_call` the prepared calldata before returning. If revert, parse the revert reason and return it as a blocker.

### Phase 1 — Pool enrichment layer (1-2 days)

- New module `src/defi/pools/enrich.py` (Python) + matching Node helpers in the sidecar.
- Function: `enrich_pool(pool_id, chain) -> PoolState`.
- Pull token addresses, decimals on-chain (Solana via `getAccountInfo` + Metaplex; EVM via `multicall3` of `decimals()`).
- Classify pool type (V2 / V3 / stable / DLMM / vault) by inspecting contract bytecode hash or known address registries.
- For V3: fetch `fee_tier`, `tick_spacing`, `current_tick`, `sqrtPriceX96`.
- For Solana AMM: fetch market id, vault accounts.
- Cache in Redis 30s.

### Phase 2 — V2 zap (single-sided) end-to-end (2-3 days)

- EVM: 0x quote × 2 + Universal Router multicall (or per-protocol Router). Pre-sim.
- Solana: Jupiter quote × 2 + Raydium SDK `addLiquidity`. Pack with ALT or split.
- Update `solana_yield_builder.py` raydium adapter to actually call `addLiquidity` after the swap.
- Card stays `execution_plan_v3` with proper multi-step rendering; per-step status; "Phantom will prompt N times" header when split.

### Phase 3 — Curve / Balancer stable single-sided (1 day)

- Native pool single-asset deposit. No router needed. This is the easiest case and a great smoke test.
- Add adapter `src/defi/execution/adapters/curve.py` for Curve pools (3pool, stETH/ETH, etc.).
- Balancer is similar; phase 3b if Curve covers enough TVL.

### Phase 4 — V3 / CLMM with range UI (3-5 days)

- New card type `pool_deposit_v3` with the schema from §4.
- Frontend `PoolDepositV3Card.tsx` with the interactive range selector.
- Backend `/api/v1/pool/rebuild` POST endpoint that takes a chosen range and rebuilds the plan in real time, with simulation.
- EVM: `@uniswap/v3-sdk` integration + Permit2 + Universal Router multicall. Enso as bundle provider for the subset of pools it supports.
- Solana: `@orca-so/whirlpools` SDK and `@raydium-io/raydium-sdk-v2` clmm module. Two-tx flow with progress indicators.

### Phase 5 — Kamino vault + EVM auto-vaults (2 days)

- Real Kamino REST integration in `kamino.js`. Drop the JLP/JitoSOL fake.
- Gamma + Arrakis adapters on EVM for the Uniswap V3 pools they index.
- Default routing: if `input_usd < 100` and an auto-vault exists for the requested pool, prefer the vault.

### Phase 6 — Meteora DLMM (optional, niche)

- `@meteora-ag/dlmm` SDK, bin distribution math, multi-bin deposit. Only worth doing if a pilot user requests it.

---

## 8. Validation Plan — How We Prove It Works

Three layers, each blocking deploy.

### Layer 1 — Unit tests

- `tests/test_decimals.py`: enforce no float-typed amount ever leaves the build layer. Property tests with hypothesis covering 6/9/18 decimals, 0.1, 0.0000001, max-uint64.
- `tests/test_v3_math.py`: known-good fixtures for `optimalRatio()` and `tickAlign()` from Uniswap V3 reference vectors.
- `tests/test_pool_enrich.py`: mock RPC, verify decimals/tick/fee are extracted correctly.

### Layer 2 — Wallet-sim harness expansion

We already have `tests/wallet_sim/` and `scripts/validate_no_exec.py`. Expand with a new `scripts/validate_pool_exec.py`:

- 30 scenarios across 10 pool types × 3 chains, mixing single-sided, two-sided, stable, V3 narrow, V3 wide, V3 out-of-range, Kamino vault, Raydium AMM, Raydium CLMM, Orca Whirlpool.
- For each: full SSE round-trip + simulation receipt + assertion on tx structure (right pool, right tokens, right amounts within slippage cap).
- Pass criterion: 30/30 simulate successfully; per-step decoded program errors are zero.

### Layer 3 — Live 30-conversation suite on `ilyonai.com`

After the new branch deploys, run a structured adversarial corpus:

- 10 trivial single-pool intents (single-token deposit, common pairs).
- 10 conversational multi-turn (refine range, swap source token, change USD amount, ask for APR comparison).
- 10 edge cases (out-of-range V3, dusty long-tail Solana pool, classic-USDT approve reset, Token-2022 token, native SOL wrap, ALT-required size, off-range single-sided, Kamino-vs-direct comparison, "all my USDT" balance grab, "execute the top pool I see").

For each conversation: capture transcript + simulated receipts + screenshots. Any failure halts the run and triggers an immediate fix-and-retry until clean.

### Layer 4 — Tester-mirror integration

Once 30/30 pass, give the tester a fresh corpus they have never seen. Their job is to attempt every step on the live site (no signing real funds — Phantom + MetaMask testnet RPCs only). Any UX issue, miscount, or revert -> ticket back to us, fix, redeploy, retest.

---

## 9. Risks & Open Questions

- **Enso V3 LP support is partial.** We must benchmark which V3 pools Enso actually mints positions for vs falls through to aUSDC. Recommendation: smoke-test the top 50 Uniswap V3 pools by TVL via Enso `/shortcuts/route` and tabulate.
- **Solana ALT cost vs split-tx UX.** ALT creation is one-time per address set but takes one slot. We probably want a curated global ALT containing Jupiter, Raydium AMM/CLMM, Orca Whirlpool, Meteora, top 50 mints. Maintenance burden but worth it.
- **Permit2 wallet support.** MetaMask supports Permit2 typed-data signing. Coinbase Wallet, Phantom-EVM, WalletConnect-routed wallets vary. Need a feature-detect layer.
- **Range historical data.** We don't run our own price archives. Options: Birdeye API (Solana), CoinGecko (everything else), GeckoTerminal (per-pool tick history for V3 — most accurate but rate-limited).
- **Slippage and MEV on EVM.** For deposits >$10k, we should require MEV protection (Flashbots Protect RPC or 0x Slippage-aware routing). Below that, classic mempool is fine.

---

## 10. Definition of Done

- 30/30 live conversations execute without manual intervention.
- 0 cards with float-formatted amounts.
- 0 V3 deposits routed to Aave by accident.
- 0 Solana LP deposits where the "deposit" tx is actually a prep-swap.
- All LP txs are simulated before the user sees a Sign button.
- Tester repeats the run on fresh corpus and confirms deposits land in the intended pools.
