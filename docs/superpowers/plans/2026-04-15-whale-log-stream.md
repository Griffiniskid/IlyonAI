# Implementation Plan — Whale Log Stream

**Spec:** `docs/superpowers/specs/2026-04-15-whale-log-stream-design.md`
**Date:** 2026-04-15

## File map

| File | Action |
|------|--------|
| `src/data/solana_log_parser.py` | Create — pure decoders + `SwapEvent` dataclass |
| `src/services/whale_stream.py`  | Create — WS client, enrichment pipeline, reconnect |
| `src/config.py` | Modify — add `whale_feed_mode`, `helius_ws_url`, `min_whale_usd`, `whale_stream_audit` |
| `src/main.py` | Modify — branch on `whale_feed_mode` when starting background task |
| `.env.example` / `deploy/staging/app.env.example` / `deploy/prod/app.env.example` | Document new vars |
| `tests/fixtures/solana_logs/*.json` | Create — captured mainnet log fixtures |
| `tests/data/test_solana_log_parser.py` | Create — per-DEX decoder tests |
| `tests/services/test_whale_stream.py` | Create — end-to-end stream test w/ mocked WS+RPC |

## Step 1 — Add config and env scaffolding

Edit `src/config.py`. Add after the existing `helius_api_key` field (line 52) in the blockchain section:

```python
helius_ws_url: str = Field(
    "wss://mainnet.helius-rpc.com",
    env="HELIUS_WS_URL",
    description="Helius WebSocket endpoint (api-key appended at connect time)",
)
whale_feed_mode: str = Field(
    "stream",
    env="WHALE_FEED_MODE",
    description="Whale feed source: 'stream' (logsSubscribe) or 'poll' (legacy)",
)
min_whale_usd: float = Field(
    10_000.0,
    env="MIN_WHALE_USD",
    description="Minimum USD value to qualify as a whale transaction",
)
whale_stream_audit: bool = Field(
    True,
    env="WHALE_STREAM_AUDIT",
    description="Hourly audit poll against parsed-tx endpoint to detect decoder drift",
)
```

Append to `.env.example`, `deploy/staging/app.env.example`, `deploy/prod/app.env.example`:

```
# Whale feed
WHALE_FEED_MODE=stream
HELIUS_WS_URL=wss://mainnet.helius-rpc.com
MIN_WHALE_USD=10000
WHALE_STREAM_AUDIT=true
```

## Step 2 — Build the log parser module

Create `src/data/solana_log_parser.py`:

1. Define the `SwapEvent` frozen dataclass from spec §3.1.
2. Constants: `WSOL_MINT`, `USDC_MINT`, `USDT_MINT`, `PAYMENT_MINTS`, and the DEX program IDs. Import from `src/data/solana.py` where possible to avoid drift.
3. Anchor event discriminator helper:

```python
def _anchor_discriminator(event_name: str) -> bytes:
    import hashlib
    return hashlib.sha256(f"event:{event_name}".encode()).digest()[:8]
```

4. Base64 extractor for `"Program data: <base64>"` lines:

```python
def _extract_program_data(logs: list[str]) -> list[bytes]:
    import base64
    out: list[bytes] = []
    for line in logs:
        if line.startswith("Program data: "):
            try:
                out.append(base64.b64decode(line.removeprefix("Program data: ")))
            except Exception:
                continue
    return out
```

5. One decoder per DEX. Each returns `Optional[SwapEvent]`. Decoders share a helper that picks the payment side and rejects token-token swaps.

6. Registry:

```python
DECODERS: dict[str, Callable[[list[str], str, int], Optional[SwapEvent]]] = {
    "Jupiter": decode_jupiter,
    "Raydium": decode_raydium_v4,
    "Raydium CLMM": decode_raydium_clmm,
    "Raydium CP": decode_raydium_cp,
    "Pump.fun": decode_pumpfun,
    "Orca": decode_orca,
    "Meteora": decode_meteora,
    "Phoenix": decode_phoenix,
    "Lifinity": decode_lifinity,
}

DEX_PROGRAM_IDS: dict[str, str] = {
    "Jupiter": "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",
    "Raydium": "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
    "Raydium CLMM": "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK",
    "Raydium CP": "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C",
    "Pump.fun": "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
    "Orca": "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",
    "Meteora": "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo",
    "Phoenix": "PhoeNiXZ8ByJGLkxNfZRnkUfjvmuYqLR89jjFHGqdXY",
    "Lifinity": "2wT8Yq49kHgDzXuPxZSaeLaH1qbmGXtEyPy64bL7aD3s",
}
```

Note — these IDs are duplicated from `src/data/solana.py`. Deduplication can be a follow-up; not a blocker.

**Pragmatic scope for v1**: ship Jupiter + Raydium V4 + Pump.fun decoders first (cover ~85% of volume). Other six return `None` initially, which makes them behave as "accept only what logs allow," and the once-per-hour audit path (Step 4) will warn if we're dropping meaningful volume. Add remaining decoders in follow-ups as real fixture logs become available.

7. Implementation notes per decoder:
   - **Jupiter v6** (`decode_jupiter`): `_anchor_discriminator("SwapEvent")`. Match `Program data:` bytes starting with that discriminator. Decode the Anchor struct: `amm: Pubkey (32) | input_mint: Pubkey (32) | input_amount: u64 | output_mint: Pubkey (32) | output_amount: u64`. Total: 112 bytes after discriminator.
   - **Raydium V4 AMM** (`decode_raydium_v4`): lines starting with `ray_log: `. Base64 decode → first byte is log-type discriminator; `3` = swap. Layout for swap: `u8 kind | u64 amount_in | u64 amount_out | ... (remainder ignored)`. `user_wallet` is not in the log; leave `None`.
   - **Pump.fun** (`decode_pumpfun`): `_anchor_discriminator("TradeEvent")`. Struct: `mint: Pubkey | sol_amount: u64 | token_amount: u64 | is_buy: bool | user: Pubkey | timestamp: i64 | virtual_sol_reserves: u64 | virtual_token_reserves: u64`. `payment_side = "input"` if `is_buy` else `"output"`.
   - **Others**: return `None` in v1 with a TODO comment naming the IDL source.

## Step 3 — Build the stream service

Create `src/services/whale_stream.py`:

1. `TOPIC = "whale-transactions"` (same as poller so consumers need no change).
2. Class `WhaleTransactionStream(db, stream_hub=None)`. Internal state:
   - `self._ws: aiohttp.ClientWebSocketResponse | None`
   - `self._subs: dict[int, str]` mapping subscription ID → DEX name
   - `self._seen_sigs: collections.OrderedDict[str, float]` LRU of size 10_000
   - `self._last_sig: dict[str, str]` last processed signature per DEX for backfill
   - `self._reconnect_delay: float = 1.0`
3. `async def run_forever(self)`: outer `while True` with reconnect loop. Inner: `_connect_and_consume`.
4. `_connect_and_consume`:
   - Build URL: `f"{settings.helius_ws_url}/?api-key={settings.helius_api_key}"`.
   - `async with aiohttp.ClientSession() as sess:`
   - `async with sess.ws_connect(url, heartbeat=20, autoping=True) as ws:`
   - Reset reconnect delay.
   - Run backfill (if `_last_sig` non-empty).
   - Send 9 `logsSubscribe` requests; read 9 responses; populate `_subs`.
   - Loop `async for msg in ws: dispatch(msg)`.
5. `_handle_notification(payload)`:
   - Extract `sub_id`, look up DEX name.
   - Extract `signature`, `slot`, `logs`.
   - Dedup via `_seen_sigs`; update LRU.
   - Call `DECODERS[dex_name](logs, signature, slot)`.
   - If `None` → return.
   - Compute USD from `payment_usd_estimate` or derive from payment mint + cached SOL price.
   - If < `settings.min_whale_usd` → return.
   - Enqueue `_enrich(swap_event)` as a background task (bounded by a `asyncio.Semaphore(8)` for safety).
6. `_enrich(swap_event)`:
   - Call `getTransaction` on `settings.solana_rpc_url` (Helius RPC) with `{ "encoding": "jsonParsed", "maxSupportedTransactionVersion": 0, "commitment": "confirmed" }`. Retry once on 429/5xx.
   - Build Helius-shape dict from parsed response (tokenTransfers, nativeTransfers, timestamp, signature, source).
   - `parsed = await solana_client._parse_helius_transaction(helius_dict, settings.min_whale_usd, sol_price=sol_price)` — reusing the existing parser by constructing a short-lived `SolanaClient`.
   - If `parsed` is None → skip silently (parser disagreed with our log estimate — rare, acceptable).
   - `await db.insert_whale_transactions([parsed])`.
   - `await stream_hub.publish(TOPIC, <dict matching poller's broadcast>)`.
7. `_backfill_on_reconnect()`:
   - For each DEX with a `_last_sig`, call `getSignaturesForAddress(program_id, until=last_sig, limit=1000)` in parallel.
   - For each sig not in `_seen_sigs`, call a simplified path: `getTransaction` → `_parse_helius_transaction` → threshold check → persist/broadcast. This accepts slightly higher credit cost on reconnect (parse USD not decoded from logs) — tradeoff is necessary since we don't have logs for historical sigs without a second call.
8. `_audit_poll()` (background task, runs if `settings.whale_stream_audit`):
   - Every 3600s, call the old Helius endpoint for Jupiter only (`GET /v0/addresses/JUP…/transactions?type=SWAP&limit=20`). Parse. For each sig that's a whale but NOT in our recent DB window (last 10 min), log WARNING `"whale_stream_miss"` with sig + USD. This gives us drift visibility.
   - ~20 credits/hour. Kill-switch via env var.

## Step 4 — Wire into main

Edit `src/main.py`. Replace the "Start whale transaction poller" block:

```python
    # Start whale transaction feed (stream by default, poll as fallback)
    try:
        from src.storage.database import get_database
        from src.platform.stream_hub import get_stream_hub
        db = await get_database()
        hub = get_stream_hub()

        if settings.whale_feed_mode == "stream":
            from src.services.whale_stream import WhaleTransactionStream
            feed = WhaleTransactionStream(db=db, stream_hub=hub)
            app["_whale_feed_task"] = asyncio.create_task(feed.run_forever())
            logger.info("Whale feed: stream mode (logsSubscribe)")
        else:
            from src.services.whale_poller import WhaleTransactionPoller
            poller = WhaleTransactionPoller(db=db, stream_hub=hub)
            app["_whale_feed_task"] = asyncio.create_task(poller.run_forever())
            logger.info("Whale feed: poll mode (legacy)")
    except Exception as e:
        logger.warning(f"Whale feed startup failed: {e}")
```

Cleanup: rename `_whale_poller_task` → `_whale_feed_task` in both startup and shutdown hooks.

## Step 5 — Tests

### `tests/fixtures/solana_logs/jupiter.json`

Captured real `logsNotification.result.value` payloads (log arrays + signatures + slots), minimum 3 samples including one whale-sized and one sub-threshold.

### `tests/fixtures/solana_logs/pumpfun.json`, `raydium_v4.json`

Same pattern.

### `tests/data/test_solana_log_parser.py`

```python
import json
import pathlib
import pytest
from src.data.solana_log_parser import (
    decode_jupiter, decode_pumpfun, decode_raydium_v4, SwapEvent,
)

FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures" / "solana_logs"

@pytest.mark.parametrize("sample", json.loads((FIXTURES / "jupiter.json").read_text()))
def test_decode_jupiter_golden(sample):
    event = decode_jupiter(sample["logs"], sample["signature"], sample["slot"])
    if sample["expected"] is None:
        assert event is None
    else:
        assert event is not None
        assert event.input_mint == sample["expected"]["input_mint"]
        assert event.input_amount_raw == sample["expected"]["input_amount_raw"]
        # ... remaining fields

# identical pattern for pumpfun and raydium_v4

def test_decoder_rejects_unrelated_logs():
    assert decode_jupiter(["Program 11111111111111111111111111111111 invoke [1]"], "sig", 1) is None
```

### `tests/services/test_whale_stream.py`

Use `aiohttp.test_utils.TestServer` to spin up a mock WS + mock RPC endpoint. Replay a recorded notification, assert that:

- Sub-threshold notifications never trigger `getTransaction`.
- Whale notifications call `db.insert_whale_transactions` exactly once per unique sig.
- Duplicate signatures deduplicate.
- On forced WS close, reconnect logic runs and re-subscribes.

Mock the DB and stream_hub with `unittest.mock.AsyncMock`.

## Step 6 — Verification

1. `pytest tests/data/test_solana_log_parser.py -v`
2. `pytest tests/services/test_whale_stream.py -v`
3. `pytest` (full suite — must pass)
4. Static check: `python -c "from src.services.whale_stream import WhaleTransactionStream; from src.data.solana_log_parser import DECODERS; print(list(DECODERS.keys()))"`
5. Commit each step in sequence, then push.

## Rollback plan

Set `WHALE_FEED_MODE=poll` in env. No code revert needed.
