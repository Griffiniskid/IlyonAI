# Tester Walkthrough — Pool Execution Validation

Run against `https://staging.ilyonai.com` with a connected MetaMask (EVM) wallet
and Phantom (Solana) wallet. Each test shows the exact prompt the tester types
and the expected outcome.

**Pass criterion for each test:**
- The expected card type renders (`execution_plan_v3` for native execution,
  `pool_link` for redirect-only paths, `pool_deposit_v3` for V3 range cards).
- For `execution_plan_v3` cards: the step count and step actions match.
- Sign buttons emit a real signature request via the wallet; no "Open in
  Uniswap" redirect unless explicitly listed.
- For multi-turn refinement: the card rebuilds with the new chain / protocol /
  amount surfaced in the summary text.

Total: **75 scenarios** spanning all matrix cells.

---

## Group 1 — EVM Lending / Vault Single-Sided (Enso shortcut)

### 1.1 Aave V3 USDC supply on Ethereum
- **Prompt:** `Supply 100 USDC to Aave V3 on Ethereum`
- **Wallet:** MetaMask
- **Expected card:** `execution_plan_v3`
- **Steps:** 1 step — Enso bundled supply (`tx.to = 0xF75584eF6673aD213a685a1B58Cc0330B8eA22Cf`).
- **Sim check:** eth_call against Enso router; benign revert (test wallet 0 USDC) = pass.

### 1.2 Aave V3 USDT supply on Ethereum
- **Prompt:** `Supply 100 USDT to Aave V3 on Ethereum`
- **Wallet:** MetaMask
- **Expected card:** `execution_plan_v3`, single step, Enso route, USDT in.

### 1.3 Aave V3 DAI supply on Ethereum
- **Prompt:** `Supply 50 DAI to Aave V3 on Ethereum`
- **Expected card:** `execution_plan_v3`, single step.

### 1.4 Aave V3 USDC supply on Base
- **Prompt:** `Supply 100 USDC to Aave V3 on Base`
- **Expected card:** `execution_plan_v3`; tx.to = Enso router on Base.

### 1.5 Aave V3 USDT supply on Polygon
- **Prompt:** `Supply 50 USDT to Aave V3 on Polygon`
- **Expected card:** `execution_plan_v3`.

### 1.6 Aave V3 USDC supply on Arbitrum
- **Prompt:** `Supply 50 USDC to Aave V3 on Arbitrum`
- **Expected card:** `execution_plan_v3`.

### 1.7 Aave V3 USDC supply on Optimism
- **Prompt:** `Supply 50 USDC to Aave V3 on Optimism`
- **Expected card:** `execution_plan_v3`.

### 1.8 Aave V3 USDC supply on Avalanche
- **Prompt:** `Supply 50 USDC to Aave V3 on Avalanche`
- **Expected card:** `execution_plan_v3`.

### 1.9 Compound V3 USDC supply on Ethereum
- **Prompt:** `Supply 100 USDC to Compound V3 on Ethereum`
- **Expected card:** `execution_plan_v3`.

### 1.10 Compound V3 USDC supply on Base
- **Prompt:** `Supply 75 USDC to Compound V3 on Base`
- **Expected card:** `execution_plan_v3`.

### 1.11 Compound V3 USDC supply on Arbitrum
- **Prompt:** `Supply 60 USDC to Compound V3 on Arbitrum`
- **Expected card:** `execution_plan_v3`.

### 1.12 Yearn USDC vault on Ethereum
- **Prompt:** `Deposit 100 USDC into Yearn USDC vault on Ethereum`
- **Expected card:** `execution_plan_v3`. Routes via Enso resolver →
  yvUSDC position token.

### 1.13 Yearn USDC vault on Base
- **Prompt:** `Deposit 25 USDC into Yearn USDC vault on Base`
- **Expected card:** `execution_plan_v3`.

### 1.14 Morpho USDC on Base
- **Prompt:** `Deposit 100 USDC into Morpho on Base`
- **Expected card:** `execution_plan_v3`; tx.to = Enso router.

### 1.15 Spark DAI on Ethereum
- **Prompt:** `Deposit 50 DAI into Spark on Ethereum`
- **Expected card:** `execution_plan_v3`; resolver maps `spark` → `spark`
  Enso slug, position token = sDAI.

---

## Group 2 — EVM Stable LP (Enso single-sided into Curve / Balancer)

### 2.1 Curve DAI-USDC on Ethereum
- **Prompt:** `Add liquidity to Curve DAI-USDC on Ethereum $100`
- **Expected card:** `execution_plan_v3`; one-step Curve add_liquidity.

### 2.2 Curve DAI-USDT on Ethereum (inverted form)
- **Prompt:** `Deposit 50 DAI into Curve DAI-USDT on Ethereum`
- **Expected card:** `execution_plan_v3`.

### 2.3 Curve USDC-USDT on Arbitrum
- **Prompt:** `Add liquidity to Curve USDC-USDT on Arbitrum $30`
- **Expected card:** `execution_plan_v3`.

### 2.4 Curve DAI-USDC on Optimism
- **Prompt:** `Add liquidity to Curve DAI-USDC on Optimism $20`
- **Expected card:** `execution_plan_v3`.

### 2.5 Curve DAI-USDC on Polygon
- **Prompt:** `Add liquidity to Curve DAI-USDC on Polygon $30`
- **Expected card:** `execution_plan_v3`.

### 2.6 Curve USDC-USDBC on Base
- **Prompt:** `Add liquidity to Curve USDC-USDBC on Base $40`
- **Expected card:** `execution_plan_v3`.

### 2.7 Balancer USDC-DAI on Ethereum
- **Prompt:** `Add liquidity to Balancer USDC-DAI on Ethereum $100`
- **Expected card:** `execution_plan_v3`.

### 2.8 Balancer on Arbitrum
- **Prompt:** `Deposit 50 USDC into Balancer on Arbitrum`
- **Expected card:** `execution_plan_v3`.

---

## Group 3 — EVM LST Stake (Enso bundled into Lido / RocketPool / EtherFi / Frax)

### 3.1 Lido stETH stake
- **Prompt:** `Stake 0.05 ETH with Lido on Ethereum`
- **Expected card:** `execution_plan_v3`, one step.

### 3.2 Rocket Pool rETH stake
- **Prompt:** `Stake 0.05 ETH with Rocket Pool on Ethereum`
- **Expected card:** `execution_plan_v3`.

### 3.3 EtherFi eETH stake
- **Prompt:** `Stake 0.05 ETH with EtherFi on Ethereum`
- **Expected card:** `execution_plan_v3`.

---

## Group 4 — EVM V3 NFT (UniswapV3NFTAdapter — closes the "any pool" gap)

Every V3 prompt below produces a 4-step `execution_plan_v3`:
1. **Swap** input → counterpart token (Enso) — skipped if input already
   matches token0 or token1 in full proportion.
2. **Approve token0** to NonfungiblePositionManager (one-time max approve).
3. **Approve token1** to NonfungiblePositionManager.
4. **Mint NFT position** via `NonfungiblePositionManager.mint` with default
   range ±10% from current price, tick-spacing-aligned, optimal token0/token1
   ratio computed live from `slot0()`.

### 4.1 Uniswap V3 USDC/WETH 0.05% on Ethereum
- **Prompt:** `Add liquidity to Uniswap V3 USDC/WETH 0.05% on Ethereum with $100`
- **Expected:** 4-step plan. Step 4 tx.to = `0xC36442b4a4522E871399CD717aBDD847Ab11FE88`.
- **Sim:** eth_call benign (insufficient balance) → pass.

### 4.2 Uniswap V3 USDC/WETH on Base
- **Prompt:** `Add liquidity to Uniswap V3 USDC/WETH on Base with 50 USDC`
- **Expected:** 4-step plan; tx.to = Base NFP manager `0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1`.

### 4.3 Uniswap V3 USDC/WETH on Arbitrum
- **Prompt:** `Add liquidity to Uniswap V3 USDC/WETH on Arbitrum $40`
- **Expected:** 4-step plan.

### 4.4 Uniswap V3 USDC/WETH on Polygon
- **Prompt:** `Add liquidity to Uniswap V3 USDC/WETH on Polygon $35`
- **Expected:** 4-step plan.

### 4.5 Uniswap V3 USDC/WETH on Optimism
- **Prompt:** `Add liquidity to Uniswap V3 USDC/WETH on Optimism $30`
- **Expected:** 4-step plan.

### 4.6 Uniswap V3 USDC/WAVAX on Avalanche
- **Prompt:** `Add liquidity to Uniswap V3 USDC/WAVAX on Avalanche $25`
- **Expected:** 4-step plan.

### 4.7 PancakeSwap V3 USDT-BNB on BSC
- **Prompt:** `Deposit $50 into PancakeSwap V3 USDT-BNB on BSC`
- **Expected:** `execution_plan_v3` — PancakeSwap V3 NFP manager `0x46A15B0b27311cedF172AB29E4f4766fbE7F4364`.

### 4.8 Aerodrome Slipstream USDC-WETH on Base
- **Prompt:** `Add liquidity to Aerodrome Slipstream USDC-WETH on Base $50`
- **Expected:** `execution_plan_v3`; NFP manager `0x827922686190790b37229fd06084350E74485b72`.

### 4.9 SushiSwap V3 (no native adapter — still redirects)
- **Prompt:** `Add liquidity to SushiSwap V3 USDC-WETH on Ethereum $50`
- **Expected:** `pool_deposit_v3` card with range UI; final mint redirects
  to SushiSwap app (intentional — no SushiSwap V3 in `V3_NATIVE_EXEC`).

---

## Group 5 — EVM V2 Dual-Token (Native router.addLiquidity)

V2 dual-token requires both legs. Single-amount V2 emits a `blocked`
`execution_plan_v3` with an explanatory blocker (no auto-zap).

### 5.1 Uniswap V2 USDC+WETH dual-token
- **Prompt:** `Add liquidity to Uniswap V2 USDC-WETH on Ethereum with 100 USDC and 0.05 WETH`
- **Expected:** `execution_plan_v3` with 3 steps: approve USDC + approve WETH + addLiquidity.

### 5.2 SushiSwap USDC+WETH dual-token
- **Prompt:** `Add liquidity to SushiSwap USDC-WETH on Ethereum with 50 USDC and 0.025 WETH`
- **Expected:** `execution_plan_v3`, 3 steps.

### 5.3 PancakeSwap V2 USDC+WBNB on BSC
- **Prompt:** `Add liquidity to PancakeSwap V2 USDC-WBNB on BSC with 50 USDC and 0.1 WBNB`
- **Expected:** `execution_plan_v3`, 3 steps.

### 5.4 Uniswap V2 single-amount (blocked plan, NOT pool_link)
- **Prompt:** `Add liquidity to Uniswap V2 USDC-WETH on Ethereum with $100`
- **Expected:** `execution_plan_v3` with `blockers: [...]` — second leg amount missing.

---

## Group 6 — Solana

### 6.1 Marinade SOL stake
- **Prompt:** `Stake 0.1 SOL with Marinade`
- **Wallet:** Phantom
- **Expected:** signable plan (legacy v2 OR v3, both produce real signed VersionedTransaction).

### 6.2 Jito SOL stake
- **Prompt:** `Stake 0.1 SOL with Jito`
- **Expected:** signable plan.

### 6.3 Sanctum INF stake
- **Prompt:** `Stake 0.1 SOL into Sanctum INF`
- **Expected:** signable plan.

### 6.4 Raydium AMM zap (pair-aware prep swap)
- **Prompt:** `Execute raydium-amm SPACEX-WSOL with 10 USDC`
- **Expected:** `execution_plan_v3` with pair-aware Jupiter prep-swap + Raydium AMM addLiquidity.

### 6.5 Orca Whirlpools (CLMM)
- **Prompt:** `Execute orca-dex USDC-SOL with 10 USDC`
- **Expected:** `execution_plan_v3`.

### 6.6 Orca CLMM narrow
- **Prompt:** `Add liquidity to orca-whirlpools USDC-SOL on Solana with 10 USDC`
- **Expected:** `execution_plan_v3`.

### 6.7 Meteora SOL-USDC DLMM
- **Prompt:** `Deposit 10 USDC into Meteora SOL-USDC DLMM`
- **Expected:** `execution_plan_v3`.

### 6.8 Meteora SOL-USDC AMM
- **Prompt:** `Add liquidity to Meteora SOL-USDC on Solana with 10 USDC`
- **Expected:** `execution_plan_v3`.

### 6.9 Kamino USDC-SOL vault
- **Prompt:** `Deposit 25 USDC into Kamino USDC-SOL on Solana`
- **Expected:** `execution_plan_v3`.

---

## Group 7 — Multi-Turn Refinement

Each row is a session — every turn must re-render the right card on staging.

### 7.1 Aave chain switch
1. `Supply 100 USDC to Aave V3 on Ethereum` → `execution_plan_v3` (chain=ethereum)
2. `Try Base instead` → `execution_plan_v3` (chain=base, summary shows "base")
3. `And Arbitrum?` → `execution_plan_v3` (chain=arbitrum)

### 7.2 Aave token switch
1. `Supply 50 USDC to Aave V3 on Ethereum`
2. `Actually use USDT instead` → asset_in=USDT, same chain/protocol.

### 7.3 Aave → Yearn protocol switch
1. `Supply 100 USDC to Aave V3 on Ethereum`
2. `Actually use Yearn instead` → protocol=yearn-finance, action=supply.

### 7.4 Curve chain switch
1. `Add liquidity to Curve DAI-USDC on Ethereum $50`
2. `Try Polygon instead` → chain=polygon (may blocker if no Curve pool there — that's OK)
3. `And Arbitrum?` → chain=arbitrum.

### 7.5 V3 EVM amount refine
1. `Add liquidity to Uniswap V3 USDC-WETH on Ethereum $100` → 4-step plan.
2. `Make it $50` → 4-step plan with new amount.
3. `Try Base instead` → 4-step plan on Base (USDC/WETH on Base).

### 7.6 Solana Raydium refinement
1. `Show me Raydium AMM SPACEX-WSOL pool`
2. `Execute with 5 USDC` → `execution_plan_v3`.
3. `Make it 10 USDC instead` → updated `execution_plan_v3`.

### 7.7 Top-one pick from search
1. `Show me Uniswap V3 USDC-WETH pools on Ethereum` → defi_opportunities card.
2. `Add liquidity with $50 to the top one` → V3 NFT 4-step plan.

---

## Group 8 — Error / Edge Cases

### 8.1 Unknown protocol → pool_link
- **Prompt:** `Supply 100 USDC to FakeBank on Ethereum`
- **Expected:** `pool_link` redirect (no adapter).

### 8.2 V3 missing fee tier
- **Prompt:** `Add liquidity to Uniswap V3 USDC-WETH on Base with 50 USDC` (no fee suffix)
- **Expected:** `execution_plan_v3` defaulting to 0.05% (500 bps) tier.

### 8.3 Wallet mismatch — Solana request from EVM session
- **Prompt:** `Execute raydium-amm SPACEX-WSOL with 10 USDC` (EVM wallet only)
- **Expected:** blocker or warning.

### 8.4 Wallet mismatch — EVM request from Solana session
- **Prompt:** `Add liquidity to Uniswap V3 USDC-WETH on Ethereum $50` (Solana wallet only)
- **Expected:** blocker or warning.

---

## Group 9 — Float / Decimal Regression

### 9.1 Tiny SOL stake
- **Prompt:** `Stake 0.001 SOL with Marinade`
- **Expected:** signable plan; **MUST NOT** print `0.0009999999` or `0.1111111`.

### 9.2 Fractional USDC supply
- **Prompt:** `Supply 0.1 USDC to Aave V3 on Ethereum`
- **Expected:** `execution_plan_v3`; no `0.0999999` text.

### 9.3 Large fractional amount
- **Prompt:** `Supply 12345.6789 USDC to Aave V3 on Ethereum`
- **Expected:** `execution_plan_v3`; no scientific-notation drift.

### 9.4 Curve $3.14 deposit
- **Prompt:** `Add liquidity to Curve DAI-USDC on Ethereum $3.14`
- **Expected:** `execution_plan_v3`; amount surfaced as 3.14, no `3.1415926...`.

---

## Group 10 — Sentinel / Search Regression

### 10.1 Yield discovery
- **Prompt:** `Top 3 yields with TVL above 500M on Ethereum`
- **Expected:** `defi_opportunities` card.

### 10.2 Sentinel report
- **Prompt:** `Sentinel report on USDC ethereum`
- **Expected:** sentinel narrative; **no** stray `pool_link` card.

### 10.3 Swap regression
- **Prompt:** `Swap 100 USDC to WETH on Ethereum`
- **Expected:** swap card with signable tx.

### 10.4 Solana swap regression
- **Prompt:** `Swap 0.1 SOL to USDC on Solana`
- **Expected:** swap card with signable VersionedTransaction.

---

## Verification Steps After Each Sign

For every `execution_plan_v3` that emits real calldata:

1. Open MetaMask / Phantom popup. Confirm:
   - `to` address matches the expected contract (Enso router / NFP manager / Raydium program).
   - `data` calldata is not all zeros, starts with the expected selector.
   - `value` matches the native-token leg (0x0 for ERC20 plays, real wei for ETH stakes).
2. Reject the signature (test wallet need not sign on mainnet). Confirm the
   card stays in "ready" state and that no double-render happens.
3. Refresh the chat. Confirm the prior card persists in history.

## Acceptance

Test passes when **every numbered scenario** above renders the expected card type AND multi-turn refinement updates the chain/protocol/amount in the summary text. Any deviation = file a bug with the conversation transcript.
