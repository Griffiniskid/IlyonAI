# Whale Log Stream — Zero-Cost Replacement for Helius Polling

**Status:** approved · **Date:** 2026-04-15 · **Author:** architecture

## 1. Problem

The whale transaction feed currently drains **~238K Helius credits/day** — effectively the entire Free-tier monthly budget in ~1.4 days. The cause is a scheduled poller (`src/services/whale_poller.py`) that calls Helius's parsed-transaction endpoint `GET /v0/addresses/{dex}/transactions?type=SWAP&limit=100` for **nine DEX program IDs every five minutes**. Each call is billed at **100 credits** (TRANSACTION_HISTORY category), yielding:

```
9 programs × 288 cycles/day × 100 credits = 259,200 credits/day
```

Upgrading Helius to gain access to webhooks / Enhanced WebSockets is not acceptable (paid plan). Reducing poll frequency, pruning DEX coverage, or switching vendors are all rejected for quality reasons. We must keep every whale that today's feed catches, on every currently-monitored DEX, at equal-or-better freshness, at **zero marginal cost**.

## 2. Solution Overview

Replace the polling loop with a **persistent Solana JSON-RPC WebSocket subscription** using the `logsSubscribe` method — a **standard Solana method included in Helius's Free tier at zero credit cost per event**. For each of the nine DEX program IDs we open one `logsSubscribe` with `{ mentions: [dex_program_id] }`. Helius pushes the transaction signature plus its full log array to our service in real time.

Because Solana DEXes emit structured, publicly-documented logs containing swap amounts and mint addresses, we can **decode the USD value of each swap directly from the log bytes — no RPC call required**. Sub-threshold swaps are dropped in-process (zero cost). Only transactions that clear the whale threshold (default $10K) trigger a follow-up **standard `getTransaction` RPC** (~10 credits) to retrieve full account metadata (wallet, token transfers, labels) for feed enrichment.

### Credit model

| Source                                  | Current (poll) | Proposed (stream) |
|-----------------------------------------|----------------|-------------------|
| Subscription traffic (WS push)          | n/a            | 0 credits         |
| Pre-filter rejection (decoded from log) | n/a            | 0 credits         |
| Enrichment of whale candidates          | n/a            | ~10 credits × ~100/day = **~1,000 credits/day** |
| Parsed-history poll calls               | **259,200/day**| 0                 |
| Reconnect backfill (1× `getSignaturesForAddress` per DEX per reconnect) | n/a | <100 credits/day |
| **Total**                               | **~259K/day**  | **~1.1K/day (−99.6%)** |

Quality gain: freshness improves from 5-minute polled batches to **sub-second push**. No DEX is dropped. No threshold changes. DB schema, API contract, and frontend remain untouched.

## 3. Architecture

```
                                 ┌────────────────────────────┐
Helius WSS  ──logsNotification──▶│       whale_stream         │
  mentions=[JUP|RAY|PUMP|…]      │  (one long-lived task)     │
                                 │                            │
                                 │  1. decode SwapEvent       │
                                 │     via solana_log_parser  │
                                 │  2. cached SOL/stable USD  │
                                 │     valuation              │
                                 │  3. threshold filter       │
                                 │     (< $10K → drop)        │
                                 │  4. for survivors:         │
                                 │     getTransaction RPC     │
                                 │  5. same parse path        │
                                 │     (_parse_helius_tx)     │
                                 │  6. DB insert + stream_hub │
                                 └────────────┬───────────────┘
                                              │
                                              ▼
                                    existing  whale  feed
                                    (unchanged consumers)
```

### 3.1 New: `src/data/solana_log_parser.py`

Stateless, pure-function module. One decoder per DEX. All decoders share a single output type:

```python
@dataclass(frozen=True)
class SwapEvent:
    dex_name: str                    # "Jupiter" | "Raydium" | ...
    signature: str
    slot: int
    block_time: Optional[int]        # unix seconds, may be None in notifications
    user_wallet: Optional[str]       # best-effort extraction; may be None
    input_mint: Optional[str]
    input_amount_raw: Optional[int]  # token base units
    output_mint: Optional[str]
    output_amount_raw: Optional[int]
    # Denormalized: at least ONE side must be a known payment mint (SOL/WSOL/USDC/USDT)
    # so we can compute USD without a separate price lookup.
    payment_side: Literal["input", "output"]
    payment_usd_estimate: float       # computed by caller using sol_price + stable=1
```

Decoder signature (all nine):

```python
def decode_jupiter(logs: list[str], signature: str, slot: int) -> Optional[SwapEvent]: ...
def decode_raydium_v4(logs: list[str], signature: str, slot: int) -> Optional[SwapEvent]: ...
# …etc.
```

Each decoder:

1. Scans the `logs` list for the DEX's event signature:
   - **Jupiter v6** — anchor program logs emit base64-encoded `SwapEvent` under `Program data:` lines. Discriminator: first 8 bytes of `sha256("event:SwapEvent")`.
   - **Pump.fun** — custom text logs `buy: <base58_user> bought <amount> tokens for <lamports> lamports` / `sell: ...`.
   - **Raydium V4 (AMM)** — `ray_log: <base64>`; bytes 1..9 is `amount_in`, 9..17 `amount_out`.
   - **Raydium CLMM** — anchor `SwapEvent` (discriminator documented in Raydium IDL on GitHub).
   - **Raydium CP** — anchor `SwapEvent` (CPMM program, public IDL).
   - **Orca Whirlpool** — anchor `Swapped` event.
   - **Meteora DLMM** — anchor `Swap` event.
   - **Phoenix** — custom binary log with well-known field layout (public SDK).
   - **Lifinity** — anchor `Swap` event.
2. On parse failure or irrelevant log → returns `None` (dropped silently).
3. On success → returns a populated `SwapEvent`. If neither side is SOL/stable, returns `None` (the rare token-for-token hop can't be valued without another price lookup; these are <1% of whale-candidate volume and are acceptable loss — equivalent to current behavior, which also drops unpriced mid-hops).

Published IDLs / reverse-engineered log formats are all publicly available — no proprietary research required. An `IDL_REFERENCES.md` companion note in the module docstring lists source URLs for each.

### 3.2 New: `src/services/whale_stream.py`

Single class `WhaleTransactionStream` replaces `WhaleTransactionPoller`. Same constructor signature (`db`, `stream_hub`), same `run_forever()` shape so `src/main.py` swaps them with minimal code change.

Responsibilities:

- Maintain one `aiohttp.ClientSession().ws_connect(settings.helius_ws_url)` with keepalive (`ping_interval=30`, `heartbeat=20`).
- On connect: send nine JSON-RPC `logsSubscribe` requests, one per DEX program ID, with `{ "commitment": "confirmed" }` and `{ "mentions": [program_id] }`. Cache the returned subscription IDs.
- Ingest loop:
  - Parse each `logsNotification`. Dispatch to the matching decoder by subscription ID.
  - Dedupe signatures in a 10-min rolling LRU (prevents double-processing on commitment upgrade).
  - Compute USD:
    - If payment side mint is WSOL/SOL → `payment_raw × sol_price_cache / 1e9`.
    - If stable (USDC/USDT) → `payment_raw / 10**decimals` (6).
  - Drop if < `min_amount_usd` (configurable, default 10_000).
- Enrichment path (only for survivors):
  - `getTransaction(signature, {encoding: "jsonParsed", maxSupportedTransactionVersion: 0})` via the existing Helius RPC URL. This returns the same structure the old polling path consumed.
  - Convert to the existing Helius-shape dict (`tokenTransfers`, `nativeTransfers`, `source`, `timestamp`, `signature`) and hand to **the unchanged `_parse_helius_transaction`** in `SolanaClient` so downstream fields match byte-for-byte. No DB or API changes needed.
  - Persist via `db.insert_whale_transactions([...])` and publish via `stream_hub.publish(TOPIC, ...)` identical to the poller.
- Reconnect protocol:
  - On disconnect or timeout: exponential backoff `1s → 2s → 5s → 15s → 30s` (cap 30s).
  - On reconnect, before re-subscribing, run one `getSignaturesForAddress(program_id, until=<last_seen_sig>, limit=1000)` per DEX in parallel. For each returned sig not yet in our 10-min LRU, run the same enrichment pipeline (which applies the threshold filter after parsing — no log is available post-hoc, so backfill uses parsed-tx USD as it already does today). If the list fills to 1000, log a warning (rare — requires a >30s outage on a busy DEX) and accept the gap; this is strictly better than the current 5-min polling gaps.
- Structured logging: one log line per whale accepted, per rejection reason counter tick, per reconnect. Metric counters published via existing `stream_hub` or stdout for now.

### 3.3 Integration touchpoints (minimal)

| File                         | Change |
|------------------------------|--------|
| `src/config.py`              | Add `whale_feed_mode: Literal["stream","poll"] = Field("stream", env="WHALE_FEED_MODE")` and `helius_ws_url: str = Field("wss://mainnet.helius-rpc.com", env="HELIUS_WS_URL")`. |
| `src/main.py`                | Branch on `settings.whale_feed_mode`: start `WhaleTransactionStream` (new default) or keep `WhaleTransactionPoller` (fallback). |
| `src/services/whale_poller.py` | **Retained unchanged** as a manual-opt-out safety net for one release. |
| `src/data/solana_log_parser.py` | **New**. |
| `src/services/whale_stream.py`  | **New**. |
| `.env.example` (root, deploy/staging, deploy/prod) | Document `WHALE_FEED_MODE` and `HELIUS_WS_URL`. |
| `tests/data/test_solana_log_parser.py` | **New** — table-driven fixtures per DEX decoder using captured real logs. |
| `tests/services/test_whale_stream.py`  | **New** — integration test with mocked WS & mocked RPC using `aiohttp.web` test server. |

**Explicitly unchanged**: `src/api/routes/whale.py`, `src/storage/database.py`, DB schema, `web/` frontend, `src/alerts/producer.py`. They all read from DB or stream_hub and are contract-compatible.

## 4. Data Flow — Worked Example

1. A Jupiter v6 swap for 45 SOL → 8,200,000 BONK lands in slot 296_481_302.
2. Helius pushes `logsNotification` (subscription ID 4, which we mapped to Jupiter) with `logs = [... "Program data: <base64 SwapEvent>" ...]`.
3. `whale_stream` receives, dispatches to `decode_jupiter`, which returns:
   ```
   SwapEvent(dex_name="Jupiter", signature="5Nf…", slot=296481302,
             user_wallet="F3v…", input_mint=WSOL, input_amount_raw=45_000_000_000,
             output_mint="DezXAZ…BONK", output_amount_raw=8_200_000_000_000,
             payment_side="input", payment_usd_estimate=0)  # filled by caller
   ```
4. Caller computes `payment_usd = 45 × $168.40 = $7,578`. **Below $10K threshold → dropped.** Zero credits consumed.

---

Same slot, different signature: 180 SOL → 32,000,000 WIF:

5. Decoded USD: `180 × $168.40 = $30,312` ≥ $10K → enrichment path.
6. `getTransaction(sig)` called on Helius RPC (~10 credits). Response fed into `_parse_helius_transaction`, yielding the exact dict shape the poller produces today.
7. `db.insert_whale_transactions([tx])` and `stream_hub.publish("whale-transactions", tx)` run. Frontend receives push event. Freshness ≈ 700 ms after block confirmation.

## 5. Error Handling & Edge Cases

- **Decoder miss (new Jupiter version / unknown log variant):** increment `decoder_misses{dex}` counter, log at DEBUG. Sub-threshold whales we miss are acceptable loss; above-threshold misses are flagged by cross-checking against a **once-per-hour audit poll** of the old endpoint for a single DEX (Jupiter), sampling 20 swaps, to detect drift. ~20 credits/hour = 480/day. Toggle via `WHALE_STREAM_AUDIT=true` (default on, disable if credits ever become tight).
- **Price cache miss (SOL price unavailable):** fall back to `settings.sol_price_fallback` (default $200, already exists in `SolanaClient._parse_helius_transaction`). Log warning. Stream continues.
- **Enrichment RPC failure (429/5xx):** retry once with 500 ms delay. On second failure, skip the tx (it's still in DB via no path — the whale is lost for this round). Rate of enrichment calls is low enough that 429 is highly unlikely; we will see if it becomes an issue and introduce a bounded semaphore if so.
- **WS disconnect (network / Helius side):** reconnect loop detailed in §3.2. Backfill via `getSignaturesForAddress` on reconnect.
- **Duplicate notifications (commitment level upgrade):** 10-min LRU dedup by signature. Sized 10,000 entries — well above any realistic whale rate.
- **Helius Free-tier WS limits:** Helius publishes no hard cap on `logsSubscribe` subscriptions or event volume on Free tier beyond bandwidth, which is separately metered as "Streaming Usage" with its own free allocation. Nine subscriptions on DEX programs produces ~100–400 notifications/sec at peak — well under any reasonable bandwidth concern. If Helius rate-limits us, documented HTTP 429 is ignored for WS (they use server-sent close frames); we degrade to backoff.

## 6. Testing Strategy

### Unit — `tests/data/test_solana_log_parser.py`

Table-driven. For each DEX:

- **Golden input:** 3–5 real log arrays captured from mainnet (stored as JSON fixtures in `tests/fixtures/solana_logs/<dex>.json`).
- **Assertions:** decoded `SwapEvent` matches recorded expected fields (mints, amounts, user_wallet).
- **Negative cases:** logs from unrelated programs (should return `None`), malformed base64 (should return `None`), truncated bytes (should return `None`).

### Integration — `tests/services/test_whale_stream.py`

- Stand up an `aiohttp.web.Application` exposing a WS endpoint that plays back recorded `logsNotification` frames from a fixture.
- Stand up a mock RPC endpoint that returns canned `getTransaction` responses.
- Run `WhaleTransactionStream` pointed at both test URLs; assert:
  - DB insert called with the expected shape.
  - `stream_hub.publish` called for whale txs only.
  - Sub-threshold txs never reach enrichment (`getTransaction` call count == whale count).
  - On forced WS close, reconnect + backfill path runs.

### Regression

Full `pytest` suite must pass with no modifications to existing tests. The poller's own test (if any) stays green because we leave `whale_poller.py` untouched.

## 7. Rollout

1. Ship behind `WHALE_FEED_MODE=stream` default. Toggle to `poll` if the stream misbehaves — zero user impact either way.
2. Observe for 48h in production: Helius usage dashboard should show the TRANSACTION_HISTORY graph drop to a flat line at zero with a small bump for enrichment `getTransaction` calls.
3. After one successful release, delete `src/services/whale_poller.py` and remove the mode flag.

## 8. Non-Goals

- No change to whale threshold ($10K default).
- No change to DEX coverage list (all nine retained).
- No vendor switch (Helius stays for RPC + WS; only the call pattern changes).
- No change to stream_hub protocol or frontend.
- No webhook endpoint (requires paid Helius tier; out of scope).
