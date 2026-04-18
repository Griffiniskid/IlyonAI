# Ilyon AI

**AI-Powered Multi-Chain DeFi Intelligence Platform**

> Real-time token security analysis, smart money tracking, whale monitoring, and portfolio intelligence across Solana and all major EVM chains — powered by AI.

![Solana Frontier Hackathon](https://img.shields.io/badge/Solana-Frontier%20Hackathon-9945FF?style=for-the-badge&logo=solana&logoColor=white)
![Multi-Chain](https://img.shields.io/badge/Multi--Chain-Ethereum%20%7C%20Solana%20%7C%20Base%20%7C%20BSC%20%7C%20Arbitrum%20%7C%20Polygon-9945FF?style=for-the-badge)
![Blinks Ready](https://img.shields.io/badge/Solana%20Actions-Blinks%20Ready-9945FF?style=for-the-badge&logo=solana)
![Next.js](https://img.shields.io/badge/Next.js-15-000000?style=for-the-badge&logo=next.js)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)

---

## Solana Frontier Hackathon

Ilyon AI is a participant in the **Solana Frontier Hackathon**. Our platform is deeply integrated with Solana and built to strengthen the Solana ecosystem by providing the intelligence layer that traders, builders, and communities need to operate safely on-chain.

### How Ilyon AI Integrates with Solana

**Native Wallet Integration** — Ilyon AI connects directly to Solana wallets (Phantom, Solflare, Backpack, and others) via `@solana/wallet-adapter`. Users authenticate by signing a message with their connected wallet, enabling session-based access to portfolio tracking, wallet analysis, and personalized intelligence. No email, no password — your wallet is your identity.

**Real-Time On-Chain Data via Helius** — The backend consumes Solana on-chain data through Helius RPC and DAS API endpoints. This powers token metadata resolution, holder distribution analysis, mint/freeze authority checks, LP lock verification, and deployer wallet history — all in real time. When Helius data is unavailable, the platform degrades gracefully to direct Solana RPC calls.

**Jupiter DEX Integration** — Ilyon AI integrates with Jupiter aggregator for Solana-specific honeypot detection. The system simulates swap routes through Jupiter to verify whether a token can actually be sold, calculates effective sell taxes, and detects hidden fee mechanisms that static analysis would miss.

**Smart Money & Whale Tracking** — The platform monitors $10K+ DEX swaps on Solana via WebSocket streams, identifying smart money wallets, tracking accumulation and distribution patterns, and surfacing whale activity in real time. All wallet addresses link directly to Solscan for on-chain verification.

**Solana Actions & Blinks** — Ilyon AI implements the Solana Actions specification, allowing token analysis reports to be shared as Blinks (Blockchain Links) on X (Twitter) and other platforms. Anyone clicking a Blink can view the security analysis directly in their Solana wallet interface without visiting the app.

**RugCheck Integration** — For Solana tokens, the platform integrates with RugCheck to verify LP lock status, detect bundled launches, and cross-reference community-reported risks — layering community intelligence on top of AI analysis.

**Portfolio Intelligence** — Connected Solana wallets get instant portfolio breakdowns: total value, 24h P&L, health scores, per-token safety ratings, and multi-chain exposure analysis. The platform reads token balances directly from the Solana blockchain and enriches them with market data and security scores.

### How Ilyon AI Helps the Solana Ecosystem

Solana's speed and low fees make it the most active chain for token launches — but that same accessibility creates opportunities for scams. Ilyon AI provides:

- **Pre-trade intelligence** so traders can assess risk before buying, not after losing money
- **Serial scammer tracking** that follows deployer wallets across multiple rug pulls, creating accountability
- **Whale transparency** that democratizes access to smart money flow data
- **Shareable security reports** via Blinks, so communities can protect each other
- **Ecosystem-level analytics** including Solana TVL tracking, trading volume charts, and market distribution data

---

## Features

### Dashboard
*Route: `/dashboard`*

The central hub providing a real-time overview of the Solana token ecosystem.

**What it shows:**
- **24h Trading Volume** — Aggregated DEX volume across tracked pairs with percentage change and a 14-day volume chart
- **Solana TVL** — Total value locked across Solana DeFi protocols
- **Total Liquidity** — Sum of liquidity across all tracked token pairs
- **SOL Price** — Current SOL/USD price with 24h change
- **Trading Volume Chart** — Interactive 14-day area chart with hourly granularity, tooltips showing precise values
- **Market Distribution** — Donut chart breaking down market composition (DeFi, memecoins, infrastructure, etc.) with percentages
- **Grade Distribution** — Horizontal bar chart showing how analyzed tokens distribute across safety grades (A through F)
- **Trending Tokens** — Top 5 trending tokens by velocity with price, 24h change, and direct links to analysis
- **Smart Money Activity** — Latest whale transactions showing wallet label, token, amount, and relative timestamp

**How to use:**
1. Navigate to `/dashboard` or click "Dashboard" in the sidebar
2. Click **Refresh** to pull the latest data across all widgets
3. Click any trending token to open its full analysis page
4. Click any whale transaction to view the wallet on Solscan
5. Use the "View All" links to drill into Trending or Whales feeds

---

### Trending Tokens
*Route: `/trending`*

Discover high-velocity tokens across Solana and all major EVM chains with real-time market data.

**Categories:**
- **Trending** — Tokens with the highest transaction velocity and social momentum
- **Top Gainers** — Biggest price increases in the last 24 hours
- **Top Losers** — Biggest price drops in the last 24 hours
- **New Pairs** — Recently created trading pairs

**Chain Filters:** Solana, Ethereum, Base, Arbitrum, BSC, Polygon, Optimism, Avalanche, or All Chains.

**Each token card displays:**
- Rank, symbol, name, and token logo
- Chain and DEX name
- Current price with 24h percentage change
- Market cap, liquidity, 24h volume, and pair age
- Transaction count (1h) with color-coded activity badges

**How to use:**
1. Select a category tab (Trending, Top Gainers, Top Losers, New Pairs)
2. Filter by chain using the chain selector
3. Click **Refresh** to force-fetch fresh data from DexScreener
4. Click any token card to open the full token analysis page
5. Cards are color-coded: green for gains, red for losses

---

### Token Analysis
*Route: `/token/[address]`*

Deep-dive security and market analysis for any token on any supported chain. This is the core intelligence feature.

**Analysis includes:**
- **Safety Score** (0-100) — AI-generated composite score factoring in contract security, deployer reputation, holder distribution, liquidity depth, and honeypot status
- **Security Checks** — Mint authority, freeze authority, LP lock status, contract verification, proxy detection, ownership renouncement
- **Market Data** — Price, market cap, volume, liquidity, holder count, top holder concentration
- **Website Analysis** — Domain age, SSL validity, content quality signals, social media presence
- **AI Analysis** — Detailed narrative assessment with red flags, green flags, and risk reasoning generated by multi-model AI (GPT-4o + Grok)
- **Whale Activity** — Recent large transactions for this specific token
- **REKT Context** — Related hack/exploit incidents from the REKT database

**How to use:**
1. Navigate to `/token` and enter any token contract address (Solana or EVM)
2. Or click any token from the Trending or Dashboard pages
3. For EVM tokens, append `?chain=ethereum` (or base, arbitrum, etc.) to the URL
4. The analysis runs automatically — wait for all sections to populate
5. Click **Refresh** to re-run the analysis with fresh data
6. Click **Share** to create a Solana Blink for sharing on X/Twitter
7. Use the **Copy** button to copy the token address
8. Click external links to view on Solscan (Solana) or Etherscan (EVM)

**Interpreting the Safety Score:**
| Score | Grade | Meaning |
|-------|-------|---------|
| 85-100 | A | Low risk — appears legitimate with strong fundamentals |
| 75-84 | B | Minor concerns — proceed with caution |
| 60-74 | C | Notable risks — significant red flags present |
| 45-59 | D | High risk — multiple serious concerns |
| 0-44 | F | Critical — high probability of scam or exploit |

---

### Smart Contract Scanner
*Route: `/contract`*

AI-powered smart contract security analysis for EVM chains. Analyzes verified source code or decompiles bytecode for unverified contracts.

**Supported chains:** Ethereum, Base, Arbitrum, BSC, Polygon, Optimism, Avalanche.

**What it detects:**
- Reentrancy vulnerabilities
- Integer overflow/underflow
- Access control issues (unprotected functions, missing modifiers)
- Backdoor functions (hidden mints, kill switches, blacklist mechanisms)
- Proxy patterns with upgrade risks
- Scam template similarity (known rug pull contract patterns)
- Gas optimization issues
- Unsafe external calls

**Each vulnerability shows:**
- Severity level (Critical, High, Medium, Low, Info)
- Vulnerability name and category
- Affected code location (function and line)
- Detailed description and recommended fix
- Expandable details with code context

**How to use:**
1. Navigate to `/contract`
2. Select the target EVM chain from the dropdown
3. Enter the contract address (0x...)
4. Click **Scan Contract** — the AI analyzer will process the contract
5. Review the vulnerability list sorted by severity
6. Expand each finding for details, affected code, and remediation steps
7. Click the Explorer link to view the contract source on-chain

---

### Smart Money Hub
*Route: `/smart-money`*

Real-time smart money flow analysis tracking $10K+ DEX swaps on Solana with WebSocket streaming.

**Metrics displayed:**
- **Net Flow** — Aggregate inflow minus outflow in USD
- **Inflow** — Total buy-side volume from tracked wallets
- **Outflow** — Total sell-side volume from tracked wallets
- **Flow Direction** — Accumulating, Distributing, or Neutral

**Sections:**
- **Top Buyers** — Table of wallets with largest buy volume, showing wallet address, USD amount, transaction count, token, DEX, and last seen time
- **Top Sellers** — Same format for sell-side
- **Transaction Feed** — Chronological list of all whale transactions with buy/sell indicators, wallet links to Solscan, token symbols, USD amounts, DEX name, and transaction signatures

**Stream status indicators:**
- **Live** (green pulse) — Connected to WebSocket, receiving real-time updates
- **Reconnecting** (yellow) — Attempting to re-establish WebSocket connection
- **Polling** (blue) — Falling back to HTTP polling when WebSocket is unavailable

**How to use:**
1. Navigate to `/smart-money`
2. Data streams in automatically — watch the live indicator
3. Filter the transaction feed by direction (Buys/Sells/All)
4. Set a minimum USD threshold to filter noise
5. Click any wallet address to view it on Solscan
6. Click transaction signatures to view the swap on Solscan
7. Use "Open Whales Feed" to go to the full whale tracker

---

### Whale Tracker
*Route: `/whales`*

Search and filter large transactions across Solana, Ethereum, Base, and Arbitrum.

**Filters:**
- **Minimum Amount (USD)** — Default $1,000, adjustable in $1,000 increments
- **Chain** — Solana, Ethereum, Base, Arbitrum, or All Chains
- **Type** — Buys only, Sells only, or All

**Each transaction shows:**
- Buy/sell indicator with color coding (green/red)
- Token symbol and name with link to token analysis
- Timestamp and DEX name
- Chain badge
- USD amount and token quantity
- Wallet address (linked to Solscan/Etherscan) with whale badge
- Wallet label (if identified)
- Transaction signature (linked to block explorer)

**How to use:**
1. Navigate to `/whales`
2. Set your minimum USD amount filter
3. Select a chain filter
4. Choose buy/sell type filter
5. Click **Search Transactions** to execute the query
6. Click **Refresh** to force-fetch fresh data bypassing cache
7. Click any token symbol to open its analysis page
8. Click wallet addresses to view on block explorer

---

### Portfolio
*Route: `/portfolio`*

Multi-wallet portfolio tracking with security scoring and risk analysis. Requires a connected Solana wallet.

**Portfolio summary:**
- **Total Value** — Aggregated USD value of all holdings
- **24h P&L** — Portfolio-wide profit/loss percentage
- **Token Count** — Number of distinct tokens held
- **Health Score** (0-100) — Overall portfolio safety rating

**Features:**
- **Holdings List** — Every token with balance, USD value, 24h change, safety score badge, and logo
- **Track Another Wallet** — Enter any Solana address to view its holdings alongside yours
- **Risk Context** — Related REKT incidents for your top holdings
- **Multi-Chain Exposure** — Table showing your exposure across different chains
- **Capability Risk Breakdown** — Detailed risk analysis of your portfolio's vulnerability surface

**How to use:**
1. Connect your Solana wallet (Phantom, Solflare, Backpack, etc.)
2. Your portfolio loads automatically with all token balances
3. Review safety score badges — green (70+), yellow (40-69), red (<40)
4. To track someone else's wallet, enter their Solana address and click **Track**
5. Authentication is required for wallet tracking — go to Settings first
6. Click any token to open its full analysis page
7. Click **Refresh** to re-fetch balances and prices

---

### Pool Analysis
*Route: `/pool/[id]`*

Detailed liquidity pool analysis for any DexScreener pair or pool address.

**How to use:**
1. Navigate to `/pool` and enter a pool address or DexScreener pair ID
2. Solana base58 addresses and EVM 0x addresses are auto-detected
3. The analysis page shows pool composition, TVL, volume, APY, and risk metrics

---

### Settings
*Route: `/settings`*

Account management and wallet authentication.

**Sections:**
- **Wallet Connection** — Connect/disconnect Solana wallets, view connection status
- **Session Authentication** — Sign a message to authenticate and unlock premium features (wallet tracking, API access)
- **Account Statistics** — Analysis count, tracked wallets, and alerts count (shown after authentication)
- **Notifications** — Toggle price alerts, whale activity alerts, and security alerts
- **Resources** — Links to documentation, Twitter, and Telegram

**How to use:**
1. Click the wallet button in the top-right to connect your Solana wallet
2. Click **Authenticate** and sign the message in your wallet
3. Once authenticated, your session persists until you sign out
4. Toggle notification preferences as desired

---

## Architecture

```
ilyon-ai/
├── src/                          # Python backend (aiohttp)
│   ├── main.py                   # Application entry point
│   ├── config.py                 # Pydantic settings from .env
│   ├── api/                      # HTTP API layer
│   │   ├── app.py                # aiohttp application factory
│   │   ├── routes/               # Route handlers
│   │   │   ├── analysis.py       # Token analysis endpoints
│   │   │   ├── blinks.py         # Solana Blinks/Actions
│   │   │   ├── actions.py        # Solana Actions specification
│   │   │   ├── whale.py          # Whale tracking endpoints
│   │   │   ├── transactions.py   # Transaction feed
│   │   │   └── entity.py         # Entity/wallet clustering
│   │   ├── services/             # Business logic services
│   │   │   ├── blink_service.py  # Blink generation
│   │   │   └── icon_generator.py # Dynamic icon creation
│   │   └── middleware/           # CORS, rate limiting
│   ├── core/                     # Analysis engine
│   │   ├── analyzer.py           # Main analysis orchestrator
│   │   ├── scorer.py             # Risk scoring system
│   │   └── models.py             # Data models
│   ├── chains/                   # Chain-specific clients
│   │   ├── solana/               # Solana RPC + Helius
│   │   └── address.py            # Multi-chain address utils
│   ├── data/                     # External data providers
│   │   ├── dexscreener.py        # Market data (all chains)
│   │   ├── jupiter.py            # Solana DEX aggregator
│   │   ├── rugcheck.py           # Solana LP verification
│   │   ├── honeypot.py           # Honeypot detection
│   │   └── solana.py             # Solana on-chain data
│   ├── ai/                       # AI analysis layer
│   │   ├── router.py             # Multi-model routing
│   │   └── openai_client.py      # OpenAI/OpenRouter client
│   ├── storage/                  # Persistence
│   │   ├── database.py           # PostgreSQL (SQLAlchemy async)
│   │   └── cache.py              # Redis caching
│   └── analytics/                # Advanced analysis
│       ├── wallet_forensics.py   # Deployer/scammer tracking
│       └── anomaly_detector.py   # Behavioral pattern detection
├── web/                          # Next.js frontend
│   ├── app/                      # App Router pages
│   │   ├── dashboard/            # Main dashboard
│   │   ├── trending/             # Trending tokens
│   │   ├── token/                # Token analysis
│   │   ├── contract/             # Contract scanner
│   │   ├── smart-money/          # Smart money hub
│   │   ├── whales/               # Whale tracker
│   │   ├── portfolio/            # Portfolio manager
│   │   ├── pool/                 # Pool analysis
│   │   └── settings/             # User settings
│   ├── components/               # Shared UI components
│   │   ├── ui/                   # Base components (card, button, badge, etc.)
│   │   ├── layout/               # App shell, sidebar, mobile nav
│   │   ├── token/                # Token-specific components
│   │   └── portfolio/            # Portfolio components
│   ├── lib/                      # Utilities
│   │   ├── api.ts                # Backend API client
│   │   ├── hooks.ts              # React Query hooks
│   │   ├── utils.ts              # Formatting, validation
│   │   └── feature-flags.ts      # Feature flag system
│   └── next.config.js            # Next.js configuration
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

### Analysis Pipeline

```
User Request
    │
    ├──► Data Collection (parallel)
    │       ├── DexScreener: price, liquidity, volume, pair age
    │       ├── Helius / Solana RPC: on-chain data, holders, authorities
    │       ├── RugCheck: LP lock status, bundled launch detection
    │       ├── Jupiter: swap simulation, sell tax calculation
    │       └── Website scraper: domain age, SSL, social links
    │
    ├──► Advanced Analytics (parallel)
    │       ├── Wallet forensics: deployer history, serial scammer detection
    │       ├── Anomaly detection: volume/price divergence, sell pressure buildup
    │       └── Honeypot simulation: buy/sell verification via DEX routers
    │
    ├──► AI Analysis
    │       ├── Structured prompt with all collected data
    │       ├── Multi-model analysis (GPT-4o + Grok)
    │       └── Red/green flag identification with reasoning
    │
    └──► Scoring & Output
            ├── AI score as primary metric (0-100)
            ├── Component scores for granular context
            ├── Hard caps for known scammers/honeypots
            └── Cached result with TTL for performance
```

---

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL 14+ (or Docker)
- Redis (optional, for caching)

### Backend Setup

```bash
# Clone the repository
git clone https://github.com/Griffiniskid/AISentinel.git
cd AISentinel

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys (see Configuration section)

# Run the backend server
python -m src.main
```

### Frontend Setup

```bash
cd web

# Install dependencies
npm install

# Configure environment
cp .env.local.example .env.local
# Edit .env.local — see Configuration section

# Run the development server
npm run dev
```

The frontend runs on `http://localhost:3000` and proxies API requests to the backend at `http://localhost:8080`.

### Docker Deployment

```bash
# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Set required password
export POSTGRES_PASSWORD=your_secure_password

# Start all services
docker-compose up -d
```

---

## Configuration

### Required API Keys

| Service | Purpose | Get Key |
|---------|---------|---------|
| **OpenRouter** or **OpenAI** | AI analysis engine | [openrouter.ai](https://openrouter.ai/keys) or [platform.openai.com](https://platform.openai.com/api-keys) |

### Recommended API Keys

| Service | Purpose | Get Key |
|---------|---------|---------|
| **Helius** | Solana RPC + DAS API (faster, more reliable) | [dev.helius.xyz](https://dev.helius.xyz/) (free tier available) |

### Backend Environment Variables (`.env`)

```bash
# Required
OPENROUTER_API_KEY=sk-or-v1-your_key

# Recommended for production
HELIUS_API_KEY=your_helius_key
DATABASE_URL=postgresql://user:pass@localhost:5432/ilyon_ai

# Optional
REDIS_URL=redis://localhost:6379
BOT_TOKEN=your_telegram_bot_token           # Telegram bot interface
ALLOWED_USERS=123456789,987654321           # Telegram user whitelist
```

### Frontend Environment Variables (`web/.env.local`)

```bash
# Backend API URL
NEXT_PUBLIC_API_URL=http://localhost:8080

# Solana Network (mainnet-beta, devnet, testnet)
NEXT_PUBLIC_SOLANA_NETWORK=mainnet-beta

# Optional: Helius RPC for better performance
NEXT_PUBLIC_SOLANA_RPC_URL=https://api.mainnet-beta.solana.com

# Coming Soon plugs (true = show plugs on in-development pages, false = show full features)
NEXT_PUBLIC_COMING_SOON=false
```

### Feature Flags

The `NEXT_PUBLIC_COMING_SOON` environment variable controls visibility of features:

| Value | Behavior |
|-------|----------|
| `false` (default) | All features are fully accessible — Shield, Audits, REKT, Alerts, Entity Explorer. |
| `true` | Shield, Audits, REKT Database, Alerts, and Entity Explorer show "Coming Soon" placeholders. Alert notifications are hidden. |

---

## Development

### Running Tests

```bash
# Backend tests
pytest tests/

# Frontend tests
cd web && npm test
```

### Code Style

```bash
# Backend
black src/
ruff check src/

# Frontend
cd web && npm run lint
```

### Adding New Data Sources

1. Create a client in `src/data/`
2. Add to parallel collection in `src/core/analyzer.py`
3. Update `TokenInfo` model if new fields are needed
4. Update the AI prompt to include new data

---

## Contributing

Contributions are welcome:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## Security

### Reporting Vulnerabilities

If you discover a security vulnerability, please email security@ilyonai.io instead of opening a public issue.

### Best Practices

- Never commit `.env` files
- Use `ALLOWED_USERS` in production for the Telegram bot
- Rotate API keys regularly
- Enable `LOG_REDACT_SENSITIVE=true`

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Disclaimer

Ilyon AI provides analysis and risk assessment for educational purposes. It is not financial advice. Always do your own research before trading. The developers are not responsible for any financial losses.
