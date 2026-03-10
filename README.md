# Ilyon AI

**AI-Powered DeFi Intelligence Platform**

> Multi-chain security analysis, smart contract auditing, and DeFi protocol intelligence — powered by AI.

![Multi-Chain](https://img.shields.io/badge/Multi--Chain-Ethereum%20%7C%20Solana%20%7C%20Base%20%7C%20BSC%20%7C%20Arbitrum%20%7C%20Polygon-9945FF?style=for-the-badge)
![Blinks Ready](https://img.shields.io/badge/Solana%20Actions-Blinks%20Ready-9945FF?style=for-the-badge&logo=solana)

Ilyon AI is an open-source DeFi intelligence platform that protects traders across all major blockchains from rug pulls, scams, and smart contract vulnerabilities using advanced AI analysis, behavioral detection, and wallet forensics.

## Key Innovation

### Multi-Chain DeFi Intelligence
Ilyon AI supports **Ethereum, Solana, Base, Arbitrum, BSC, Polygon, Optimism, and Avalanche** with a unified analysis engine that adapts to each chain's unique risk factors.

### AI-Native Architecture
Every feature is powered by AI — not bolted on as an afterthought. From smart contract auditing to predictive rug detection, AI is the core engine.

### Solana Blinks Integration
One of the first security tools to fully support **Solana Actions (Blinks)** — share token analysis directly on X (Twitter).

## Key Features

### Multi-Chain Token Analysis
Comprehensive token security analysis across all major blockchains:
- EVM chains: contract verification, proxy detection, ownership analysis
- Solana: mint/freeze authority, LP lock verification, RugCheck integration
- Universal: holder distribution, liquidity depth, market data

### Smart Contract Scanner
AI-powered contract auditing that goes beyond static pattern matching:
- Source code analysis for verified contracts
- Bytecode decompilation for unverified contracts
- 200+ vulnerability detectors (reentrancy, overflow, access control, backdoors)
- Scam template similarity detection

### Shield (Approval Manager)
Protect your wallets from risky smart contract approvals:
- Scan all token approvals across EVM chains
- Risk-score each approval with AI context
- One-click revoke for dangerous approvals

### DeFi Protocol Analysis
Analyze liquidity pools, yield farms, and lending protocols:
- Pool composition and impermanent loss estimation
- APY verification (detect inflated yield claims)
- Protocol health scoring based on TVL, audits, and incident history

### Predictive Rug Detection
Unlike tools that detect rugs *after* they happen, Ilyon AI warns you *before* using behavioral pattern analysis:
- Liquidity staging detection (small removals before major rug)
- Volume/price divergence identification
- Sell pressure buildup monitoring
- Time-to-rug estimation

### Serial Scammer Tracking
Cross-chain wallet forensics that catches repeat offenders:
- Tracks deployer wallets across multiple token launches and chains
- Identifies patterns: rapid deployment, consistent rug timing, LP removal
- Creates accountability — scammers can't hide behind new wallets or chains

### Honeypot Detection
Behavioral simulation that tests if tokens can actually be sold:
- Jupiter-based swap simulation (Solana)
- EVM swap simulation via DEX router calls
- Sell tax calculation and hidden fee detection

### AI Agent & Chat
Natural language interface to query any DeFi data:
- "Is this token safe to buy?"
- "What yield farming opportunities exist on Arbitrum with audited contracts?"
- "Review my portfolio for risks"

### Intelligence Database
- REKT Database: searchable archive of DeFi hacks, exploits, and scams
- Audit Database: indexed smart contract audits from major firms
- Scammer Registry: cross-chain wallet blacklist

### Additional Features
- Multi-AI analysis (GPT-4o + Grok narrative analysis)
- Real-time DexScreener integration across all chains
- Portfolio tracking with multi-wallet aggregation
- Whale activity monitoring
- Solana Actions/Blinks for shareable reports

---

## Quick Start

### Prerequisites
- Python 3.10+
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- AI API Key (OpenRouter or OpenAI)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/ilyon-ai.git
cd ilyon-ai

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys (see Configuration section)

# Run the bot
python -m src.main
```

### Docker Deployment

```bash
# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Set required password
export POSTGRES_PASSWORD=your_secure_password

# Start services
docker-compose up -d
```

---

## Configuration

### Required API Keys

| Service | Purpose | Get Key |
|---------|---------|---------|
| **Telegram** | Bot interface | [@BotFather](https://t.me/botfather) |
| **OpenRouter** or **OpenAI** | AI analysis | [openrouter.ai](https://openrouter.ai/keys) or [platform.openai.com](https://platform.openai.com/api-keys) |

### Recommended API Keys

| Service | Purpose | Get Key |
|---------|---------|---------|
| **Helius** | Fast Solana RPC | [dev.helius.xyz](https://dev.helius.xyz/) (Free tier available) |

### Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
# Required
BOT_TOKEN=your_telegram_bot_token
OPENROUTER_API_KEY=sk-or-v1-your_key

# Recommended for production
HELIUS_API_KEY=your_helius_key
ALLOWED_USERS=123456789,987654321  # Comma-separated Telegram IDs

# Optional
DATABASE_URL=postgresql://user:pass@localhost:5432/ilyon_ai
REDIS_URL=redis://localhost:6379
```

See [.env.example](.env.example) for all available options.

---

## Usage

### Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and help |
| `/analyze <token>` | Full token analysis |
| `/quick <token>` | Quick risk check |
| `/help` | Show all commands |

### Analyzing a Token

Simply send a Solana token address to the bot:

```
EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v
```

Or use the analyze command:

```
/analyze EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v
```

### Understanding Results

**Risk Levels:**
- **SAFE** (Score 85+): Low risk, appears legitimate
- **LOW** (Score 75-84): Minor concerns, proceed with caution
- **MEDIUM** (Score 60-74): Notable risks identified
- **HIGH** (Score 45-59): Significant red flags
- **CRITICAL** (Score <45): High probability of scam

**Key Metrics:**
- **Security Score**: Contract safety (authorities, LP lock)
- **Deployer Reputation**: Developer wallet history
- **Holder Distribution**: Concentration risk
- **Honeypot Status**: Sell ability verification

---

## Architecture

```
ilyon-ai/
├── src/
│   ├── main.py              # Application entry point
│   ├── config.py            # Configuration management
│   ├── bot/                 # Telegram bot interface
│   │   ├── handlers/        # Command and callback handlers
│   │   └── formatters/      # Response formatting
│   ├── core/                # Core analysis engine
│   │   ├── analyzer.py      # Main analysis orchestrator
│   │   ├── scorer.py        # Risk scoring system
│   │   └── models.py        # Data models
│   ├── data/                # External data providers
│   │   ├── dexscreener.py   # Market data
│   │   ├── rugcheck.py      # LP verification
│   │   ├── solana.py        # On-chain data
│   │   └── honeypot.py      # Honeypot detection
│   ├── analytics/           # Advanced analysis
│   │   ├── wallet_forensics.py  # Deployer tracking
│   │   └── anomaly_detector.py  # Behavioral patterns
│   ├── ai/                  # AI integrations
│   │   ├── router.py        # AI provider routing
│   │   └── openai_client.py # OpenAI/OpenRouter client
│   ├── api/                 # HTTP API (Blinks)
│   │   ├── routes/          # API endpoints
│   │   └── middleware/      # CORS, rate limiting
│   ├── storage/             # Data persistence
│   │   ├── database.py      # PostgreSQL
│   │   └── cache.py         # Redis caching
│   └── monetization/        # Affiliate integration
├── docker-compose.yml       # Docker deployment
├── Dockerfile
├── requirements.txt
└── .env.example
```

### Analysis Pipeline

1. **Data Collection** (parallel):
   - DexScreener: price, liquidity, volume
   - RugCheck: LP lock status
   - Solana RPC: on-chain data, holders
   - Website scraper: quality signals

2. **Advanced Analytics** (parallel):
   - Wallet forensics: deployer history
   - Anomaly detection: behavioral patterns
   - Honeypot simulation: sell verification

3. **AI Analysis**:
   - Structured prompt with all data
   - Risk assessment with reasoning
   - Red/green flag identification

4. **Scoring**:
   - AI score as primary metric
   - Component scores for context
   - Hard caps for known scammers/honeypots

---

## Development

### Running Tests

```bash
pytest tests/
```

### Code Style

```bash
# Format code
black src/

# Lint
ruff check src/
```

### Adding New Data Sources

1. Create client in `src/data/`
2. Add to parallel collection in `src/core/analyzer.py`
3. Update `TokenInfo` model if new fields needed
4. Update AI prompt to include new data

---

## Contributing

Contributions are welcome! Please:

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
- Use `ALLOWED_USERS` in production
- Rotate API keys regularly
- Enable `LOG_REDACT_SENSITIVE=true`

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

## Disclaimer

Ilyon AI provides analysis and risk assessment for educational purposes. It is not financial advice. Always do your own research before trading. The developers are not responsible for any financial losses.
