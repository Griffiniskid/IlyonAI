# Advanced Logging System Documentation

## Overview

AI Sentinel now includes a comprehensive, production-grade logging system that tracks every AI response, exit code, and error for improved debugging and precise AI analysis.

## Features

✅ **Dual Output** - JSON logs (machine-readable) + colored console logs (human-readable)
✅ **Full AI Tracking** - Every request/response logged with tokens, latency, and cost
✅ **Exit Code Standardization** - Consistent success/failure codes across all operations
✅ **Trace IDs** - Request correlation across async operations
✅ **Sensitive Data Protection** - Automatic API key/token/PII redaction
✅ **Rotating Files** - 10MB max, 5 backups
✅ **Log Analysis Tools** - CLI utilities for parsing and analyzing logs

## Log Outputs

### 1. Console (Human-Readable)
Colored, context-rich logs for real-time monitoring:
```
12:34:56 | INFO | ai.openai | AI response: success
  → Symbol: BONK | Provider: openai (gpt-4o) | Exit: 0
  → Tokens: 1234 (prompt:890, completion:344) | Latency: 2345ms | Cost: $0.0123
  → Result: SAFE | Score: 85/100 | Confidence: 92% | Rug: 15%
```

### 2. JSON File (Machine-Parsable)
Located at `logs/ai_sentinel.json`:
```json
{
  "timestamp": "2025-12-30T12:34:56.789Z",
  "level": "INFO",
  "logger": "ai.openai",
  "message": "AI response: success",
  "trace_id": "BONK_analyze_1735564496789",
  "symbol": "BONK",
  "exit_code": 0,
  "ai_metadata": {
    "provider": "openai",
    "model": "gpt-4o",
    "tokens_prompt": 890,
    "tokens_completion": 344,
    "tokens_total": 1234,
    "latency_ms": 2345,
    "cost_usd": 0.0123
  },
  "response": {
    "ai_score": 85,
    "verdict": "SAFE",
    "confidence": 92,
    "rug_probability": 15
  }
}
```

### 3. Text File (Traditional)
Located at `LOG_FILE` env variable path (if configured):
```
2025-12-30 12:34:56 | INFO | ai.openai_client | analyze:214 | AI response: success
```

## Configuration

### Environment Variables

Add to your `.env` file:

```bash
# Basic logging
LOG_LEVEL=INFO                    # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FILE=logs/ai_sentinel.log    # Optional text log file

# Advanced logging
LOG_MAX_BYTES=10485760           # 10MB (default)
LOG_BACKUP_COUNT=5               # Number of backup files
LOG_AI_FULL_RESPONSES=true       # Log full AI responses (recommended)
LOG_REDACT_SENSITIVE=true        # Redact API keys/tokens (recommended)
```

## Exit Codes

### AI Operations (0-9)
- `0` - Success
- `1` - Timeout (asyncio.TimeoutError)
- `2` - API error (HTTP error, connection error)
- `3` - Parse error (JSON decode failure)
- `4` - Empty response
- `5` - Rate limited

### Data Operations (10-19)
- `10` - Success
- `11` - Timeout
- `12` - HTTP error
- `13` - Parse error
- `14` - Rate limited
- `15` - Not found

### Bot Operations (20-29)
- `20` - Success
- `21` - Token not found
- `22` - Analysis failed
- `23` - Formatting error
- `24` - Rate limited

### Analysis Pipeline (30-39)
- `30` - Success
- `31` - Data collection failed
- `32` - AI analysis failed
- `33` - Scoring failed
- `34` - Cache error

## Log Analysis CLI

Powerful command-line tools for analyzing logs:

### Show Statistics
```bash
python -m src.logging.utils.cli stats
```
Displays comprehensive metrics including:
- AI performance by provider
- Token usage and costs
- Success rates and latencies
- Error summary

### Show Recent Errors
```bash
python -m src.logging.utils.cli errors --limit 100
```
Lists recent errors with:
- Timestamp
- Error type
- Exit code
- Stack trace

### Cost Analysis
```bash
python -m src.logging.utils.cli cost --hours 24
```
Calculates AI costs over time:
- Total cost in USD
- Breakdown by provider/model
- Cost per request
- Token usage

### Tail Logs
```bash
python -m src.logging.utils.cli tail --limit 20 --level ERROR
```
View recent log entries:
- Filter by log level
- Colored output
- Shows extra context

## Logged Information

### AI Requests
- Provider and model
- Prompt (preview in logs, full if enabled)
- Parameters (temperature, max_tokens, etc.)
- Trace ID for correlation

### AI Responses
- Success/failure status
- Full response data
- Token counts (prompt, completion, total)
- Latency in milliseconds
- Cost in USD
- Exit code

### Errors
- Exception type and message
- Stack trace
- Exit code
- Context (symbol, address, etc.)

### Bot Interactions
- User messages (anonymized)
- Button clicks
- Analysis requests
- Completion status

### Data Sources
- API calls and responses
- Retry attempts
- Status codes
- Latency

## Security & Privacy

### Automatic Redaction
The system automatically redacts:
- API keys (openai_api_key, openrouter_api_key, etc.)
- Bearer tokens
- Private keys (64-char hex strings)
- Database URLs with passwords
- Secret keys (sk-*, xai-*)

Example:
```
Before: "api_key=sk-1234567890abcdef"
After:  "api_key=[REDACTED:API_KEY]"
```

### User Anonymization
- User IDs hashed with SHA256
- Usernames hashed (first 12 chars)
- Message content limited to preview (100 chars)

## Cost Tracking

The system automatically calculates AI costs using current pricing:

### OpenAI Models
- **gpt-4o**: $2.50 input / $10.00 output per 1M tokens
- **gpt-4o-mini**: $0.15 input / $0.60 output per 1M tokens

### Gemini Models
- **gemini-2.0-flash-exp**: $0.075 input / $0.30 output per 1M tokens

### Grok Models
- **grok-2-latest**: $2.00 input / $10.00 output per 1M tokens

Costs are logged with every AI response for accurate tracking.

## Trace IDs

Every operation gets a unique trace ID for correlation:

Format: `{symbol}_{operation}_{timestamp_ms}`

Example: `BONK_analyze_1735564496789`

Use trace IDs to:
- Track requests across logs
- Correlate AI calls with user interactions
- Debug complex multi-step operations

## Performance Impact

The logging system is designed for minimal overhead:
- **<5ms** per log operation
- Async-friendly (no blocking)
- Efficient JSON serialization
- Rotating files prevent disk issues

## File Structure

```
src/logging/
├── __init__.py              # Package exports
├── structured.py            # JSON + console formatters
├── filters.py               # Sensitive data redaction
├── handlers.py              # File handlers
├── context.py               # Trace IDs & context
├── adapters/
│   ├── ai_logger.py         # AI operation logging
│   ├── bot_logger.py        # Bot interaction logging
│   ├── data_logger.py       # Data source logging
│   └── performance_logger.py # Performance tracking
└── utils/
    ├── analyzer.py          # Log analysis
    └── cli.py               # CLI tools
```

## Usage Examples

### In Code
```python
from src.logging.adapters import AILogger, BotLogger
from src.logging.context import generate_trace_id

# AI logging
ai_logger = AILogger("ai.custom")
trace_id = generate_trace_id("BONK", "analyze")

ai_logger.log_request(
    provider="openai",
    model="gpt-4o",
    operation="analyze",
    prompt=prompt_text,
    params={"temperature": 0.1},
    context={"trace_id": trace_id, "symbol": "BONK"}
)

# Bot logging
bot_logger = BotLogger("bot.handlers")
bot_logger.log_analysis_request(
    user_id=12345,
    symbol="BONK",
    address="abc123...",
    mode="standard"
)
```

### Analyzing Logs Programmatically
```python
from src.logging.utils import LogAnalyzer

analyzer = LogAnalyzer("logs/ai_sentinel.json")
analyzer.load_logs(limit=1000)

# Get AI metrics
metrics = analyzer.get_ai_metrics()
print(f"Total cost: ${metrics['openai']['total_cost_usd']}")

# Get error summary
errors = analyzer.get_error_summary()
print(f"Total errors: {errors['total_errors']}")

# Print full summary
analyzer.print_summary()
```

## Troubleshooting

### Logs not appearing
1. Check `LOG_LEVEL` environment variable
2. Ensure `logs/` directory is writable
3. Verify `setup_logging()` is called in main.py

### Log files growing too large
1. Adjust `LOG_MAX_BYTES` to smaller value
2. Increase `LOG_BACKUP_COUNT` for more history
3. Set up log rotation in production

### Sensitive data in logs
1. Ensure `LOG_REDACT_SENSITIVE=true`
2. Check filter patterns in `filters.py`
3. Report any leaked data as a bug

## Best Practices

1. **Always use trace IDs** for multi-step operations
2. **Log exit codes** for every operation
3. **Include context** (symbol, user_id, etc.) in extra fields
4. **Use appropriate log levels** (DEBUG for details, INFO for important events, ERROR for failures)
5. **Analyze logs regularly** using CLI tools
6. **Monitor costs** to optimize AI usage
7. **Review errors** to identify systemic issues

## Future Enhancements

Potential additions:
- Real-time log streaming
- Grafana/Prometheus metrics export
- Alerting on error thresholds
- Log aggregation to external services
- Machine learning on error patterns

---

For questions or issues, check the logs first with:
```bash
python -m src.logging.utils.cli stats
python -m src.logging.utils.cli errors
```
