# AI Sentinel

**Solana Token Security Intelligence Platform**

AI Sentinel is an open-source Telegram bot that protects Solana traders from rug pulls and scams using advanced AI analysis, behavioral detection, and wallet forensics.

## Key Features

### Predictive Rug Detection
Unlike tools that detect rugs *after* they happen, AI Sentinel warns you *before* using behavioral pattern analysis:
- Liquidity staging detection (small removals before major rug)
- Volume/price divergence identification
- Sell pressure buildup monitoring
- Time-to-rug estimation

### Serial Scammer Tracking
Cross-token wallet forensics that catches repeat offenders:
- Tracks deployer wallets across multiple token launches
- Identifies patterns: rapid deployment, consistent rug timing, LP removal
- Creates accountability - scammers can't hide behind new wallets

### Honeypot Detection
Behavioral simulation that tests if tokens can actually be sold:
- Jupiter-based swap simulation
- Sell tax calculation
- Route availability verification
- Hidden fee detection

### Multi-AI Analysis
Consensus-based risk assessment using multiple AI providers:
- OpenAI GPT-4o for deep analysis
- Gemini for supplementary insights
- Structured output with confidence scoring

### Additional Features
- Real-time DexScreener integration
- RugCheck LP lock verification
- Top holder concentration analysis
- Website quality scoring
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
git clone https://github.com/yourusername/ai-sentinel.git
cd ai-sentinel

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
DATABASE_URL=postgresql://user:pass@localhost:5432/ai_sentinel
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
ai-sentinel/
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

If you discover a security vulnerability, please email security@aisentinel.io instead of opening a public issue.

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

AI Sentinel provides analysis and risk assessment for educational purposes. It is not financial advice. Always do your own research before trading. The developers are not responsible for any financial losses.
