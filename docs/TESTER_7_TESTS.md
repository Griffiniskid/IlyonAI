# 7 Complex Tester Tests — Pool Execution Validation

Run against `https://staging.ilyonai.com` with MetaMask (EVM) + Phantom (Solana).
Each test is **one continuous chat session** — turns must be entered in order so
refinement context carries. Disconnect between tests.

Pass rule per turn: expected card type renders + summary text mentions the
named chain / protocol / asset / amount. Multi-turn refinement: latest delta
surfaces in the new card.

---

## TEST 1 — EVM Lending Switch Storm
**Wallet:** MetaMask · **Coverage:** Aave V3 + Compound V3 × Ethereum / Base / Polygon × USDC / USDT × chain + token + protocol + amount refine.

| Turn | Prompt | Expected |
|---|---|---|
| 1 | `Supply 100 USDC to Aave V3 on Ethereum` | `execution_plan_v3`, 1 step, summary mentions `aave-v3`, `ethereum`, `100`, `USDC`. |
| 2 | `Try Base instead` | `execution_plan_v3`, summary mentions `base` (not ethereum), same protocol. |
| 3 | `Actually use USDT instead` | `execution_plan_v3`, summary mentions `USDT`, chain still `base`. |
| 4 | `Try Polygon` | `execution_plan_v3`, summary mentions `polygon`. |
| 5 | `Now switch to Compound V3` | `execution_plan_v3`, summary mentions `compound-v3`, still `polygon`. |
| 6 | `Make it $250` | `execution_plan_v3`, amount surfaces as 250. |

**Fail conditions:** any turn drops to `pool_link`, returns empty cards, or summary still shows the prior chain / protocol / amount.

---

## TEST 2 — V3 NFT Multi-Chain + Range Math
**Wallet:** MetaMask · **Coverage:** Uniswap V3 on Ethereum & Base + Aerodrome Slipstream on Base + amount / fee / chain refine + range UI.

Every V3 turn must produce a **4-step `execution_plan_v3`**:
1. Swap input → counterpart (Enso router)
2. Approve token0 → NonfungiblePositionManager (max approve)
3. Approve token1 → NonfungiblePositionManager
4. `NonfungiblePositionManager.mint` with ticks aligned to spacing + optimal token0/token1 ratio computed live from `slot0()`.

| Turn | Prompt | Expected |
|---|---|---|
| 1 | `Add liquidity to Uniswap V3 USDC/WETH 0.05% on Ethereum with $100` | 4-step plan. Step 4 `tx.to` = `0xC36442b4a4522E871399CD717aBDD847Ab11FE88`. |
| 2 | `Make it $50` | 4-step plan, amount 50. |
| 3 | `Try Base instead` | 4-step plan, chain=base, step 4 `tx.to` = `0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1`. |
| 4 | `Add liquidity to Aerodrome Slipstream USDC-WETH on Base $75` | 4-step plan, step 4 `tx.to` = `0x827922686190790b37229fd06084350E74485b72`. |
| 5 | `What about a wider 25% range?` | Range UI updates: capital efficiency drops vs ±10%, in-range probability rises. |

**Fail conditions:** any V3 turn redirects to Uniswap UI (`finalize_externally:true`), mint calldata invalid hex, range UI doesn't recompute.

---

## TEST 3 — Cross-Token Zap + Protocol Cascade
**Wallet:** MetaMask · **Coverage:** USDT-not-in-pair Curve zap + Yearn switch + Morpho cross-chain + amount refine.

| Turn | Prompt | Expected |
|---|---|---|
| 1 | `Deposit 100 USDT into Curve DAI-USDC on Ethereum` | `execution_plan_v3`. Enso internally swaps USDT → DAI/USDC then `add_liquidity` (single bundled tx). |
| 2 | `Actually use Yearn USDC vault instead` | `execution_plan_v3`, protocol=`yearn-finance`, position token = yvUSDC. |
| 3 | `Try Morpho on Base` | `execution_plan_v3`, chain=base, protocol=`morpho-blue`, position = MetaMorpho USDC. |
| 4 | `Make it 25 USDC` | `execution_plan_v3`, amount 25 USDC. |

**Fail conditions:** T1 emits `pool_link` (cross-token must zap via Enso); T2/T3 protocol switch doesn't take.

---

## TEST 4 — Solana LST Cascade + Mixed LP
**Wallet:** Phantom · **Coverage:** Marinade / Jito / Sanctum stake + Raydium AMM zap + Orca Whirlpools CLMM.

| Turn | Prompt | Expected |
|---|---|---|
| 1 | `Stake 0.1 SOL with Marinade` | Signable `VersionedTransaction` (legacy v2 OR v3). Text MUST NOT contain `0.1111111` or `0.0999999`. |
| 2 | `Switch to Jito` | Signable tx routed to Jito stake. |
| 3 | `And Sanctum INF` | Signable tx for Sanctum INF. |
| 4 | `Add 5 USDC to Raydium AMM SPACEX-WSOL` | `execution_plan_v3` with pair-aware Jupiter prep-swap + Raydium `addLiquidity`. |
| 5 | `Execute orca-dex USDC-SOL with 10 USDC` | `execution_plan_v3` for Orca Whirlpools. |

**Fail conditions:** any turn emits float-drift text (`0.1111111` / `5.5555555` / etc.); `tx.serialized` fails deserialization; `simulateTransaction` reports non-benign error.

---

## TEST 5 — V2 → V3 Same Pair Promotion
**Wallet:** MetaMask · **Coverage:** Uniswap V2 dual-token + V3 mint + fee tier switch + cross-chain.

| Turn | Prompt | Expected |
|---|---|---|
| 1 | `Add liquidity to Uniswap V2 USDC-WETH on Ethereum with 100 USDC and 0.05 WETH` | `execution_plan_v3`, **3 steps**: approve USDC, approve WETH, `addLiquidity`. `tx.to` = Uniswap V2 router. |
| 2 | `Switch to Uniswap V3 same pair $200` | `execution_plan_v3`, **4 steps** (swap + 2× approve + mint), default 0.05% fee tier. |
| 3 | `Try 0.30% fee tier` | `execution_plan_v3`, mint calldata encodes `fee=3000` + `tick_spacing=60`. |
| 4 | `Try Base instead` | `execution_plan_v3`, 4 steps on Base. |

**Fail conditions:** T2 stays 3-step (V2→V3 promotion failed); T3 fee param missing in mint calldata.

---

## TEST 6 — Error Recovery + Graceful Degradation
**Wallet:** MetaMask · **Coverage:** unknown protocol fallback + adapter error decoding + huge amount sim.

| Turn | Prompt | Expected |
|---|---|---|
| 1 | `Supply 100 USDC to FakeBank on Ethereum` | `pool_link` redirect (no adapter for `fakebank`). |
| 2 | `Try Aave V3 instead` | `execution_plan_v3` rebuilds with `aave-v3`. |
| 3 | `Make it 999999999 USDC` | `execution_plan_v3`. Sim benign-reverts (test wallet lacks balance); blocker shows decoded hint (e.g. `ERC20: transfer amount exceeds balance`). |
| 4 | `Show me USDC balance on Ethereum` | Portfolio / balance response, NOT `pool_link`. |

**Fail conditions:** T1 emits broken plan; T3 throws unhandled exception instead of human blocker; T4 leaks a stale `pool_link`.

---

## TEST 7 — Float Precision + Tiny Amounts (Regression Guard)
**Wallet:** MetaMask · **Coverage:** decimal serialization on tiny / huge / fractional amounts.

| Turn | Prompt | Expected |
|---|---|---|
| 1 | `Supply 0.1 USDC to Aave V3 on Ethereum` | `execution_plan_v3`, amount surfaces as `0.1` not `0.0999999` or `0.1111111`. |
| 2 | `Make it 12345.6789 USDC` | `execution_plan_v3`, amount `12345.6789`; calldata encodes `12345678900` raw units (6 decimals). |
| 3 | `Add liquidity to Curve DAI-USDC on Ethereum $3.14` | `execution_plan_v3`, amount `3.14`, no `3.14159265...` drift. |

**Fail conditions:** any text contains `0.0999999`, `0.1111111`, `1.1111111`, `3.14159265`, scientific notation, or atomic-unit display.

---

# Verification After Each Sign

For every `execution_plan_v3` step:

1. Open MetaMask / Phantom popup. Verify:
   - `to` address matches the expected contract (Enso router / NFP manager / Raydium program).
   - `data` starts with the expected 4-byte selector and is valid hex.
   - `value` matches the native-token leg (0x0 for ERC20 only, real wei for ETH stakes).
2. Reject signature (test wallet need not sign). Card stays in `ready`; no double-render.
3. Refresh chat. Prior card persists in history.

# Acceptance

All 7 tests pass when every numbered turn renders the expected card type AND multi-turn refinement updates chain / protocol / amount in the summary text. Any deviation = bug report with full transcript.
