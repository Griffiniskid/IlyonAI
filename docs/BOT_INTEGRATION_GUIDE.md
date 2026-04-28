# Ilyon AI API — Twitter Bot Integration Guide

**Audience:** the AI agent building the Twitter marketing bot.
**Scope:** everything you need to call `https://ilyonai.com` from server-side code. Read this first, then use `BOT_API_REFERENCE.md` for every endpoint's exact schema.

---

## 1. Base URL & transport

- **Base URL:** `https://ilyonai.com`
- **Protocol:** HTTPS only (HTTP/2 available). Content-Type on POST: `application/json`.
- **Encoding:** UTF-8 JSON in and out.
- **Hosting:** Cloudflare in front of a Caddy reverse proxy. Expect `cf-ray` and `cf-cache-status` response headers.

## 2. Auth model for the bot

**You do not need to authenticate.** The Twitter bot is server-to-server and all endpoints you need (`/analyze`, `/token`, `/defi/pool/analyze`, `/trending`, `/search`, `/whales`, `/contract/scan`, `/shield/...`, `/wallets/...`, `/stats`, `/chains`, `/smart-money/overview`, `/intel/*`) are public.

Endpoints that DO require auth (and that the bot can ignore):
- `POST /api/v1/portfolio/wallets` and other portfolio writes
- `POST /api/v1/alerts/rules` and other alerts writes
- `GET /api/v1/auth/me`

Auth uses Sign-In-With-Solana (SIWS): `POST /api/v1/auth/challenge` → sign message in wallet → `POST /api/v1/auth/verify`. Session cookie is returned. Unless the bot needs to persist user-scoped state, skip this entirely.

## 3. Rate limits

| Caller | Limit |
|---|---|
| Anonymous (IP-keyed) | 30 req/min, 200 req/hour (defaults in `rate_limit.py`; may be higher on prod) |
| Authenticated | 2× the above |
| Scope burst cap (mutations, streams) | separate short-window cap, irrelevant for the bot |

On limit hit you get **HTTP 429** with:
```json
{ "error": "Rate limit exceeded: 30/minute", "code": "RATE_LIMIT_EXCEEDED" }
```
Response headers include `Retry-After` (seconds) and `X-RateLimit-Reset` (epoch s). **Always respect `Retry-After`.**

Practical bot guidance: batch your analyses and space them ≥ 2 s apart, or run a token bucket at 25 req/min to stay well under the threshold.

## 4. Response-shape rules (IMPORTANT)

There are **two response shapes** in this API and you must handle both.

### 4a. Envelope shape (newer endpoints)
```json
{
  "status": "ok" | "error",
  "data": { ... },
  "meta": {},
  "errors": [ { "code": "...", "message": "...", "details": {} } ],
  "trace_id": null,
  "freshness": "live"
}
```
Used by: `/stats`, `/trending*`, `/whales` (collection), `/chains`, `/defi/analyze`, `/defi/pool` list, `/smart-money/overview`, `/intel/*`, `/wallets/*/profile|forensics|balances`, `/shield/*`, `/entities`, `/alerts`, opportunities.

Rule: if top-level keys include `status` and `data`, read from `data`. Errors are inside `errors[0].code`.

### 4b. Bare shape (token analysis + pool analysis)
```json
{ "token": {...}, "scores": {...}, "market": {...}, "security": {...}, ... }
```
Used by: `POST /api/v1/analyze`, `GET /api/v1/token/{addr}`, `POST /api/v1/token/{addr}/refresh`, `GET /api/v1/search`, `POST /api/v1/defi/pool/analyze`, `GET /api/v1/defi/pools`, `GET /api/v1/defi/pools/{id}`, `GET /api/v1/defi/yields`, `GET /api/v1/defi/opportunities*`, `GET /api/v1/defi/protocols*`, `POST /api/v1/contract/scan`, `GET /api/v1/contract/{chain}/{addr}`, `POST/GET whale profile/wallet`.

Rule: parse directly from top level. Errors use `{ "error": "...", "code": "..." (optional), "details": {...} }`.

### 4c. Error shape (both families)
HTTP status ≥ 400. Always check status before parsing. Common codes:
`INVALID_REQUEST`, `INVALID_ADDRESS`, `MISSING_ADDRESS`, `UNKNOWN_CHAIN`, `UNSUPPORTED_CHAIN`, `NOT_FOUND`, `RATE_LIMIT_EXCEEDED`, `ANALYSIS_FAILED`, `INTERNAL_ERROR`, `SERVICE_UNAVAILABLE`.

## 5. Chain handling

The API is multi-chain aware. Wherever you see `chain`, the accepted values are:

- **Canonical:** `solana`, `ethereum`, `base`, `arbitrum`, `bsc`, `polygon`, `optimism`, `avalanche`
- **Aliases (auto-normalized):** `sol` → solana, `eth` → ethereum, `arb` → arbitrum, `bnb` → bsc, `matic` → polygon, `op` → optimism, `avax` → avalanche

**Address auto-detection:** if you omit `chain`, the server detects Solana vs. EVM from address format. You can always be explicit to avoid ambiguity (some tokens exist on multiple chains with the same symbol).

- Solana base58: 32–44 chars, no `0`/`O`/`I`/`l`.
- EVM: `0x` + 40 hex chars.

## 6. Canonical bot workflow

The bot's job is: *given a token address or symbol mentioned on Twitter, produce an analysis to post back.* Here is the exact call sequence.

### 6a. Fast path (token already cached)
```
GET /api/v1/token/{address}?chain={chain}   → 200 in ~100 ms, cached:true
```
If you get **404 `NOT_FOUND`**, fall through to 6b.

### 6b. Cold path (first analysis)
```
POST /api/v1/analyze
Body: { "address": "...", "chain": "...", "mode": "standard" }
→ 200 in 12–25 s
```
Modes:
- `quick` — skips expensive AI calls. Use for rapid scanning.
- `standard` — **default, recommended for tweets.** Runs full token analysis including Grok narrative and AI summary.
- `deep` — maps internally to `"full"`. Slowest, adds deployer forensics + behavioral anomaly detection.

After this completes, subsequent `GET /token/{addr}` within process TTL returns instantly.

### 6c. Resolving a symbol to an address
```
GET /api/v1/search?query=bonk&chain=solana&limit=5
```
Returns a ranked list of pools/tokens. Pull the first `type:"token"` match and use its `address` for step 6a/6b.

### 6d. Pool / LP analysis (optional)
If the tweet is about a liquidity pool or yield farm:
```
POST /api/v1/defi/pool/analyze
Body: { "pool_id": "33c732f6-..." , "include_ai": true }
```
`pool_id` comes from `GET /api/v1/defi/pools` or `/api/v1/defi/yields`. If you only have a DEX pair address (e.g. a Dexscreener URL), use:
```
Body: { "pair_address": "0x...", "source": "dexpair", "include_ai": true }
```
Timeout: 120 s server-side; set your HTTP client to ≥ 130 s.

### 6e. Trending for discovery tweets
```
GET /api/v1/trending?chain=solana&limit=10&category=trending
```
Categories: `trending` (default), `gainers`, `losers`, `new`. Or hit the shortcut routes `/trending/gainers`, `/trending/losers`, `/trending/new`.

### 6f. Whale / smart-money tweets
```
GET /api/v1/whales/token/{address}?min_amount_usd=50000&limit=20
GET /api/v1/smart-money/overview
```
Use these to post "top buyers / sellers in the last 24 h" style threads.

## 7. Timeouts & concurrency

| Operation | Typical cold | Recommended client timeout |
|---|---|---|
| `GET /health`, `/chains`, `/token/{addr}` (cached) | < 500 ms | 10 s |
| `GET /search`, `/trending`, `/whales` | 1–4 s | 20 s |
| `POST /analyze` | 12–25 s | **60 s** |
| `POST /token/{addr}/refresh` | same as analyze | 60 s |
| `POST /defi/pool/analyze` (with AI) | 15–30 s | **130 s** |
| `POST /contract/scan` | 5–20 s | 60 s |

Concurrency: don't fan out > 4 parallel `/analyze` calls — the upstream AI (Grok + LLM) and on-chain providers (Helius, RugCheck, DefiLlama) throttle. Serial or low-concurrency is safer and hits internal deduplication (same pool analyze requests are coalesced in-flight).

## 8. Caching the bot should do

- **Response cache keyed by `{address, chain}`:** store `/analyze` output locally for 60 s–5 min; reply instantly to duplicate mentions without re-hitting the API.
- **Hot-symbol cache:** for tokens the bot posts about frequently, run a background refresh every 5–10 min via `POST /token/{addr}/refresh?mode=standard`.

Server-side caching is already in place (~5 min for trending, 60 s for pool analysis replay, process-TTL for analyze cache), but duplicating on your side cuts latency and rate-limit pressure.

## 9. What the API gives the bot — enough or not?

### Already sufficient for the bot
- Full token safety + scoring (`POST /analyze`): 8 sub-scores, grade A–F, liquidity lock %, mint/freeze authority, honeypot verdict, top-10 holders, Grok narrative, AI summary, verdict, red/green flags, rug probability, whale-risk prose. **This is enough to autogenerate any "token audit" tweet.**
- Market data (price, volume 1h/24h, liquidity, FDV, market cap, buys/sells/txns 24 h, age, DEX, pair address) — bundled in the analyze response.
- Social signals (Twitter/TG/website URLs detected + website quality score).
- Trending, gainers, losers, new pairs — for daily/hourly "what's hot" posts.
- Whale transactions (per-token + per-wallet + leaderboard).
- Pool / LP safety analysis with 8 dimensions, 90 d history, AI-generated risk summary, safer-alternative suggestion.
- Contract scanner for EVM audits (`POST /contract/scan`).
- Approval scanner ("wallet shield") for revoke-prep tweets.
- Chain metadata.
- Intel archive: Rekt (historical hacks) + audit registry.
- Per-wallet profile, forensics, balances.

### Gaps the bot may hit (recommend building next)

1. **No webhook / push stream for alerts.** There is a WebSocket `/api/v1/stream/ws` and SSE `/api/v1/stream/sse`, but there's no "notify me when this token's score drops" REST webhook. If the bot needs to react to events (exploit alerts, new scam detections), it must poll — or we wire webhooks into the alert engine.
2. **No bulk analyze endpoint.** Analyzing 50 tokens for a "top risky tokens today" tweet requires 50 sequential POSTs (with server dedup). If the bot does this regularly, we should add `POST /api/v1/analyze/batch` that accepts `[{address, chain}, ...]`.
3. **No tweet-ready formatted output.** The API returns structured data; the bot must template tweets itself. Not a blocker, but a `format=tweet` query param that returns a 280-char string could simplify.
4. **Search does not currently include contracts/wallets.** The universal `/search` endpoint currently returns token/pool matches. If the bot should let users tweet "analyze @wallet" the bot must route manually to `/wallets/{address}/profile`.
5. **No public rate-limit headers on 2xx.** Only 429 includes `X-RateLimit-Reset`. The bot can't know how close it is to the limit until it hits it. Low priority — implementing a client-side token bucket covers this.
6. **Image assets are not auto-generated.** The `logo_url` field is a Dexscreener CDN URL (may be missing/broken for obscure tokens). If the bot posts images, it should fallback to chain-agnostic placeholder rendering.
7. **CORS is browser-only and scoped to ilyonai.com.** Irrelevant for server-side bot, mentioned so you don't try to call from a browser extension.

None of these are blockers — the bot can ship today against what exists and these gaps become next-iteration work.

## 10. Minimum-viable bot integration checklist

- [ ] Server-side HTTP client with 60 s timeout for analyze, 130 s for pool/analyze, 15 s for everything else.
- [ ] Retry policy: retry ONLY on 5xx and network errors, **never on 4xx**. Max 2 retries with exponential backoff (1 s, 3 s).
- [ ] Respect `Retry-After` on 429.
- [ ] Shape-detector: check for top-level `status` key; branch to envelope vs. bare parsing.
- [ ] Address validator before sending: regex `^0x[0-9a-fA-F]{40}$|^[1-9A-HJ-NP-Za-km-z]{32,44}$`.
- [ ] Local cache keyed by `{chain}:{address}` with 2–5 min TTL.
- [ ] Graceful degradation: if `ai.available:false`, still post the numeric scores.
- [ ] Log `trace_id` (envelope responses) so debugging with our backend is possible.

## 11. Smoke-test commands (copy-paste to verify live)

```bash
# 1. Health
curl -s https://ilyonai.com/health | jq

# 2. API catalog
curl -s https://ilyonai.com/api/v1 | jq .endpoints

# 3. Full token analyze (BONK on Solana)
curl -s -X POST https://ilyonai.com/api/v1/analyze \
  -H 'Content-Type: application/json' \
  -d '{"address":"DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263","chain":"solana","mode":"standard"}' \
  | jq '{symbol: .token.symbol, score: .scores.overall, verdict: .ai.verdict, summary: .ai.summary}'

# 4. Trending (Solana top 5)
curl -s 'https://ilyonai.com/api/v1/trending?chain=solana&limit=5' \
  | jq '.data.tokens[] | {sym: .symbol, price: .price_usd, pct_24h: .price_change_24h}'

# 5. Pool analyze
POOL=$(curl -s 'https://ilyonai.com/api/v1/defi/pools?limit=1' | jq -r '.pools[0].pool_id')
curl -s -X POST https://ilyonai.com/api/v1/defi/pool/analyze \
  -H 'Content-Type: application/json' \
  -d "{\"pool_id\":\"$POOL\",\"include_ai\":true}" \
  | jq '{title, overall: .dimensions[0].score, ai: .ai_analysis.summary[0:200]}'

# 6. Contract scan (EVM only)
curl -s -X POST https://ilyonai.com/api/v1/contract/scan \
  -H 'Content-Type: application/json' \
  -d '{"address":"0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48","chain":"ethereum"}'
```

If any of these returns non-200 or an unexpected shape, the bot has a real problem to report back.

---

Read `BOT_API_REFERENCE.md` for every endpoint's exact request/response schema.
