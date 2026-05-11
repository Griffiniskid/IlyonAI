# Ilyon AI

**The AI-native DeFi copilot. One chat box. Every chain. Every action signed in your own wallet.**

> Live demo → **[ilyonai.com](https://ilyonai.com)**

![Multi-Chain](https://img.shields.io/badge/Multi--Chain-Solana%20%7C%20Ethereum%20%7C%20Base%20%7C%20Arbitrum%20%7C%20BSC%20%7C%20Polygon%20%7C%20Optimism%20%7C%20Avalanche-9945FF?style=for-the-badge)
![Solana Actions](https://img.shields.io/badge/Solana%20Actions-Blinks%20Ready-9945FF?style=for-the-badge&logo=solana)
![Non-Custodial](https://img.shields.io/badge/Non--Custodial-Wallet--Signed-10B981?style=for-the-badge)

Ilyon AI is an agentic DeFi platform that turns natural-language intent into wallet-gated execution across Solana and seven EVM chains. Ask a question, get an answer; ask for a swap, get a signable transaction; ask for a yield strategy, get a sized allocation across audited protocols — all from a single chat box, with risk-scored every step of the way.

---

## Why it matters

Decentralised finance is the most powerful financial primitive ever shipped to the open internet, and the worst-designed consumer surface in software history. Today a user who wants to earn yield in a single liquidity pool needs to: pick a chain, pick a DEX, find the right pool, confirm it's not a rug, route a swap from whatever they already hold, decide on slippage, pay gas in the right native asset, sign three transactions in two different wallets, and pray they aren't sandwiched.

**Ilyon AI compresses that ten-step gauntlet into one sentence.** The agent reads live opportunities, scores them with the Sentinel risk engine, composes a capital allocation under risk caps, and emits wallet-ready transactions. The user signs in Phantom or MetaMask. Funds never leave their custody. Every recommendation comes with a numerical safety score, a deployer-wallet check, an exit-liquidity estimate, and a Shield audit of token approvals already on their wallet.

---

## What it does

| Surface | What the user sees |
|---|---|
| **Agent chat** | A streaming conversational interface that returns typed cards — token reports, pool reports, allocation matrices, execution plans — instead of plaintext. Every card is interactive. |
| **Sentinel risk score** | A unified 0–100 score across five surfaces: token security, pool durability, whale clustering, deployer entity, and Shield approval surface. Every opportunity carries the score and the dimension breakdown that produced it. |
| **Allocation planner** | "Give me $5k of balanced yield on Ethereum and Base" sizes 1–5 positions, applies per-position caps, blends APY, and ranks for exit depth. |
| **Pool discovery** | Natural-language filters over the entire DeFi yields universe — chain, asset family, APY band, TVL floor, audit + incident flags. |
| **One-click swap** | Same-chain swap across all eight chains, routed through Jupiter (Solana) and Enso (EVM) with slippage and price-impact gates baked in. |
| **Cross-chain bridge** | Unified bridge layer over deBridge with fee, ETA, and destination-receive preview before signing. |
| **Liquid staking** | Direct deposit into Marinade, Jito, Sanctum, Lido, Rocket Pool, EtherFi, and twenty-plus more LSTs — single signed transaction, native receipt token returned. |
| **Liquidity pool deposit** | Single-token zap into Raydium, Orca, Meteora, Uniswap V3 / V4, PancakeSwap, Aerodrome, Curve, and Yearn. V3 / CLMM pools open a live range-selector card where APR and capital efficiency recompute as the user drags the range. |
| **Shield (token approvals)** | Continuous EVM token-approval audit. One-click revoke for anything stale or oversized. |
| **Predictive rug detection** | Behavioural analysis on liquidity staging, deployer wallet history, and price-volume divergence to surface rugs *before* they happen. |
| **Serial scammer registry** | Cross-chain deployer-wallet forensics that ties each new contract back to the actor behind it. |
| **Solana Blinks** | Every token report and yield position ships as a shareable signed-action card — share a link, get a deposit button on the receiving end. |

---

## Architecture

Ilyon AI is composed of five cooperating services and a Next.js front-end. Every piece is open-source MIT and runs in containers behind a single Caddy reverse proxy.

```
                          ┌────────────────────────┐
                          │  Next.js 14 Frontend   │
                          │  (chat · cards · TS)   │
                          └─────────┬──────────────┘
                                    │ SSE
                                    ▼
                ┌─────────────────────────────────────┐
                │       Sentinel API (aiohttp)        │
                │                                     │
                │   • Typed-tool LLM agent            │
                │   • Intent router                   │
                │   • Sentinel scoring                │
                │   • Allocation composer             │
                │   • Solana Actions / Blinks         │
                └─────┬─────────────┬──────────────┬──┘
                      │             │              │
              ┌───────▼──┐   ┌──────▼─────┐   ┌────▼──────┐
              │ Wallet   │   │  Solana    │   │ Postgres  │
              │ Assistant│   │  Yield     │   │ + Redis   │
              │ (Python) │   │  Builder   │   │           │
              │ EVM swap │   │  (Node)    │   │ sessions  │
              │ + bridge │   │  Raydium · │   │ + cache   │
              │ + supply │   │  Orca ·    │   │           │
              │ via Enso │   │  Meteora · │   │           │
              │ + 0x +   │   │  Kamino ·  │   │           │
              │ deBridge │   │  Marinade  │   │           │
              └──────────┘   └────────────┘   └───────────┘
```

### What every service does

- **Frontend** (`web/`) — Next.js 14 + Radix UI + Tailwind. Streams a server-sent-event channel from the agent and renders typed cards: `allocation`, `execution_plan_v3`, `pool_deposit_v3` (with the interactive range selector), `pool_link`, `swap_quote`, eight Sentinel report variants, and more. Wallet integration covers Phantom, MetaMask, Solflare, Backpack, OKX, Coinbase Wallet, and WalletConnect.
- **Sentinel API** (`src/`) — Python aiohttp service. Hosts the LLM tool-use loop, the Sentinel risk engine, the allocation composer, the pool-resolution layer, and every Solana Actions / Blinks endpoint. Talks to DefiLlama, DexScreener, RugCheck, Helius, Moralis, Birdeye, GeckoTerminal, and Honeypot.
- **Wallet Assistant** (`IlyonAi-Wallet-assistant-main/server/`) — Python sidecar that builds EVM transactions through Enso (yield routing), 0x (swaps), and deBridge (cross-chain). Returns calldata pre-simulated via `eth_call` so the user never pays gas on a guaranteed revert.
- **Solana Yield Builder** (`services/solana-yield-builder/`) — Node sidecar with first-party adapters for Raydium, Orca Whirlpools, Meteora DLMM, Kamino vaults, Marinade, Jito, Sanctum, Jupiter. Builds versioned transactions with Address Lookup Tables, pair-aware prep swaps, and a mandatory `simulateTransaction` gate before any tx leaves the sidecar.
- **Postgres + Redis** — session memory and tool-result cache. Redis fronts price/quote lookups so repeated user questions feel instant.

### Multi-chain coverage

| Chain | Swap | Bridge | Supply / Lend | LP Deposit | LST Stake |
|---|---|---|---|---|---|
| Solana | Jupiter | deBridge | Lulo, Save, Drift | Raydium, Orca, Meteora, Kamino | Marinade, Jito, Sanctum + 18 |
| Ethereum | Enso / 0x | deBridge | Aave V3, Compound V3, Spark, Morpho | Uniswap V3/V4, V2, Curve, Balancer, Yearn | Lido, RocketPool, EtherFi, Frax |
| Base | Enso / 0x | deBridge | Aave V3, Compound V3, Moonwell | Uniswap V3, Aerodrome (CL + AMM) | Lido on Base |
| Arbitrum | Enso / 0x | deBridge | Aave V3, Compound V3 | Uniswap V3, Camelot, Pendle | RocketPool |
| Optimism | Enso / 0x | deBridge | Aave V3 | Uniswap V3, Velodrome | Lido |
| Polygon | Enso / 0x | deBridge | Aave V3, Compound V3 | Uniswap V3, Quickswap | Stader |
| BNB Chain | Enso / 0x | deBridge | Venus | PancakeSwap V3 + V2 | Binance staked SOL |
| Avalanche | Enso / 0x | deBridge | Aave V3, Benqi | Trader Joe V2 | Benqi liquid staking |

---

## How a deposit works end-to-end

Below is the actual data flow for `"Add liquidity to Uniswap V3 USDC/WETH on Ethereum with $100"`.

1. **Browser** opens an SSE channel to `POST /api/v1/agent` with the user's question, wallet addresses, and a session id.
2. **Intent router** classifies the message — pool deposit, supply, swap, bridge, stake, transfer — and short-circuits the deterministic cases without the LLM.
3. **Pool resolver** matches the natural-language pool reference to a real on-chain pool: pair tokens, fee tier, current price, tick spacing, sqrtPriceX96, TVL, fee revenue.
4. **Sentinel scoring** lifts the safety / durability / exit / confidence dimensions for the pool, the underlying tokens, and the deployer.
5. **Strategy router** picks the right builder for the pool type — V2 zap (two swaps + addLiquidity), V3 mint (range-aware optimal ratio + NonfungiblePositionManager), stable single-sided (Curve's native multi-sided `add_liquidity`), auto-vault (Kamino / Gamma).
6. **Quote + assemble** through the right provider (Jupiter on Solana, Enso / 0x on EVM) with pair-aware decimal-precision amounts.
7. **Pre-sign simulation** runs every transaction through `simulateTransaction` (Solana) or `eth_call` (EVM) before exposing a Sign button. Real reverts surface as readable errors; the user never burns gas on a guaranteed failure.
8. **Card streams** to the frontend. For V3 pools the card is an interactive range selector — capital efficiency, in-range probability, and APR recompute on every drag, entirely on the frontend, with zero round-trips.
9. **Sign → submit → track.** The wallet signer fires, the agent watches for confirmation, the card updates in real time.

---

## API surface

The Sentinel API is open and partner-ready. All endpoints return JSON; the agent endpoint streams server-sent events.

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/agent` | POST (SSE) | Primary chat. Streams `thought / tool / observation / card / final` frames. |
| `/api/v1/analyze` | POST | Full token analysis: security, holders, AI red-flags, recommendation. |
| `/api/v1/quick` | POST | Lightweight risk check for embeds. |
| `/api/v1/portfolio` | GET | Multi-wallet aggregation across all eight chains. |
| `/api/v1/shield/approvals` | GET | EVM token-approval audit. |
| `/api/v1/yields` | GET | Filtered yield universe — chain, APY, TVL, risk. |
| `/api/v1/blinks/*` | GET | Solana Actions metadata + tx build for shareable signed actions. |
| `/actions/*` | GET | Public CORS-open Solana Action endpoints. |

Full schemas live in `src/api/schemas/`. Card payload types are mirrored 1:1 in `web/types/agent.ts` so any partner front-end can render Ilyon cards natively.

---

## What's open

Everything in this repository is MIT-licensed and immediately self-hostable. A complete deployment of the live site runs in five containers behind a single Caddy proxy — see `deploy/README.md` for the VPS layout and `docker-compose.yml` for the service graph.

We expose three primitives any other team can build on:

1. **The Sentinel score** — a chain-and-protocol-agnostic risk number with explicit dimension breakdowns.
2. **The card schema** — a typed, discriminated-union card model that lets any agent or wallet render Ilyon-quality cards without re-implementing the layout logic.
3. **The intent layer** — natural-language → typed JSON tool calls covering swap, bridge, supply, deposit_lp, stake, transfer, search, analyze. Drop in your own LLM router and reuse the entire downstream pipeline.

---

## Roadmap

- **Solana CLMM in-chat mint.** Native Raydium CLMM / Orca Whirlpool position mint without leaving the chat, including range NFT issuance.
- **Smart-account batching.** ERC-4337 + session keys collapse multi-step EVM zaps into a single user signature.
- **MEV protection on EVM.** Flashbots Protect + CoW Protocol routing as a per-user toggle for high-value swaps.
- **Auto-rebalancing vaults.** First-party Ilyon vaults that ride on top of Uniswap V3 + Aerodrome Slipstream with automatic range rebalancing.
- **Multi-wallet identity.** Sign in with one EVM and one Solana wallet; Ilyon binds both into a single portfolio with cross-chain Sentinel scoring.

---

## Tech stack

- **Backend** — Python 3.11, aiohttp, Pydantic v2, SQLAlchemy 2.0 async, Redis 7, PostgreSQL 16
- **Frontend** — Next.js 14 (app router), React 18, TypeScript 5, Tailwind CSS, Radix UI, lucide-react
- **AI** — OpenRouter (multi-provider routing) with structured tool-use; Sentinel scoring + allocation composer are deterministic Python, no LLM in the loop for risk math
- **DeFi infra** — Enso, 0x, Jupiter, deBridge, DefiLlama, DexScreener, RugCheck, Helius, Moralis, Birdeye, GeckoTerminal, Honeypot.is
- **Solana** — `@solana/web3.js`, `@solana/spl-token`, `@orca-so/whirlpools-sdk`, `@meteora-ag/dlmm`, `@raydium-io/raydium-sdk-v2`
- **Deploy** — Docker Compose, Caddy v2, GitHub Actions, single-VPS layout with staging + prod isolation

---

## Try it

- **Web app** — [ilyonai.com](https://ilyonai.com)
- **Twitter** — [@ilyonProtocol](https://x.com/ilyonProtocol)
- **Telegram** — [t.me/ilyonProtocol](https://t.me/ilyonProtocol)
- **Self-host** — `git clone … && docker compose up -d --build`

---

## Security & disclaimer

Ilyon AI is non-custodial. The platform never holds user funds; every transaction is built unsigned and signed in the user's own wallet. Sentinel scoring is a *signal*, not a guarantee — always DYOR before signing. Trading DeFi assets carries the risk of total loss; the developers are not responsible for user outcomes. Report vulnerabilities to `security@ilyonai.io`.

## License

MIT — see [LICENSE](LICENSE).
