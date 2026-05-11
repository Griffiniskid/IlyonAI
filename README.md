# Ilyon AI

**AI-native DeFi intelligence + execution copilot for Solana and EVM.**

> Live at **[ilyonai.com](https://ilyonai.com)** — chat-driven token scoring, yield ranking, capital allocation, and wallet-gated transaction routing.

![Multi-Chain](https://img.shields.io/badge/Multi--Chain-Solana%20%7C%20Ethereum%20%7C%20Base%20%7C%20Arbitrum%20%7C%20BSC%20%7C%20Polygon%20%7C%20Optimism%20%7C%20Avalanche-9945FF?style=for-the-badge)
![Solana Actions](https://img.shields.io/badge/Solana%20Actions-Blinks%20Ready-9945FF?style=for-the-badge&logo=solana)

Ilyon AI is an open agentic DeFi platform. One chat box ranks live opportunities across DefiLlama, applies the Sentinel risk score, composes capital allocations, and builds protocol-specific unsigned transactions that the user signs in their own wallet (Phantom, MetaMask, Solflare, Backpack, OKX, Coinbase Wallet, WalletConnect).

---

## What it does

| Surface | Capability |
|---------|-----------|
| **Agent chat** (`POST /api/v1/agent`, SSE) | Typed-tool LLM agent. Streams `thought / tool / observation / card / final` frames. |
| **Sentinel scoring** | Unified 0–100 risk score for tokens, pools, whales, entities, and shield surfaces. |
| **Allocation planner** | Sizes 1–N positions across chains under risk caps, blended APY, and exit-depth constraints. |
| **Pool discovery** | Filters DefiLlama by chain, asset, APY band, TVL floor, audit/incident flags. |
| **Same-chain swap** | Jupiter (Solana) and Enso (EVM) route quotes with slippage + price-impact gates. |
| **Cross-chain bridge** | Bridge-aware execution plan; previews fees, ETA, destination receive. |
| **LST staking** | Direct stake to Lido, Marinade, Jito, Sanctum, RocketPool, and 18+ more LSTs. |
| **Shield (approvals)** | EVM token-approval audit + one-click revoke. |
| **Predictive rug detection** | Behavioral pattern analysis on liquidity staging, sell pressure, volume/price divergence. |
| **Serial scammer registry** | Cross-chain deployer-wallet forensics. |
| **Solana Blinks** | Shareable signed-action cards for token reports. |

---

## Pool execution — per-pool routing

The runtime classifies every pool intent and routes it to the safest builder it can prove works for that pool type. Five paths, exactly one per request:

| Pool family | Route | Card |
|---|---|---|
| EVM lending (Aave V3, Compound V3) | Direct `approve` + `supply` calldata, pre-sim'd via `eth_call` | `execution_plan_v3` |
| EVM V3 / CLMM (Uniswap V3/V4, Pancake V3, Aerodrome Slipstream, Ramses, …) | Deeplink to the exact pool on the protocol app (range NFTs require a UI step) | `pool_link` |
| EVM V2 / stable / vault (Curve, Balancer, Uniswap V2, Yearn, Gamma, Arrakis, …) | Deeplink to the exact pool on the protocol app (V2 zap composer ships in Phase 2) | `pool_link` |
| Solana LST (Marinade, Jito, Sanctum, …) | Direct Jupiter route into the LST mint, single signed tx | `execution_plan_v3` |
| Solana AMM (Raydium AMM, Orca Whirlpools, Meteora) | Pair-aware prep swap into the pool's *missing* token via Jupiter + deeplink to finish on the protocol app | `execution_plan_v3` + protocol URL |

Same-chain swap, bridge, and LST stake execute end-to-end on every chain.

### Execution hardening

- **Pre-sign simulation gate.** Every Solana tx runs through `connection.simulateTransaction({sigVerify: false, replaceRecentBlockhash: true})`; every EVM tx runs through `eth_call` against a public mainnet RPC. Non-benign reverts abort the build before the user sees a Sign button.
- **Pair-aware Solana prep swap.** Adapters read the pool's actual underlying mints from DefiLlama and swap the input into the side the user does *not* hold. `WSOL-AURA` stages `WSOL → AURA`, not `WSOL → USDC`.
- **Decimal-precision amounts.** All human-readable amounts on the wire are fixed-precision strings (`"0.1"`, not `"0.1111111111111111"`). No `float` leaks into card payloads.
- **Real Kamino REST.** Tries `api.kamino.finance/v2/transactions/deposit` first, falls back to a Jupiter proxy with an explicit "not a Kamino vault deposit" banner if Kamino is unreachable.

The full diagnosis + roadmap for the in-flight V3 range UI, V2 zap composer, native Curve adapter, and Meteora DLMM bin distribution lives at [`docs/POOL_EXECUTION_FIX_PLAN.md`](docs/POOL_EXECUTION_FIX_PLAN.md).

---

## Architecture

```
ilyon-ai/
├── src/                       # Python aiohttp API (Sentinel)
│   ├── main.py                  # Service entrypoint, route registration, lifespan hooks
│   ├── api/                     # HTTP surface
│   │   ├── routes/agent.py      # SSE agent runtime (POST /api/v1/agent)
│   │   ├── routes/analysis.py   # Token analysis lifecycle (init_analyzer)
│   │   ├── routes/blinks.py     # Solana Actions endpoints
│   │   ├── schemas/agent.py     # Pydantic ToolEnvelope, CardType, payloads
│   │   └── middleware/cors.py   # Single source of CORS truth
│   ├── agent/                   # Typed-tool LLM agent
│   │   ├── tools/               # ~40 tools (swap, bridge, build_yield_*, allocate_*…)
│   │   ├── protocol_urls.py     # Per-protocol pool deeplink resolver
│   │   └── intent_router.py     # Detector short-circuits (swap/sell/buy/bridge/stake/transfer)
│   ├── allocator/composer.py    # Position sizing + protocol_url stamping
│   ├── scoring/                 # Sentinel score components
│   ├── defi/execution/          # Step models, signing-plan builder
│   ├── data/                    # DexScreener, RugCheck, DefiLlama, Helius, Honeypot
│   ├── analytics/               # Deployer forensics, anomaly detection
│   ├── shield/                  # EVM approval scanner
│   └── storage/                 # Postgres (SQLAlchemy async) + Redis cache
├── web/                       # Next.js 14 frontend
│   ├── app/                     # Routes: /, /agent/{chat,portfolio,swap}, /alerts, /audits…
│   ├── components/agent/cards/  # AllocationCard, ExecutionPlanCard, PoolLinkCard, SwapQuoteCard…
│   ├── types/agent.ts           # TypeScript mirror of Pydantic CardType
│   └── lib/                     # Hooks, providers (QueryClient, wallet, toast)
├── IlyonAi-Wallet-assistant-main/server/   # Node sidecar — wallet assistant API
├── docker-compose.yml         # web · api · assistant-api · solana-yield-builder · postgres · redis
├── deploy/                    # Caddyfile + prod/staging configs
└── docs/ARCHITECTURE_LIVE.md  # Source-of-truth architecture doc
```

### Agent runtime data flow

1. **Browser** opens SSE to `POST /api/v1/agent` with `{message, session_id, evm_wallet?, solana_wallet?}`.
2. **Intent router** short-circuits common verbs (swap, sell, buy, bridge, transfer, stake) before LLM.
3. **Agent loop** emits `thought`, calls typed tools, receives validated `ToolEnvelope` observations.
4. **Tools** hit DefiLlama / Jupiter / Enso / Helius / DexScreener / Sentinel scoring + composer.
5. **Cards** stream as `card` events (`allocation`, `execution_plan_v3`, `pool_link`, `swap_quote`, `sentinel_*`…).
6. **Frontend** renders cards; execute buttons open wallet signers for real transactions, or external links for paused pool deposits.

---

## Quick start

### Prerequisites
- Python 3.10+
- Node 20+ (for `web/` and assistant sidecar)
- Docker + Docker Compose (recommended)
- API keys: AI provider (OpenAI/OpenRouter), Helius (Solana RPC), Moralis (EVM), optional Telegram bot

### Local dev (Docker)
```bash
cp .env.example .env
# fill keys; required: OPENAI_API_KEY / OPENROUTER_API_KEY, POSTGRES_PASSWORD
export POSTGRES_PASSWORD=change_me

docker-compose up -d
# web   → http://localhost:3000
# api   → http://localhost:8000
```

### Local dev (no Docker)
```bash
# Backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m src.main         # serves API on :8000

# Frontend
cd web && npm install && npm run dev     # :3000

# Assistant sidecar (optional)
cd IlyonAi-Wallet-assistant-main/server && npm install && npm run dev
```

---

## Configuration

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENAI_API_KEY` *or* `OPENROUTER_API_KEY` | ✅ | LLM inference |
| `POSTGRES_PASSWORD` | ✅ (Docker) | Postgres init |
| `DATABASE_URL` | ✅ (non-Docker) | SQLAlchemy async URL |
| `REDIS_URL` | recommended | Tool-result + price caching |
| `HELIUS_API_KEY` | recommended | Solana RPC + balance/transaction history |
| `MORALIS_API_KEY` | recommended | EVM token balances + approvals |
| `ENSO_API_KEY` | recommended | EVM yield exec routing |
| `JUPITER_API_KEY` | optional | Pro-tier Solana swap |
| `BOT_TOKEN` | optional | Telegram interface |
| `ALLOWED_USERS` | recommended (TG) | Comma-separated Telegram IDs |
| `LOG_REDACT_SENSITIVE` | recommended | Scrub secrets from logs |

See `.env.example` for the full set.

---

## API surface

| Endpoint | Method | Notes |
|----------|--------|-------|
| `/api/v1/agent` | POST (SSE) | Primary agent chat. Streams typed cards. |
| `/api/v1/analyze` | POST | Token analysis (full pipeline). |
| `/api/v1/quick` | POST | Quick risk check. |
| `/api/v1/portfolio` | GET | Multi-wallet aggregation. |
| `/api/v1/shield/approvals` | GET | EVM approval audit. |
| `/api/v1/blinks/*` | GET | Solana Actions metadata + tx build. |
| `/actions/*` | GET | Public Solana Action endpoints (CORS-open). |

Full schema in `src/api/schemas/`.

---

## Validation

Live validation harness against `https://ilyonai.com`:
```bash
python scripts/validate_no_exec.py
```
Runs 5 real SSE requests: Aave V3 pool link, Raydium pool link, multi-chain allocation, Solana swap exec, yield discovery.

Unit + integration tests:
```bash
pytest tests/                       # backend
cd web && npm run test              # frontend (Vitest)
cd web && npm run build             # type-check + Next.js build
```

---

## Deployment

Production stack runs on a single VPS behind Caddy:
- Caddy reverse-proxies `web` (3000) and `api` (8000)
- Docker Compose orchestrates web / api / assistant-api / solana-yield-builder / postgres / redis
- Postgres + Redis volumes persisted on host

See `deploy/README.md` for SSH key setup, swap configuration (Next.js build needs ≥4 GB), and rollback procedure.

---

## Security

- Sentinel scoring is risk *signal*, not a guarantee. Always DYOR.
- The platform never holds custody — every transaction is built unsigned and signed in the user's wallet.
- Report vulnerabilities to **security@ilyonai.io**.
- Never commit `.env`; rotate API keys; enable `LOG_REDACT_SENSITIVE=true` in prod.

---

## Contributing

1. Fork
2. `git checkout -b feature/your-thing`
3. Open PR against `main` (with-exec) or the active `no-exec-pools-*` branch
4. CI runs `pytest`, `npm run lint`, `npm run build`

---

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

Ilyon AI surfaces analysis and risk signal for educational use. It is not financial advice. Trading DeFi assets involves risk of total loss. You sign every transaction yourself; the developers are not responsible for losses.
