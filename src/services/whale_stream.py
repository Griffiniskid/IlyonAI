"""
WhaleTransactionStream — real-time whale feed via Solana `logsSubscribe`.

This service replaces the polling `WhaleTransactionPoller` with a persistent
WebSocket subscription to Helius. It consumes exactly zero TRANSACTION_HISTORY
credits under steady state: swap amounts are decoded directly from program
logs, sub-threshold trades are dropped in-process, and only survivors trigger
a single standard `getTransaction` RPC for enrichment.

Contract equivalence with the poller:
  - Publishes to the same `TOPIC = "whale-transactions"` on the stream hub.
  - Persists via `db.insert_whale_transactions`, yielding rows of identical
    shape (the enrichment step reuses `SolanaClient._parse_helius_transaction`).
  - Constructor signature matches the poller so `main.py` can swap them.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import OrderedDict
from typing import Any, Optional

import aiohttp

from src.config import settings
from src.data.solana import SolanaClient
from src.data.solana_log_parser import (
    DECODERS,
    DEX_PROGRAM_IDS,
    SwapEvent,
    compute_payment_usd,
)
from src.platform.stream_hub import get_stream_hub
from src.storage.database import Database

logger = logging.getLogger(__name__)

TOPIC = "whale-transactions"

_DEDUP_SIZE = 10_000
_ENRICH_CONCURRENCY = 8
_RECONNECT_DELAYS = [1.0, 2.0, 5.0, 15.0, 30.0]
_AUDIT_INTERVAL_SECONDS = 3600


class WhaleTransactionStream:
    """Streams DEX swap events via logsSubscribe and persists whale-sized trades."""

    def __init__(
        self,
        db: Database,
        stream_hub=None,
    ):
        self._db = db
        self._stream_hub = stream_hub or get_stream_hub()
        self._seen_sigs: OrderedDict[str, float] = OrderedDict()
        self._last_sig: dict[str, str] = {}
        self._sub_to_dex: dict[int, str] = {}
        self._enrich_sem = asyncio.Semaphore(_ENRICH_CONCURRENCY)
        self._solana_client: Optional[SolanaClient] = None

    # ─── Public lifecycle ────────────────────────────────────────────────

    async def run_forever(self) -> None:
        """Main loop: connect, consume, reconnect with exponential backoff."""
        logger.info(
            "Whale stream starting (mode=logsSubscribe, dexes=%d, min_usd=%s)",
            len(DEX_PROGRAM_IDS), settings.min_whale_usd,
        )
        self._solana_client = SolanaClient(
            rpc_url=settings.solana_rpc_url,
            helius_api_key=settings.helius_api_key,
        )
        audit_task: Optional[asyncio.Task] = None
        if settings.whale_stream_audit:
            audit_task = asyncio.create_task(self._audit_loop())

        attempt = 0
        try:
            while True:
                try:
                    await self._connect_and_consume()
                    attempt = 0
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    delay = _RECONNECT_DELAYS[min(attempt, len(_RECONNECT_DELAYS) - 1)]
                    logger.warning("Whale stream disconnected: %s — reconnect in %.1fs", e, delay)
                    attempt += 1
                    await asyncio.sleep(delay)
        finally:
            if audit_task:
                audit_task.cancel()

    # ─── Connection ──────────────────────────────────────────────────────

    async def _connect_and_consume(self) -> None:
        if not settings.helius_api_key:
            raise RuntimeError("HELIUS_API_KEY is not configured; whale stream cannot start")

        url = f"{settings.helius_ws_url}/?api-key={settings.helius_api_key}"
        async with aiohttp.ClientSession() as sess:
            async with sess.ws_connect(
                url,
                heartbeat=20.0,
                autoping=True,
                max_msg_size=0,
            ) as ws:
                await self._subscribe_all(ws)
                logger.info("Whale stream connected; %d subscriptions active", len(self._sub_to_dex))

                # Backfill after we know the connection is live.
                if self._last_sig:
                    asyncio.create_task(self._backfill_from_last_seen())

                async for raw in ws:
                    if raw.type == aiohttp.WSMsgType.TEXT:
                        await self._handle_message(raw.data)
                    elif raw.type == aiohttp.WSMsgType.CLOSED:
                        raise ConnectionError("WS closed by server")
                    elif raw.type == aiohttp.WSMsgType.ERROR:
                        raise ConnectionError(f"WS error: {ws.exception()}")

    async def _subscribe_all(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        self._sub_to_dex.clear()
        pending: dict[int, str] = {}
        for req_id, (dex_name, program_id) in enumerate(DEX_PROGRAM_IDS.items(), start=1):
            payload = {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": "logsSubscribe",
                "params": [
                    {"mentions": [program_id]},
                    {"commitment": "confirmed"},
                ],
            }
            await ws.send_json(payload)
            pending[req_id] = dex_name

        # Drain subscription responses (order isn't guaranteed — use id match).
        remaining = set(pending.keys())
        while remaining:
            msg = await ws.receive(timeout=15.0)
            if msg.type != aiohttp.WSMsgType.TEXT:
                raise ConnectionError(f"Unexpected WS frame during subscribe: {msg.type}")
            data = json.loads(msg.data)
            req_id = data.get("id")
            if req_id in remaining:
                sub_id = data.get("result")
                if isinstance(sub_id, int):
                    self._sub_to_dex[sub_id] = pending[req_id]
                remaining.discard(req_id)
            # Silently ignore any notifications that arrived between subscribes.

    # ─── Message handling ────────────────────────────────────────────────

    async def _handle_message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        if msg.get("method") != "logsNotification":
            return

        params = msg.get("params") or {}
        sub_id = params.get("subscription")
        dex_name = self._sub_to_dex.get(sub_id)
        if not dex_name:
            return

        result = params.get("result") or {}
        value = result.get("value") or {}
        signature = value.get("signature")
        if not signature or value.get("err") is not None:
            return

        # Dedup (commitment-upgrade notifications deliver the same sig twice).
        if signature in self._seen_sigs:
            return
        self._remember_sig(signature)
        self._last_sig[dex_name] = signature

        slot = result.get("context", {}).get("slot") or 0
        logs = value.get("logs") or []

        decoder = DECODERS.get(dex_name)
        if decoder is None:
            return
        event = decoder(logs, signature, int(slot))
        if event is None:
            return

        sol_price = await self._get_sol_price()
        usd = compute_payment_usd(event, sol_price)
        if usd < settings.min_whale_usd:
            return

        asyncio.create_task(self._enrich_and_persist(event, usd))

    def _remember_sig(self, signature: str) -> None:
        self._seen_sigs[signature] = time.time()
        if len(self._seen_sigs) > _DEDUP_SIZE:
            self._seen_sigs.popitem(last=False)

    async def _get_sol_price(self) -> float:
        if self._solana_client is None:
            return 200.0
        try:
            return await self._solana_client._get_sol_price()
        except Exception:
            return 200.0

    # ─── Enrichment ──────────────────────────────────────────────────────

    async def _enrich_and_persist(self, event: SwapEvent, decoded_usd: float) -> None:
        async with self._enrich_sem:
            try:
                helius_shape = await self._fetch_and_shape(event)
            except Exception as e:
                logger.debug("Whale stream enrichment failed for %s: %s", event.signature, e)
                return

            if helius_shape is None:
                return

            try:
                sol_price = await self._get_sol_price()
                parsed = await self._solana_client._parse_helius_transaction(
                    helius_shape,
                    min_amount_usd=settings.min_whale_usd,
                    sol_price=sol_price,
                )
            except Exception as e:
                logger.debug("Whale stream parse failed for %s: %s", event.signature, e)
                return

            if parsed is None:
                return

            parsed.setdefault("dex_name", event.dex_name)

            try:
                new_sigs = await self._db.insert_whale_transactions([parsed])
            except Exception as e:
                logger.warning("Whale stream DB insert failed for %s: %s", event.signature, e)
                return

            if not new_sigs:
                return

            await self._broadcast(parsed)
            logger.info(
                "🐋 Whale captured: %s %s $%.0f on %s (decoded=$%.0f)",
                parsed.get("type"), parsed.get("token_symbol", "?"),
                float(parsed.get("amount_usd", 0)), event.dex_name, decoded_usd,
            )

    async def _fetch_and_shape(self, event: SwapEvent) -> Optional[dict[str, Any]]:
        """Call standard getTransaction, repackage into Helius-enhanced shape."""
        url = f"https://mainnet.helius-rpc.com/?api-key={settings.helius_api_key}"
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [
                event.signature,
                {
                    "encoding": "jsonParsed",
                    "maxSupportedTransactionVersion": 0,
                    "commitment": "confirmed",
                },
            ],
        }
        for attempt in range(2):
            try:
                async with aiohttp.ClientSession() as sess:
                    async with sess.post(
                        url,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        if resp.status in (429, 500, 502, 503, 504) and attempt == 0:
                            await asyncio.sleep(0.5)
                            continue
                        if resp.status != 200:
                            return None
                        body = await resp.json()
            except Exception:
                if attempt == 0:
                    await asyncio.sleep(0.5)
                    continue
                return None

            result = body.get("result")
            if not result:
                return None
            return _shape_getparsed_as_helius(result, event)
        return None

    # ─── Broadcasting ────────────────────────────────────────────────────

    async def _broadcast(self, tx: dict[str, Any]) -> None:
        await self._stream_hub.publish(TOPIC, {
            "signature": tx.get("signature"),
            "wallet_address": tx.get("wallet_address", ""),
            "wallet_label": tx.get("wallet_label"),
            "token_address": tx.get("token_address", ""),
            "token_symbol": tx.get("token_symbol", "???"),
            "token_name": tx.get("token_name", "Unknown"),
            "direction": "inflow" if tx.get("type", "buy") == "buy" else "outflow",
            "amount_usd": float(tx.get("amount_usd", 0)),
            "amount_tokens": float(tx.get("amount_tokens", 0)),
            "price_usd": float(tx.get("price_usd", 0)),
            "dex_name": tx.get("dex_name", "Unknown"),
            "timestamp": tx.get("timestamp", ""),
            "chain": "solana",
        })

    # ─── Reconnect backfill ──────────────────────────────────────────────

    async def _backfill_from_last_seen(self) -> None:
        """Enrich missed signatures since last-seen per DEX. Runs on reconnect."""
        if not self._solana_client:
            return
        logger.info("Whale stream backfilling %d DEXes since last seen sig", len(self._last_sig))
        try:
            async with SolanaClient(
                rpc_url=settings.solana_rpc_url,
                helius_api_key=settings.helius_api_key,
            ) as client:
                # Use the existing polled-history path for a bounded backfill.
                transactions = await client.get_recent_large_transactions(
                    min_amount_usd=settings.min_whale_usd,
                    limit=100,
                )
            if not transactions:
                return
            fresh = [t for t in transactions if t.get("signature") not in self._seen_sigs]
            for t in fresh:
                sig = t.get("signature")
                if sig:
                    self._remember_sig(sig)
            if not fresh:
                return
            new_sigs = await self._db.insert_whale_transactions(fresh)
            new_sig_set = set(new_sigs or [])
            for t in fresh:
                if t.get("signature") in new_sig_set:
                    await self._broadcast(t)
            logger.info("Whale stream backfill: %d new transactions persisted", len(new_sig_set))
        except Exception as e:
            logger.warning("Whale stream backfill failed: %s", e)

    # ─── Audit loop ──────────────────────────────────────────────────────

    async def _audit_loop(self) -> None:
        """Periodically sample parsed-tx endpoint for Jupiter to detect decoder drift."""
        while True:
            try:
                await asyncio.sleep(_AUDIT_INTERVAL_SECONDS)
                await self._audit_once()
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.debug("Whale stream audit failed: %s", e)

    async def _audit_once(self) -> None:
        if not settings.helius_api_key:
            return
        program_id = DEX_PROGRAM_IDS["Jupiter"]
        url = (
            f"https://api.helius.xyz/v0/addresses/{program_id}/transactions"
            f"?api-key={settings.helius_api_key}&type=SWAP&limit=20"
        )
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        return
                    data = await resp.json()
        except Exception:
            return

        if not isinstance(data, list):
            return

        misses = 0
        for tx in data:
            sig = tx.get("signature")
            if sig and sig not in self._seen_sigs:
                misses += 1
        if misses:
            logger.warning("Whale stream audit: %d/%d recent Jupiter swaps not in stream dedup", misses, len(data))


# ─── Helper: re-shape getTransaction into Helius-enhanced shape ─────────────


def _shape_getparsed_as_helius(rpc_result: dict, event: SwapEvent) -> dict:
    """Convert a getTransaction(jsonParsed) result into the dict shape expected
    by SolanaClient._parse_helius_transaction.

    Required fields on the output: signature, timestamp, tokenTransfers[],
    nativeTransfers[], source.
    """
    block_time = rpc_result.get("blockTime") or event.block_time or 0
    meta = rpc_result.get("meta") or {}
    tx = rpc_result.get("transaction") or {}
    msg = tx.get("message") or {}
    account_keys_raw = msg.get("accountKeys") or []

    def _key_str(k):
        if isinstance(k, str):
            return k
        if isinstance(k, dict):
            return k.get("pubkey") or ""
        return ""

    account_keys = [_key_str(k) for k in account_keys_raw]

    pre_balances = meta.get("preBalances") or []
    post_balances = meta.get("postBalances") or []
    pre_token = meta.get("preTokenBalances") or []
    post_token = meta.get("postTokenBalances") or []

    # Native SOL transfers — diff pre/post balances for each account.
    native_transfers: list[dict] = []
    for idx, key in enumerate(account_keys):
        if idx >= len(pre_balances) or idx >= len(post_balances):
            continue
        delta = int(post_balances[idx]) - int(pre_balances[idx])
        if delta == 0:
            continue
        # Skip the fee payer's fee-only delta to keep noise low — users are
        # typically at idx 0 with a sizable swap delta; this is a heuristic.
        if abs(delta) < 1_000:
            continue
        if delta < 0:
            native_transfers.append({
                "amount": -delta,
                "fromUserAccount": key,
                "toUserAccount": "",
            })
        else:
            native_transfers.append({
                "amount": delta,
                "fromUserAccount": "",
                "toUserAccount": key,
            })

    # Token transfers — pair up pre/post token balances by (account, mint).
    def _token_map(entries):
        out = {}
        for e in entries:
            owner = e.get("owner") or ""
            mint = e.get("mint") or ""
            amt = (e.get("uiTokenAmount") or {}).get("amount")
            decimals = (e.get("uiTokenAmount") or {}).get("decimals") or 0
            try:
                raw = int(amt) if amt is not None else 0
            except Exception:
                raw = 0
            ui = raw / (10 ** decimals) if decimals else raw
            out[(owner, mint)] = ui
        return out

    pre_map = _token_map(pre_token)
    post_map = _token_map(post_token)
    all_keys = set(pre_map.keys()) | set(post_map.keys())

    token_transfers: list[dict] = []
    for key in all_keys:
        owner, mint = key
        delta = post_map.get(key, 0) - pre_map.get(key, 0)
        if delta == 0:
            continue
        if delta < 0:
            token_transfers.append({
                "mint": mint,
                "tokenAmount": -delta,
                "fromUserAccount": owner,
                "toUserAccount": "",
            })
        else:
            token_transfers.append({
                "mint": mint,
                "tokenAmount": delta,
                "fromUserAccount": "",
                "toUserAccount": owner,
            })

    return {
        "signature": event.signature,
        "timestamp": int(block_time) if block_time else 0,
        "type": "SWAP",
        "source": event.dex_name.upper(),
        "tokenTransfers": token_transfers,
        "nativeTransfers": native_transfers,
    }
