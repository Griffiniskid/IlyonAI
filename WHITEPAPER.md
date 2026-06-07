# Ilyon AI — Whitepaper

**The AI-native DeFi copilot. One chat box. Every chain. Every action signed in your own wallet.**

*Version 1.0 · June 2026 · [ilyonai.com](https://ilyonai.com)*

---

## Abstract

Decentralised finance is the most capable financial system ever deployed on open infrastructure and, simultaneously, the worst consumer surface in software. Earning yield in a single liquidity pool today requires a user to choose a chain, choose a venue, locate a pool, verify it is not a scam, source the input asset, set slippage, hold the right gas token, and sign a sequence of transactions across multiple wallets — any one of which can silently fail or be exploited.

Ilyon AI collapses that workflow into a single sentence. A user states intent in natural language; the agent resolves it to a concrete on-chain action, scores the associated risk with a deterministic engine, assembles the calldata, simulates it against live chain state, and returns a transaction the user signs in their own wallet. Funds are never custodied. Every recommendation carries a numerical safety score with an explicit dimension breakdown.

This document describes the system: its architecture, its intent layer, the Sentinel risk engine, the execution and simulation pipeline, the liquid-staking and position-tracking subsystem, the multi-chain coverage, and the security model. Ilyon AI is non-custodial, MIT-licensed, and self-hostable. **It has no token; this is a technical and product whitepaper, not a token-sale document.**

---

## 1. The problem

A retail DeFi user faces three structural failures at once:

1. **Fragmentation.** Liquidity, yield, and security data live across dozens of chains, hundreds of protocols, and a long tail of incompatible interfaces. No single surface aggregates them with consistent semantics.
2. **Asymmetric risk.** The same screen renders a battle-tested blue-chip pool and a deployer-controlled honeypot identically. The information needed to tell them apart — deployer history, liquidity staging, approval surface, exit depth — is public but unaggregated and unscored.
3. **Execution friction.** A single economic intent ("earn balanced yield with $5k") decomposes into routing, slippage, gas sourcing, and multi-step signing. Each step is a place to lose money to a revert, a sandwich, or a fat finger.

The result is a system whose power is captured almost entirely by sophisticated actors, while ordinary users are routed into the riskiest, highest-fee paths.

## 2. The solution

Ilyon AI is an agentic execution layer over the existing DeFi stack. It does not replace protocols; it sits in front of them and turns intent into wallet-gated execution. Three properties define it:

- **Intent-first.** The user expresses *what* they want, not *how*. The agent owns chain selection, venue selection, routing, sizing, and assembly.
- **Risk-scored by default.** Every opportunity is passed through the Sentinel engine before it is surfaced. The score and its breakdown travel with the recommendation as a first-class field, not a footnote.
- **Non-custodial by construction.** Every transaction is built unsigned and signed in the user's wallet. **Phantom (Solana) and MetaMask (EVM) are wired today**, both on desktop and via the wallet's in-app mobile browser. Solflare, Backpack, OKX, Coinbase Wallet and a direct WalletConnect handshake are on the integration roadmap (Section 13). The platform holds no keys and no funds.

## 3. System architecture

Ilyon AI is a small set of cooperating services rather than a monolith. Responsibilities are split so that risk math, EVM assembly, and Solana assembly each run in the environment best suited to them.

```
                          ┌──────────────────────┐
        Browser  ◀──SSE──▶│   Frontend (Next.js) │
   Phantom / MetaMask     │  typed-card renderer │
                          └──────────┬───────────┘
                                     │ POST /api/v1/agent (SSE)
                          ┌──────────▼───────────┐
                          │   Sentinel API       │   intent router · LLM tool-use loop
                          │   (Python, async)    │   Sentinel risk engine · allocation
                          │                      │   pool resolver · Solana Blinks
                          └───┬─────────────┬────┘
              ┌───────────────┘             └───────────────┐
   ┌──────────▼──────────┐          ┌────────────────────▼─┐
   │  Wallet Assistant    │          │  Solana Yield Builder │
   │  (Python sidecar)    │          │  (Node sidecar)       │
   │  EVM swap/bridge/    │          │  Raydium · Orca ·     │
   │  supply/stake via    │          │  Meteora · Kamino ·   │
   │  Enso · 0x · deBridge │          │  Marinade · Jito      │
   └─────────────────────┘          └───────────────────────┘
                          ┌──────────────────────┐
                          │  Postgres + Redis     │  session memory · quote/result cache
                          └──────────────────────┘
```

- **Frontend (`web/`)** — Next.js 14, React 18, TypeScript, Tailwind, Radix. Consumes a server-sent-event stream from the agent and renders *typed cards* — token reports, pool reports, allocation matrices, execution plans, swap/stake/unstake previews, an interactive V3 range selector — instead of plaintext. The card payload types are mirrored 1:1 with the backend so any partner front-end can render Ilyon cards natively.
- **Sentinel API (`src/`)** — the analytical brain. Hosts the LLM tool-use loop, the deterministic Sentinel risk engine, the allocation composer, the pool-resolution layer, and the Solana Actions / Blinks endpoints. Reads from DefiLlama, DexScreener, RugCheck, Helius, Moralis, Birdeye, GeckoTerminal, and Honeypot.
- **Wallet Assistant (`IlyonAi-Wallet-assistant-main/server/`)** — the EVM/Solana execution sidecar. Builds swap, bridge, supply, stake, **unstake**, transfer, and LP transactions through Enso, 0x, deBridge, and Jupiter. Returns calldata pre-simulated via `eth_call` (EVM) so the user never pays gas on a guaranteed revert.
- **Solana Yield Builder (`services/solana-yield-builder/`)** — Node sidecar with first-party adapters for Raydium, Orca Whirlpools, Meteora DLMM, Kamino, Marinade, Jito, Sanctum, and Jupiter. Emits versioned transactions with Address Lookup Tables and a mandatory `simulateTransaction` gate before any transaction leaves the service.
- **Postgres + Redis** (recommended in production; SQLite + in-process cache fallback for self-host) — session/conversation memory and a quote/result cache so repeated questions resolve instantly.

## 4. The intent layer

Every user message enters an **intent router** that classifies it before any model spends a token. The router recognises a fixed vocabulary of actionable intents — `swap`, `bridge`, `supply`, `deposit_lp`, `stake`, `unstake`, `transfer`, `search`, `analyze` — plus reasoning/advice questions that must be answered conversationally rather than executed.

- **Deterministic short-circuit.** Unambiguous imperatives ("stake 0.5 SOL", "unstake my jitoSOL", "swap 50 USDC to SOL") are parsed and assembled without an LLM round-trip, which removes both latency and a class of model-induced errors.
- **Reasoning gate.** Analytical phrasings ("is it worth staking if fees eat the rewards?", "should I unstake?") are routed to a single reliable reasoning call rather than a transaction builder, so advice questions never accidentally emit a signable transaction, and commands are never diverted into a chat answer.
- **Refusal on incompleteness.** Logically incomplete or self-contradictory requests (a same-token swap, a buy with no amount) are refused at the build chokepoint and returned as a clarification — never silently auto-defaulted into a transaction.

The intent layer is one of three primitives Ilyon exposes for reuse (Section 11): natural language in, typed JSON tool calls out, with the entire downstream execution pipeline reusable behind any LLM router.

## 5. The Sentinel risk engine

Sentinel is a deterministic, chain- and protocol-agnostic risk model. **No LLM participates in the risk math** — the score is reproducible Python, so the same inputs always yield the same number. It produces a unified 0–100 score across five surfaces, each with an explicit dimension breakdown that travels with the score:

| Surface | What it measures |
|---|---|
| **Token security** | Contract red flags, mint/freeze authority, honeypot behaviour, holder distribution, liquidity backing. |
| **Pool durability** | TVL depth, fee-revenue sustainability, exit liquidity, age, and incident history. |
| **Whale clustering** | Concentration and coordination among large holders. |
| **Deployer entity** | Deployer-wallet forensics tying a new contract to the actor behind it — a serial-scammer registry across chains. |
| **Shield approval surface** | The user's own outstanding EVM token approvals: stale, oversized, or malicious allowances they have already granted. |

Two capabilities sit on top of the base score:

- **Predictive rug detection** — behavioural analysis of liquidity staging, deployer history, and price/volume divergence to surface a probable rug *before* it executes.
- **Liquidity backfill** — where a primary data source reports null liquidity (common for new or bonding-curve tokens), Sentinel backfills from a secondary on-chain reserve source so a thin-data token is scored on reality rather than zeroed out.

## 6. The execution pipeline

The path from intent to a signed transaction is identical in shape for every action type:

1. **Resolve.** Map the natural-language reference to a concrete on-chain object — a pool's pair/fee-tier/tick state, a token's mint/decimals, a staking protocol's receipt token.
2. **Score.** Lift the Sentinel dimensions for the target, its underlying assets, and its deployer.
3. **Route.** Select the builder and provider for the action and chain (Jupiter for Solana swaps/stakes; Enso and 0x for EVM swaps and yield; deBridge for cross-chain), with slippage and price-impact gates applied.
4. **Assemble.** Build the transaction with pair-aware, decimal-precise amounts.
5. **Simulate.** Run every transaction through `simulateTransaction` (Solana) or `eth_call` (EVM) **before** a Sign button is exposed. Real reverts surface as readable errors; the user never burns gas on a guaranteed failure.
6. **Sign → submit → track.** The wallet signer fires; the agent watches for confirmation; the card updates in real time and the outcome is recorded.

A signature, once produced, is persisted to the originating chat card so its confirmed state survives navigation and reloads — the Sign button cannot reappear and cause an accidental double-submission.

## 7. Liquid staking, unstaking, and positions

Liquid staking is treated as a swap into a yield-bearing receipt token, and unstaking as the inverse — both fully wallet-signed and instant.

- **Stake.** "Stake 0.5 SOL" routes SOL into a liquid-staking token (jitoSOL via Jito, mSOL via Marinade) through a single signed Jupiter transaction; "stake 0.1 ETH" routes ETH into stETH/rETH/cbETH and others via Enso. The card shows the live APY (sourced from DefiLlama per-pool history) and the projected yearly yield before the user signs.
- **Unstake.** "Unstake my jitoSOL" / "unstake 0.5 stETH" / "unstake all my mSOL" performs the reverse liquid redemption — the receipt token is swapped back to its underlying instantly, with no epoch wait. Slippage is tuned per asset so the stake-pool redemption route clears its minimum-out reliably. Imperative unstake commands execute; "should I unstake?" is reasoned, not executed.
- **Positions & earnings.** The portfolio surfaces a dedicated **Staking & Positions** view. Each open liquid-staking position shows its balance, USD value, live APY, projected yearly yield, and **realized earnings** — computed as the appreciation of the currently held receipt token above the average rate the user paid to enter, derived from their own recorded stake history. This cost-basis method is robust to entry/exit churn and reflects only genuine accrued yield.

The portfolio itself is a multi-wallet, multi-chain balance aggregator that scans Solana plus fifteen EVM networks. To keep the surface responsive, the last-known balance is persisted client-side and shown instantly while a fresh scan runs concurrently in the background; transient scan failures never overwrite good data with an empty result.

## 8. Multi-chain coverage

Execution spans Solana and seven EVM chains; balance aggregation spans Solana and fifteen EVM networks (Ethereum, BNB Chain, Polygon, Arbitrum, Optimism, Base, Avalanche, zkSync Era, Linea, Scroll, Mantle, Fantom, Gnosis, Celo, Cronos).

The table below lists every protocol the agent **routes to**. The way the user is routed depends on whether that protocol is currently *one-click executable* in-app or *deep-linked* to its own UI:

- **Executable today (one-click, simulated and fork-proven):** Aave V3 and Compound V3 supply on Ethereum, Base and Arbitrum; Uniswap V2 LP on Ethereum; LST staking via Lido, Rocket Pool, Marinade, Jito and Sanctum.
- **Routed via deep-link card today:** every other row. The agent still resolves the right pool, surfaces the Sentinel score and a pre-filled action URL into the protocol's own app — execution itself stays in the protocol's UI. Bringing these in-app is the focus of Section 13.

| Chain | Swap | Bridge | Supply / Lend | LP Deposit | LST Stake |
|---|---|---|---|---|---|
| Solana | Jupiter | deBridge | Lulo, Save, Drift *(research / deep-link)* | Raydium, Orca, Meteora, Kamino | Marinade, Jito, Sanctum + more |
| Ethereum | Enso / 0x | deBridge | Aave V3, Compound V3, Spark, Morpho | Uniswap V2 / V3 / V4, Curve, Balancer, Yearn | Lido, Rocket Pool, EtherFi, Frax |
| Base | Enso / 0x | deBridge | Aave V3, Compound V3, Moonwell | Uniswap V3, Aerodrome | Lido on Base |
| Arbitrum | Enso / 0x | deBridge | Aave V3, Compound V3 | Uniswap V3, Camelot, Pendle | Rocket Pool |
| Optimism | Enso / 0x | deBridge | Aave V3 | Uniswap V3, Velodrome | Lido |
| Polygon | Enso / 0x | deBridge | Aave V3, Compound V3 | Uniswap V3, Quickswap | Stader |
| BNB Chain | Enso / 0x | deBridge | Venus | PancakeSwap V3 + V2 | Binance staked tokens |
| Avalanche | Enso / 0x | deBridge | Aave V3, Benqi | Trader Joe V2 | Benqi liquid staking |

## 9. Security model

- **Non-custodial.** Ilyon never holds keys or funds. Transactions are built unsigned and signed in the user's wallet.
- **Pre-sign simulation.** No Sign button is exposed for a transaction that has not passed `simulateTransaction` / `eth_call` against live state. Guaranteed-revert transactions are caught before the user pays gas.
- **Approval hygiene (Shield).** Continuous audit of outstanding EVM token approvals with one-click revoke for stale or oversized allowances.
- **Refusal over guessing.** Incomplete or contradictory requests are refused with a clarification rather than auto-completed into a transaction.
- **Signal, not guarantee.** The Sentinel score is an aid to judgment, not a warranty. DeFi carries the risk of total loss; users must do their own research before signing.

## 10. Solana Actions / Blinks

Every token report and yield position can be emitted as a shareable, signed-action card. A link shared anywhere a Blink unfurls renders a deposit or action button on the receiving end, served from public, CORS-open Solana Action endpoints.

## 11. Open primitives

The repository is MIT-licensed and self-hostable; a full deployment runs in a small set of containers behind a single reverse proxy. Three primitives are designed for reuse by other teams:

1. **The Sentinel score** — a chain- and protocol-agnostic risk number with explicit dimension breakdowns.
2. **The card schema** — a typed, discriminated-union card model that lets any agent or wallet render Ilyon-quality cards without re-implementing layout logic.
3. **The intent layer** — natural language → typed JSON tool calls covering swap, bridge, supply, deposit_lp, stake, unstake, transfer, search, and analyze. Drop in your own LLM router and reuse the entire downstream pipeline.

A partner-facing JSON API exposes the agent stream, token analysis, portfolio aggregation, the Shield approval audit, the filtered yield universe, and the Blinks endpoints.

## 12. Technology

- **Backends** — Python 3.11, async web frameworks, Pydantic v2, SQLAlchemy 2.0 async, Redis 7, PostgreSQL 16.
- **Frontend** — Next.js 14 (app router), React 18, TypeScript 5, Tailwind, Radix, lucide-react.
- **AI** — multi-provider LLM routing with structured tool-use for the conversational and routing layers; the Sentinel risk math and allocation composer are deterministic Python with no model in the loop.
- **DeFi infrastructure** — Enso, 0x, Jupiter, deBridge, DefiLlama, DexScreener, RugCheck, Helius, Moralis, Birdeye, GeckoTerminal, Honeypot.
- **Solana** — `@solana/web3.js`, `@solana/spl-token`, Orca/Meteora/Raydium SDKs.
- **Deployment** — Docker Compose, Caddy v2, GitHub Actions, single-VPS layout with staging/production isolation.

## 13. Roadmap

- **In-chat Solana CLMM mint** — native Raydium CLMM / Orca Whirlpool position mint, including range-NFT issuance, without leaving the chat.
- **Smart-account batching** — ERC-4337 + session keys to collapse multi-step EVM zaps into a single signature.
- **MEV protection** — Flashbots Protect + CoW routing as a per-user toggle for high-value swaps.
- **Auto-rebalancing vaults** — first-party vaults on Uniswap V3 + Aerodrome Slipstream with automatic range rebalancing.
- **Unified multi-wallet identity** — one EVM and one Solana wallet bound into a single portfolio with cross-chain Sentinel scoring.

## 14. Disclaimer

Ilyon AI is non-custodial software. It never holds user funds; every transaction is signed in the user's own wallet. The Sentinel score is a signal, not a guarantee — always do your own research before signing. Trading DeFi assets carries the risk of total loss, and the developers are not responsible for user outcomes. **Ilyon AI has no token and conducts no token sale; any asset claiming otherwise is fraudulent.**

---

*MIT-licensed. Self-host: `git clone … && docker compose up -d --build` (see repository README for full instructions). Live: [ilyonai.com](https://ilyonai.com).*
