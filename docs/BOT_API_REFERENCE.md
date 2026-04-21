# Ilyon AI API — Complete Endpoint Reference

Companion to `BOT_INTEGRATION_GUIDE.md`. Base URL: `https://ilyonai.com`.

Conventions used in this doc:
- `{path}` = URL path parameter
- `?foo=bar` = query parameter
- **Envelope** = response is wrapped in `{status, data, meta, errors, trace_id, freshness}` — read from `data`
- **Bare** = response is the payload directly
- Required fields are marked with `*`.

---

## Table of contents

1. [Meta & Health](#1-meta--health)
2. [Token Analysis](#2-token-analysis)
3. [Search](#3-search)
4. [Trending](#4-trending)
5. [Chains](#5-chains)
6. [Stats / Dashboard](#6-stats--dashboard)
7. [Whales](#7-whales)
8. [Whale Leaderboard](#8-whale-leaderboard)
9. [Smart Money](#9-smart-money)
10. [Wallet Intelligence](#10-wallet-intelligence)
11. [Portfolio](#11-portfolio)
12. [Shield (Token Approvals)](#12-shield-token-approvals)
13. [Contract Scanner](#13-contract-scanner)
14. [DeFi — Pools, Yields, Lending, Protocols](#14-defi)
15. [DeFi v2 — Intelligence](#15-defi-v2-intelligence)
16. [Opportunities](#16-opportunities)
17. [Intel — Rekt & Audits](#17-intel--rekt--audits)
18. [Entities](#18-entities)
19. [Alerts](#19-alerts)
20. [Streams (WebSocket / SSE)](#20-streams)
21. [Auth](#21-auth)
22. [Blinks & Solana Actions](#22-blinks--solana-actions)
23. [Public Status](#23-public-status)

---

## 1. Meta & Health

### `GET /health` — liveness probe
- **Auth:** none. **Response:** bare.
- **200**:
```json
{"status":"healthy","service":"Ilyon AI Web API","version":"2.0.0","blinks_enabled":true,"web_api_enabled":true}
```
- Rate-limit exempt. Safe to poll.

### `GET /api/v1` — endpoint catalog
- Bare. Returns a dict of endpoint → path + supported chain list. Good for bot self-discovery but NOT authoritative (this reference is).

### `GET /api/v1/docs` — machine-readable workflows
- Bare. Same info as `/api/v1`, grouped by workflow (token_analysis, discovery, smart_money, security, defi, alerts).

---

## 2. Token Analysis

### `POST /api/v1/analyze` — **primary endpoint**
- **Auth:** none. **Response:** bare. **Cold latency:** 12–25 s.
- **Body:**
```json
{
  "address": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",  // *
  "chain": "solana",                                           // optional, auto-detected
  "mode": "quick" | "standard" | "deep"                        // default "standard"
}
```
- Address validator: Solana base58 (32–44 chars) OR EVM `0x` + 40 hex.
- **200 bare response (16 top-level keys):**

| Key | Type | Description |
|---|---|---|
| `token` | object | `{address, name, symbol, decimals, logo_url, chain, chain_id, explorer_url}` |
| `scores` | object | `{overall (0-100), grade (A-F), safety, liquidity, distribution, social, activity, honeypot, deployer, anomaly}` — all 0-100 |
| `market` | object | `{price_usd, market_cap, fdv, liquidity_usd, volume_24h, volume_1h, price_change_24h, price_change_6h, price_change_1h, price_change_5m, buys_24h, sells_24h, txns_24h, age_hours, dex_name, pair_address}` |
| `security` | object | `{mint_authority_enabled, freeze_authority_enabled, liquidity_locked, lp_lock_percent, liquidity_lock_status ("locked"/"unlocked"/"unknown"), liquidity_lock_source, liquidity_lock_note, honeypot_status, honeypot_is_honeypot, honeypot_sell_tax_percent, honeypot_explanation, honeypot_warnings[], can_mint, can_blacklist, can_pause, is_upgradeable, is_renounced, is_proxy_contract, is_verified, buy_tax, sell_tax, transfer_pausable, is_open_source}` — fields null when not applicable to the chain |
| `holders` | object | `{top_holder_pct, holder_concentration (top-10 %), suspicious_wallets, dev_wallet_risk, holder_flags[], top_holders[10]}` |
| `ai` | object | `{available, verdict ("SAFE"/"CAUTION"/"DANGER"), score, confidence, rug_probability (0-100), summary, recommendation, red_flags[], green_flags[], code_audit, whale_risk, sentiment, trading, narrative (HTML-ready), grok: {...}}` |
| `ai.grok` | object | `{narrative_score (0-100), narrative_category, narrative_summary, sentiment, community_vibe, organic_score, trending_status, influencer_tier, influencer_activity, fud_warnings[], key_themes[]}` |
| `socials` | object | `{has_twitter, has_website, has_telegram, twitter_url, website_url, telegram_url, socials_count}` |
| `website` | object | `{quality (0-100), is_legitimate, has_privacy_policy, has_terms, has_copyright, has_contact, has_tokenomics, has_roadmap, has_team, has_whitepaper, has_audit, audit_provider, red_flags[], ai_quality ("legit"/"suspicious"/"placeholder"), ai_concerns[]}` |
| `deployer` | object | `{available, address, reputation_score, risk_level, tokens_deployed, rugged_tokens, rug_percentage, is_known_scammer, patterns_detected[], evidence_summary}` |
| `anomaly` | object | `{available, score, rug_probability, time_to_rug, severity ("NORMAL"/"ELEVATED"/"CRITICAL"), anomalies_detected[], recommendation, confidence}` |
| `recommendation` | string | Short human verdict e.g. `"🟡 CAUTION — есть риски"` |
| `analyzed_at` | ISO8601 string | UTC timestamp of analysis |
| `analysis_mode` | string | `"quick"`/`"standard"`/`"full"` |
| `cached` | bool | `false` if freshly computed |
| `chain` | string | Chain that was used |

- **400 `INVALID_REQUEST` / `INVALID_ADDRESS`**, **500 `ANALYSIS_FAILED`**, **500 `INTERNAL_ERROR`**.

### `GET /api/v1/token/{address}?chain={chain}` — cached read
- **Auth:** none. **Response:** bare. **Latency:** ~100 ms.
- Returns the exact same shape as `POST /analyze` with `cached:true`.
- **404 `NOT_FOUND`** when never analyzed (body: `{"error":"Token not found in cache. Use POST /api/v1/analyze to analyze.","code":"NOT_FOUND"}`). Fall back to `POST /analyze`.

### `POST /api/v1/token/{address}/refresh?mode=standard&chain=...` — force refresh
- Clears the cache entry and re-runs analysis. Same response as `/analyze`. Use sparingly.

---

## 3. Search

### `GET /api/v1/search?query={q}&chain={chain}&limit={n}`
- **Auth:** none. **Response:** envelope. **Latency:** 1–3 s.
- Universal search across tokens, pools, protocols. Auto-detects addresses vs. text queries.
- `limit`: default 10, max 50.
- **200 envelope.data:**
```json
{
  "query": "bonk",
  "input_type": "search_query" | "address",
  "results": [
    {
      "type": "token" | "pool" | "protocol",
      "product_type": "crypto_stable_lp" | "token" | ...,
      "title": "...",
      "subtitle": "...",
      "address": "...",              // token address or pool_id
      "chain": "solana",
      "score": 129.66,                // relevance score
      "url": "/pool/<id>",            // ilyonai.com relative path
      "logo": "..."                   // may be null
    }
  ]
}
```

---

## 4. Trending

### `GET /api/v1/trending`
- **Auth:** none. **Response:** envelope. **Server cache:** 30 s (10 s for `category=new`).
- **Query:**
  - `category` — `trending` (default) / `gainers` / `losers` / `new`
  - `chain` — optional chain filter (with alias support)
  - `limit` — default 20, max 50
  - `force_refresh` — `1`/`true` to bypass cache
- **200 envelope.data:**
```json
{
  "tokens": [
    {
      "address": "...", "chain": "solana",
      "name": "...", "symbol": "...",
      "logo_url": "...",
      "price_usd": 0.123,
      "price_change_24h": 17643.0, "price_change_1h": -8.18,
      "volume_24h": 15013892.11,
      "liquidity_usd": 248616.82,
      "market_cap": 6427869.0,
      "age_hours": 7.87,
      "dex_name": "Pumpswap",
      "pair_address": "...",
      "txns_1h": 1234
    }
  ],
  "updated_at": "2026-04-18T22:00:00Z",
  "category": "trending",
  "filter_chain": null
}
```
- **400 `INVALID_CHAIN`** if chain filter invalid; `details.supported` lists valid values.

### `GET /api/v1/trending/new`, `/trending/gainers`, `/trending/losers`
Same response shape. Shortcuts that pre-set the `category` query param.

---

## 5. Chains

### `GET /api/v1/chains`
- Envelope. Returns `{chains[], total, count}`.
- Each chain: `{chain, chain_id, display_name, native_currency, explorer_url, is_evm, block_time_seconds, logo, primary_dex}`.

### `GET /api/v1/chains/{chain}`
- Envelope. Detailed config for one chain.
- **404 `UNKNOWN_CHAIN`** if not supported.

---

## 6. Stats / Dashboard

### `GET /api/v1/stats`
- Envelope. **Server cache:** 60 s.
- **200 envelope.data** (subset):

| Field | Meaning |
|---|---|
| `total_volume_24h` | Total Solana DEX volume (DefiLlama) |
| `volume_change_24h` | % change vs 48-24h ago |
| `solana_tvl` | Solana chain TVL |
| `sol_price` + `sol_price_change_24h` | SOL/USD |
| `active_tokens`, `active_tokens_change` | Tokens with recent activity |
| `safe_tokens_percent` | % of analyzed tokens with grade A/B |
| `scams_detected`, `high_risk_tokens` | Counts |
| `avg_liquidity`, `total_liquidity` | USD |
| `volume_chart` | Array of `{time, volume}` — last 14 days |
| `risk_distribution` | Array of `{category ("SAFE"/"WARNING"/"DANGER"), count, percentage}` |
| `market_distribution` | Array of `{category ("Memecoins"/"DeFi"/"Gaming/NFT"/"Other"), volume_usd, percentage}` |
| `top_tokens_by_volume` | Array of `{symbol, volume_24h, price_change_24h, logo_url}` |
| `tokens_analyzed_today`, `total_tokens_analyzed` | Internal counters |
| `updated_at` | ISO |

### `GET /api/v1/stats/health`
Envelope. `{data_sources: [{name, status, latency_ms, last_error}], status}`. Useful if the bot wants to pre-check before posting.

---

## 7. Whales

### `GET /api/v1/whales`
- Envelope. Recent whale trades from our poller/stream.
- **Query:** `min_amount_usd` (default 1000, >=0), `limit` (1–200, default 50), `token` (filter by token address), `type` (`buy`/`sell`).
- **200 envelope.data:**
```json
{
  "transactions": [
    {
      "signature": "...",
      "wallet_address": "...", "wallet_label": "Jump Trading" | null,
      "token_address": "...", "token_symbol": "SOL", "token_name": "Solana",
      "type": "buy" | "sell",
      "amount_tokens": 12345.67, "amount_usd": 1234567.89,
      "price_usd": 100.0,
      "timestamp": "2026-04-18T22:00:00Z",
      "dex_name": "Jupiter"
    }
  ],
  "updated_at": "...",
  "filter_token": null,
  "min_amount_usd": 10000
}
```

### `GET /api/v1/whales/token/{address}`
- **Bare** (legacy shape — not envelope). Whale activity for a specific token using real on-chain data.
- **Query:** `min_amount_usd` (default 1000), `limit` (default 50, max 200), `force_refresh`.
- Adds `behavior` object with whale-concentration signal, anomaly flags, entity heuristics.
- **Server cache:** 60 s per key.

### `GET /api/v1/whales/wallet/{address}`
- Bare. Profile for a single whale wallet from DB.
- **200:**
```json
{
  "address": "...", "label": "Alameda" | null,
  "total_volume_usd": 123456.78,
  "transaction_count": 42,
  "tokens_traded": 7,
  "win_rate": null, "avg_holding_time": null,
  "recent_transactions": [ /* last 20 trades, same shape as whales */ ]
}
```

---

## 8. Whale Leaderboard

### `GET /api/v1/whales/leaderboard`
- Envelope. Ranked top whales by PnL / volume.
- **Query:** `timeframe` (`24h`/`7d`/`30d`), `chain`, `limit`.

### `GET /api/v1/whales/top-wallets`
- Envelope. Lighter top-wallets list used by the website's sidebar.

---

## 9. Smart Money

### `GET /api/v1/smart-money/overview`
- Envelope. Aggregates whale DB into `{inflow_usd, outflow_usd, top_buyers[], top_sellers[], updated_at}` over last 24 h.
- **502 `SMART_MONEY_FETCH_FAILED`** if DB is down.

---

## 10. Wallet Intelligence

All envelope. `{address}` is the URL param (Solana base58 or EVM 0x).

### `GET /api/v1/wallets/{address}/profile`
- Aggregated cross-chain profile: native balances, active chains, multi-chain flag, known label (Alameda/Jump/etc.).

### `GET /api/v1/wallets/{address}/forensics`
- Deep forensic scan: counterparties, tainted-fund paths, mixer interactions, risk score.

### `GET /api/v1/wallets/{address}/balances`
- Per-chain token balances (uses RPC clients + Helius).

---

## 11. Portfolio

**Requires session auth** (SIWS cookie). The bot shouldn't need these.

- `GET /api/v1/portfolio` — aggregated portfolio for the current session wallet
- `GET /api/v1/portfolio/wallets` — list tracked wallets
- `POST /api/v1/portfolio/wallets` — body `{address, chain?, label?}`
- `DELETE /api/v1/portfolio/wallets/{address}`
- `POST /api/v1/portfolio/wallets/{address}/sync` — force resync
- `GET /api/v1/portfolio/chains` — chain parity matrix
- `GET /api/v1/portfolio/{wallet}` — public read of a specific tracked wallet

---

## 12. Shield (Token Approvals)

Scans ERC-20 approvals a wallet has granted across EVM chains. Solana not supported.

### `GET /api/v1/shield/status`
Envelope. Current scanner health / supported chains.

### `GET /api/v1/shield/{wallet}`
- Envelope. Wallet must be `0x` + 40 hex.
- **Query:** `chain` (optional single chain), `min_risk` (0-100 filter).
- Returns `{approvals: [{token_address, token_symbol, spender_address, spender_name, amount, is_unlimited, risk_score, risk_level, chain, last_tx}], summary: {total, high_risk, unlimited_approvals}}`.

### `GET /api/v1/shield/{wallet}/{chain}`
Same as above, single-chain.

### `POST /api/v1/shield/revoke`
- **Body:** `{token_address*, spender_address*, chain*}`.
- Returns ERC-20 `approve(spender, 0)` calldata + target + chain_id for the frontend to sign. Not directly useful to a tweeting bot unless it's also prompting users to revoke.

---

## 13. Contract Scanner

### `POST /api/v1/contract/scan` — EVM only
- **Auth:** none. **Bare.** **Latency:** 5–20 s.
- **Body:** `{address*: "0x...", chain*: "ethereum"|...}`.
- **200:**
```json
{
  "address": "...", "chain": "ethereum",
  "contract_name": "...",
  "is_verified": true, "is_proxy": false, "is_upgradeable": false,
  "compiler_version": "...",
  "risk_level": "SAFE"|"LOW"|"MEDIUM"|"HIGH"|"CRITICAL",
  "risk_score": 0-100,
  "vulnerabilities": [
    {"severity": "HIGH", "category": "...", "title": "...", "description": "...", "line_number": null}
  ],
  "critical_count": 0, "high_count": 0, "medium_count": 0, "low_count": 0,
  "ai_summary": "...",
  "ai_verdict": "SAFE"|"LOW"|"MEDIUM"|"HIGH"|"CRITICAL",
  "scanned_at": "..."
}
```
- **400 `UNSUPPORTED_CHAIN`** for Solana; use `/analyze` instead.

### `GET /api/v1/contract/{chain}/{address}`
Returns cached scan result or 404.

---

## 14. DeFi

All bare unless noted.

### `GET /api/v1/defi/pools`
- Query: `chain`, `protocol` (slug like `uniswap-v3`), `min_tvl` (default 100 000), `min_apy`, `max_apy`, `limit` (default 50, max 200).
- Returns `{pools[], count, filters, summary: {high_risk_pools, total_tvl}, data_source: "DefiLlama"}`.
- Each pool exposes `pool_id` (UUID), `pool` (alias), `chain`, `project` (slug), `category`, `symbol`, `tvl_usd`, `apy`, `apy_base`, `apy_reward`, `apy_mean_30d`, `apy_borrow`, `apy_pct_1d`, `apy_pct_7d`, `risk_level`, `risk_score`, `il_risk`, `stablecoin`, `exposure`, `underlying_tokens[]`, `url`.

### `GET /api/v1/defi/pools/{pool_id}`
- Single pool + 30-day history. Returns `{...pool_fields, history: [{timestamp, tvlUsd, apy, apyBase, apyReward, il7d}], risk_breakdown: {...}}`.
- **404** if not found.

### `GET /api/v1/defi/yields`
- Filter yield farms. Query: `chain`, `exposure` (`stable-stable`/`crypto-stable`/`crypto-crypto`), `min_apy` (default 1), `max_apy`, `min_tvl` (default 50 000), `min_sustainability` (0–1, fraction of APY that's fee-based), `limit`.
- Shape like `/pools` but with emissions/sustainability analysis.

### `GET /api/v1/defi/analyze`
- Envelope. Combined analyzer workflow. Query: `chain`, `query`/`protocol`/`asset`, `min_tvl`, `min_apy`, `limit` (max 25), `include_ai` (`true`/`false`), `ranking_profile` (`balanced` default).
- Returns a full market analysis with ranked opportunities, AI commentary, comparison.

### `POST /api/v1/defi/pool/analyze` — deep analyze one pool
- **Bare.** **Latency:** 15–30 s. Server dedupes identical requests in-flight; 60 s result cache.
- **Body — ONE of `pool_id` or `pair_address` required:**
```json
{
  "pool_id": "33c732f6-a78d-41da-af5b-ccd9fa5e52d5",   // DefiLlama UUID
  "pair_address": "0x...",                             // OR DEX pair address
  "source": "defillama" | "dexpair",                   // defaults by content
  "chain": "ethereum",                                 // only needed with pair_address sometimes
  "include_ai": true,                                  // false = skip LLM, 3–5× faster
  "ranking_profile": "balanced" | "conservative" | "aggressive",
  "kind": "pool" | "yield"                             // auto-inferred
}
```
- **200 bare — 29 top-level keys:**

| Key | Description |
|---|---|
| `id` | Canonical opportunity id (e.g. `pool--<uuid>`) |
| `kind` | `pool` or `yield` |
| `product_type` | e.g. `crypto_crypto_lp`, `crypto_stable_lp`, `stable_stable_lp`, `lending_supply` |
| `score_family` | Ranking family used |
| `title`, `subtitle` | Human labels |
| `protocol`, `protocol_name`, `protocol_slug`, `project` | Protocol info |
| `symbol`, `chain` | Pair symbol and chain |
| `apy`, `tvl_usd` | Market figures |
| `tags` | Array of descriptors |
| `summary` | Short prose |
| `dimensions` | Array of 8 scored dimensions — see below |
| `confidence` | `{score (0-100), label ("HIGH"/"MEDIUM"/"LOW"), coverage_ratio, source_count, freshness_hours, partial_analysis, missing_critical_fields[], notes[]}` |
| `score_caps` | Hard ceilings (e.g. max 80 if no audit) |
| `evidence` | Array of `{key, title, summary, type ("metric"/"inheritance"/"dependency"/"history"/...), severity, source ("DefiLlama"/"token-engine"/"internal"), url}` |
| `scenarios` | Array of stress scenarios `{key, title, impact, severity, trigger}` |
| `dependencies` | Protocol + underlying token chain |
| `assets` | Each underlying asset with 20+ fields: `{symbol, role, chain, quality_score, risk_level, confidence_score, source, address, thesis, token_analysis (inner full token analysis), market_cap_usd, liquidity_usd, volume_24h, age_hours, volatility_24h, depeg_risk, wrapper_risk, is_stable, is_major}` |
| `deployment` | Chain deployment info |
| `ranking_profile` | Echo of request |
| `raw` | Underlying DefiLlama record |
| `history` | `{points: [{timestamp, tvlUsd, apy, apyBase, apyReward, il7d, apyBase7d}]}` — up to 90 days |
| `related_opportunities` | Array of comparable pools |
| `safer_alternative` | Single lower-risk alternative pool |
| `protocol_profile` | Full protocol dossier: audits, incidents, chain_breakdown, governance, docs_profile, methodology, ai_analysis |
| `ai_analysis` | **Present when `include_ai:true`:** `{available, headline, summary, best_for, why_it_exists, main_risks[], monitor_triggers[], safer_alternative}` |

**Dimensions** (always 8 items):

| key | weight |
|---|---|
| `overall_score` | 1.0 |
| `protocol_safety` | 0.20 |
| `structure_safety` | 0.18 |
| `yield_durability` | 0.18 |
| `exit_liquidity` | 0.14 |
| `behavior` | 0.08 |
| `confidence` | 0.04 |
| `apr_efficiency` | 0.40 (informational) |

- **400 on missing identifier / non-pool taxonomy**, **404 `Pool not found`**, **504 `Pool analysis timed out`** (120 s internal).

### `GET /api/v1/defi/opportunities`
Envelope. Ranked opportunities across pools + yields + lending in one list. Query: `chain`, `min_tvl`, `min_apy`, `limit`, `include_ai`, `ranking_profile`.

### `GET /api/v1/defi/opportunities/{opportunity_id}`
Envelope. Fetch a single opportunity by its canonical id (same shape as `pool/analyze` output).

### `POST /api/v1/defi/discover`
Envelope. Creates a long-running discovery analysis (queued). Returns `{analysis_id, status}`. Poll via `/opportunities/analyses/{id}`.

### `GET /api/v1/defi/lending`, `GET /api/v1/defi/lending/{protocol}`, `GET /api/v1/defi/lending/rates/{asset}`
Bare. Lending market overviews. `rates/{asset}` compares supply+borrow APY across protocols for a single asset (e.g. `USDC`).

### `GET /api/v1/defi/health?collateral_usd=&debt_usd=&liquidation_threshold=&price_drop_pct=`
Bare. Simple collateral-health calculator.

### `GET /api/v1/defi/protocols`
Bare. `{protocols: [{slug, name, tvl_usd, chains[], category, audit_count, incident_count, risk_score}], count, filter_chain, data_source: "DefiLlama"}`.

### `GET /api/v1/defi/protocol/{slug}`
Bare. Full protocol profile (same as the `protocol_profile` block in pool/analyze).

---

## 15. DeFi v2 Intelligence

Newer surface used by the web app's unified pool/compare pages. Largely a superset of v1.

- `GET /api/v2/defi/discover?chain=&min_tvl=&min_apy=&limit=&ranking_profile=`
- `GET /api/v2/defi/protocols/{slug}` — protocol v2 detail
- `GET /api/v2/defi/opportunities/{opportunity_id}` — opportunity v2 detail
- `GET /api/v2/defi/compare?asset=USDC&chain=base&protocols=aave-v3,compound-v3&mode=supply&ranking_profile=balanced` — entity-first compare
- `POST /api/v2/defi/simulate/lp` body `{deposit_usd*, apy*, tvl_usd*, price_move_pct?, emissions_decay_pct?, stable_depeg_pct?}` — returns stressed PnL
- `POST /api/v2/defi/simulate/lending` body `{collateral_usd*, debt_usd*, liquidation_threshold?, collateral_drop_pct?, stable_depeg_pct?, borrow_rate_spike_pct?, utilization_pct?, utilization_shock_pct?}` — returns liquidation scenarios
- `POST /api/v2/defi/positions/analyze` body `{kind: "lp"|"lending", ...fields above}` — combined analyzer

All envelope.

---

## 16. Opportunities

Bare.

- `POST /opportunities/analyses` — body `{chain?, query?, min_tvl=100_000, min_apy=3.0, limit=12, include_ai=true, ranking_profile?}`. Starts or coalesces an analysis, returns `{analysis_id, status, cached}`.
- `GET /opportunities/analyses/{analysis_id}` — poll status or get result
- `GET /opportunities/{opportunity_id}` — single opportunity detail
- `POST /opportunities/compare` — body `{items: [{opportunity_id?, analysis_id?}]}` — side-by-side comparison

---

## 17. Intel — Rekt & Audits

All envelope.

- `GET /api/v1/intel/rekt?chain=&category=&min_loss_usd=&limit=` — historical hacks/exploits from the Rekt archive
- `GET /api/v1/intel/rekt/{id}` — single incident detail with AI post-mortem
- `GET /api/v1/intel/audits?protocol=&auditor=&chain=&limit=` — audit registry
- `GET /api/v1/intel/audits/{id}` — single audit report detail
- `GET /api/v1/intel/stats` — aggregate intel stats (total hacked USD, category breakdown)

Useful for tweets like "Today 3 years ago [protocol] lost $X" or "Have you read [auditor]'s report on X?"

---

## 18. Entities

All envelope.

- `GET /api/v1/entities?chain=&category=&limit=` — list known entities (CEXes, market makers, DAOs, multisigs)
- `GET /api/v1/entities/{id}` — single entity profile
- `GET /api/v1/entities/stats` — counts
- `POST /api/v1/entities/resolve` body `{address, chain?}` — given a raw address, returns matching entity or best guess
- `POST /api/v1/entities/merge` body `{source_id, target_id}` — admin merge (auth required)
- `POST /api/v1/entities/{id}/wallets` body `{address, chain?}` — attach a wallet to an entity (auth required)

---

## 19. Alerts

All envelope. **Write endpoints require session auth.**

- `POST /api/v1/alerts/rules` body `{token_address*, alert_type* (enum), threshold* (>0), chain?}` — enum values: `price_above`, `price_below`, `score_below`, `whale_activity`, `contract_risk`, `portfolio_score`, `exploit_alert`
- `GET /api/v1/alerts/rules` — list the caller's rules
- `GET /api/v1/alerts/rules/{rule_id}`
- `PUT /api/v1/alerts/rules/{rule_id}` body `{enabled?, threshold?}`
- `DELETE /api/v1/alerts/rules/{rule_id}`
- `GET /api/v1/alerts` — list triggered alerts (notifications)
- `PATCH /api/v1/alerts/{alert_id}` body `{acknowledged?, dismissed?}`

---

## 20. Streams

### `GET /api/v1/stream/ws` — WebSocket
Client upgrades connection. Subscribe message: `{"type":"subscribe","channels":["whales","alerts","trending"]}`. Messages are JSON with `{type, channel, data, timestamp}`. Useful if the bot wants real-time tweet triggers instead of polling.

### `GET /api/v1/stream/sse` — Server-Sent Events
`text/event-stream`. Same channels. Re-subscribe via `?channels=whales,alerts` query.

---

## 21. Auth

Sign-In-With-Solana. Bare responses.

- `POST /api/v1/auth/challenge` body `{wallet_address*}` → `{challenge, message_to_sign, expires_at}`
- `POST /api/v1/auth/verify` body `{wallet_address*, signature* (base64), challenge*}` → sets session cookie, returns `{user, wallet_address, session_expires_at}`
- `POST /api/v1/auth/logout` — clears cookie
- `POST /api/v1/auth/refresh` — extends session
- `GET /api/v1/auth/me` — current user profile, 401 if not logged in

**The bot does not need any of this** unless it's creating user-scoped alerts/portfolios.

---

## 22. Blinks & Solana Actions

Permissive CORS (`*`). Used for Twitter/X Blink unfurling of Solana transactions.

- `GET /.well-known/actions.json`, `/actions.json`, `/actions` — action metadata for wallets
- `POST /api/v1/blinks/create` — create a shareable Blink
- `GET /api/v1/blinks/{blink_id}` — fetch Blink metadata (unfurl)
- `POST /api/v1/blinks/{blink_id}` — execute (build tx for wallet to sign)
- `GET /api/v1/blinks/{blink_id}/icon.png` — dynamic icon
- `GET /blinks/{blink_id}` — human-readable redirect

If the bot's tweets include Blinks links, they rely on these routes. No direct API calls usually needed from the bot.

---

## 23. Public Status

### `GET /api/public/v1/status`
Envelope. High-level system health for the public status page. Does not count against rate limits in the same bucket.

---

## Appendix A — Required vs. optional address fields

| Field | Required shape |
|---|---|
| Token address | Solana base58 32–44 chars OR EVM `0x` + 40 hex |
| EVM contract | `0x` + 40 hex |
| EVM wallet (shield) | `0x` + 40 hex |
| Any wallet (portfolio/intel) | Solana OR EVM |
| Pool id | DefiLlama UUID (from `/defi/pools`) |
| Pair address | DEX pair (Raydium/Uniswap/etc.) — chain auto-resolved |

## Appendix B — Supported chain slugs

Canonical: `solana`, `ethereum`, `base`, `arbitrum`, `bsc`, `polygon`, `optimism`, `avalanche`.
Aliases accepted on input (auto-normalized): `sol`, `eth`, `arb`, `bnb`, `matic`, `op`, `avax`.

## Appendix C — Error code catalog

| Code | Meaning |
|---|---|
| `INVALID_REQUEST` | Pydantic validation failed; `details.message` has the field |
| `INVALID_ADDRESS` | Address format not Solana/EVM |
| `INVALID_CHAIN` / `UNKNOWN_CHAIN` | Chain slug unsupported |
| `UNSUPPORTED_CHAIN` | Endpoint doesn't support this chain family (e.g. contract scan on Solana) |
| `MISSING_ADDRESS` | URL param missing |
| `NOT_FOUND` | Cache miss or resource not found |
| `INVALID_PARAMS` | Query param type or range violated |
| `ANALYSIS_FAILED` | Analyzer pipeline failed mid-run (500) |
| `DEFI_ANALYSIS_FAILED` | DeFi analyzer failed (500) |
| `TRENDING_FAILED` | Upstream DEX data unavailable (500) |
| `WHALE_FAILED` | Whale DB/stream failure (500) |
| `PROFILE_FAILED` | Whale profile failure (500) |
| `SMART_MONEY_FETCH_FAILED` | DB read failed (502) |
| `SERVICE_UNAVAILABLE` | Subsystem not initialized (503) |
| `RATE_LIMIT_EXCEEDED` | 429; check `Retry-After` |
| `INTERNAL_ERROR` | Unhandled (500) |

## Appendix D — Minimum set of endpoints the bot actually uses

If the bot wants to ship with the smallest surface possible:

1. `POST /api/v1/analyze` + `GET /api/v1/token/{addr}` — token safety + market + AI narrative
2. `GET /api/v1/search` — symbol → address resolution
3. `GET /api/v1/trending` — daily/hourly "what's hot" tweets
4. `GET /api/v1/whales/token/{addr}` — whale-alert tweets
5. `POST /api/v1/defi/pool/analyze` + `GET /api/v1/defi/pools` — LP/yield tweets
6. `POST /api/v1/contract/scan` — EVM contract audit tweets

Everything else is nice-to-have.
