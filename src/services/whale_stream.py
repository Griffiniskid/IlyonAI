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
    is_whale_candidate_raw,
)
from src.data.token_filters import is_alpha_token
from src.platform.stream_hub import get_stream_hub
from src.storage.database import Database

logger = logging.getLogger(__name__)

TOPIC = "whale-transactions"

_DEDUP_SIZE = 10_000
_ENRICH_CONCURRENCY = 8
_RECONNECT_DELAYS = [1.0, 2.0, 5.0, 15.0, 30.0]
_AUDIT_INTERVAL_SECONDS = 3600

# RPC supplement poll: replaces the old 15-min parsed-tx poll. Uses
# getSignaturesForAddress + getTransaction (RPC_CALL budget, not
# TRANSACTION_HISTORY). Cadence is tuned so we comfortably catch every
# whale even on DEXes with no log decoder.
_SUPPLEMENT_POLL_SECONDS = 120  # 2 min
_RPC_SIGNATURES_LIMIT = 100     # per DEX per poll cycle
_RPC_ENRICH_CONCURRENCY = 16    # parallel getTransaction calls during a poll
_TOKEN_META_CACHE_SIZE = 10_000


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
        self._seeded = False  # True after initial backfill has run
        # LRU cache of token_address -> (symbol, name). Populated via DexScreener
        # the first time we see a mint; subsequent whale txs on the same token
        # resolve instantly without an extra HTTP call.
        self._token_meta_cache: OrderedDict[str, tuple[str, str]] = OrderedDict()

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
        cleanup_task = asyncio.create_task(self._cleanup_loop())
        supplement_task = asyncio.create_task(self._supplement_poll_loop())

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
            supplement_task.cancel()
            cleanup_task.cancel()
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

                # Seed DB on first connect so endpoints return data immediately.
                # On reconnect, backfill any missed txs during the outage.
                asyncio.create_task(self._seed_or_backfill())

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

        if event.payment_side is not None:
            # Fully-priced event: USD-filter pre-enrichment (zero RPC cost).
            sol_price = await self._get_sol_price()
            usd = compute_payment_usd(event, sol_price)
            if usd < settings.min_whale_usd:
                return
        else:
            # Amount-only event (pool-based DEX): coarse raw-amount pre-filter.
            # Real USD is computed during enrichment from getTransaction data.
            if not is_whale_candidate_raw(event):
                return
            usd = 0.0

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
            await self._enrich_token_metadata([parsed])

            # Post-enrichment filter: once the real symbol is resolved we can
            # reject bridged majors / stablecoins / LSTs that only show their
            # true identity after DexScreener replies.
            if not is_alpha_token(parsed.get("token_address"), parsed.get("token_symbol")):
                return

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
        return await self._fetch_and_shape_signature(
            signature=event.signature,
            dex_name=event.dex_name,
            block_time_hint=event.block_time,
            session=None,
        )

    async def _fetch_and_shape_signature(
        self,
        signature: str,
        dex_name: str,
        block_time_hint: Optional[int] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> Optional[dict[str, Any]]:
        """Same as _fetch_and_shape but driven by a bare signature.

        Used by both the WS-enrichment path and the RPC poll. If a shared
        aiohttp session is passed, it is reused (saves TLS handshakes during
        a poll cycle).
        """
        url = f"https://mainnet.helius-rpc.com/?api-key={settings.helius_api_key}"
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [
                signature,
                {
                    "encoding": "jsonParsed",
                    "maxSupportedTransactionVersion": 0,
                    "commitment": "confirmed",
                },
            ],
        }

        async def _post(sess: aiohttp.ClientSession) -> Optional[dict[str, Any]]:
            for attempt in range(2):
                try:
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
                return _shape_rpc_result_as_helius(
                    result,
                    signature=signature,
                    dex_name=dex_name,
                    block_time_hint=block_time_hint,
                )
            return None

        if session is not None:
            return await _post(session)
        async with aiohttp.ClientSession() as sess:
            return await _post(sess)

    # ─── DB backfill for legacy '???' rows ──────────────────────────────

    async def _backfill_unresolved_token_symbols(self) -> int:
        """Resolve token_symbol/token_name for existing rows stuck on '???'.

        Runs at startup and periodically via the supplement loop. Uses the
        same DexScreener lookup + LRU cache the live enrichment path uses.
        Returns number of DB rows updated.
        """
        try:
            addresses = await self._db.get_whale_unresolved_token_addresses(limit=500)
        except Exception as e:
            logger.debug("Whale stream backfill: address fetch failed: %s", e)
            return 0
        if not addresses:
            return 0

        # Build a synthetic parsed-tx list so we can reuse the LRU+DexScreener path.
        synthetic = [{"token_address": a, "token_symbol": "???"} for a in addresses]
        await self._enrich_token_metadata(synthetic)

        updated = 0
        for tx in synthetic:
            sym = tx.get("token_symbol", "???")
            if sym and sym != "???":
                try:
                    updated += await self._db.update_whale_token_metadata(
                        token_address=tx["token_address"],
                        symbol=sym,
                        name=tx.get("token_name") or "Unknown",
                    )
                except Exception as e:
                    logger.debug("Whale stream backfill update failed: %s", e)
        if updated:
            logger.info("Whale stream token-meta backfill: updated %d rows", updated)
        return updated

    # ─── Token metadata enrichment ──────────────────────────────────────

    async def _enrich_token_metadata(self, parsed_txs: list[dict[str, Any]]) -> None:
        """Fill in token_symbol/token_name for any tx where they default to '???'.

        The base parser (`_parse_helius_transaction`) only extracts the mint
        address — symbol/name require a separate lookup. We use DexScreener's
        token endpoint because it works for any Solana mint (including new
        pump.fun tokens) and the results are already cached by the stream
        instance's LRU to avoid repeat calls for the same mint.

        Mutates `parsed_txs` in place. Silent on lookup failure — the '???'
        placeholder remains (consistent with the old poller's behavior).
        """
        if not parsed_txs:
            return

        need_lookup: set[str] = set()
        for tx in parsed_txs:
            addr = tx.get("token_address")
            if not addr:
                continue
            if tx.get("token_symbol", "???") != "???":
                continue  # already resolved upstream
            cached = self._token_meta_cache.get(addr)
            if cached is not None:
                # Refresh LRU recency and apply immediately.
                self._token_meta_cache.move_to_end(addr)
                tx["token_symbol"], tx["token_name"] = cached
                continue
            need_lookup.add(addr)

        if not need_lookup:
            return

        try:
            from src.data.dexscreener import DexScreenerClient
            async with DexScreenerClient() as dex:
                results = await asyncio.gather(
                    *(dex.get_token(addr) for addr in need_lookup),
                    return_exceptions=True,
                )
        except Exception as e:
            logger.debug("Whale stream token meta lookup failed: %s", e)
            return

        resolved: dict[str, tuple[str, str]] = {}
        for res in results:
            if not res or isinstance(res, Exception) or not isinstance(res, dict):
                continue
            main = res.get("main") or {}
            base = main.get("baseToken") or {}
            addr = base.get("address")
            if not addr:
                continue
            symbol = base.get("symbol") or "???"
            name = base.get("name") or "Unknown"
            resolved[addr] = (symbol, name)

        for addr, pair in resolved.items():
            self._token_meta_cache[addr] = pair
            self._token_meta_cache.move_to_end(addr)
        while len(self._token_meta_cache) > _TOKEN_META_CACHE_SIZE:
            self._token_meta_cache.popitem(last=False)

        for tx in parsed_txs:
            addr = tx.get("token_address")
            pair = resolved.get(addr) if addr else None
            if pair:
                tx["token_symbol"], tx["token_name"] = pair

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

    # ─── RPC-based polling (no TRANSACTION_HISTORY cost) ───────────────

    async def _rpc_poll_all_dexes(self, source: str) -> int:
        """Poll every DEX program via standard Solana RPC.

        Returns the number of new whale transactions persisted. `source` is a
        label for logs ("seed" | "backfill" | "supplement").
        """
        if not settings.helius_api_key:
            return 0

        sem = asyncio.Semaphore(_RPC_ENRICH_CONCURRENCY)
        total_new = 0
        async with aiohttp.ClientSession() as sess:
            dex_tasks = [
                self._rpc_poll_dex(dex_name, program_id, sess, sem, source)
                for dex_name, program_id in DEX_PROGRAM_IDS.items()
            ]
            results = await asyncio.gather(*dex_tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, int):
                total_new += r
            elif isinstance(r, Exception):
                logger.debug("Whale stream %s DEX poll exception: %s", source, r)
        return total_new

    async def _rpc_poll_dex(
        self,
        dex_name: str,
        program_id: str,
        session: aiohttp.ClientSession,
        enrich_sem: asyncio.Semaphore,
        source: str,
    ) -> int:
        """Poll one DEX: getSignaturesForAddress, enrich new sigs, persist whales.

        Returns count of newly-persisted whale transactions.
        """
        until_sig = self._last_sig.get(dex_name)
        try:
            sigs = await self._get_signatures_for_address(
                session=session,
                address=program_id,
                limit=_RPC_SIGNATURES_LIMIT,
                until=until_sig,
            )
        except Exception as e:
            logger.debug("Whale stream %s getSignatures(%s) failed: %s", source, dex_name, e)
            return 0

        if not sigs:
            return 0

        # Remember the newest signature for next cycle's `until=` pagination.
        # getSignaturesForAddress returns newest first.
        self._last_sig[dex_name] = sigs[0]

        # Drop already-seen sigs before spending RPC on them.
        fresh_sigs = [s for s in sigs if s not in self._seen_sigs]
        if not fresh_sigs:
            return 0

        sol_price = await self._get_sol_price()

        async def _enrich_one(sig: str) -> Optional[dict[str, Any]]:
            async with enrich_sem:
                if sig in self._seen_sigs:
                    return None
                self._remember_sig(sig)
                shaped = await self._fetch_and_shape_signature(
                    signature=sig,
                    dex_name=dex_name,
                    session=session,
                )
                if shaped is None:
                    return None
                try:
                    parsed = await self._solana_client._parse_helius_transaction(
                        shaped,
                        min_amount_usd=settings.min_whale_usd,
                        sol_price=sol_price,
                    )
                except Exception as e:
                    logger.debug("RPC poll parse failed for %s: %s", sig, e)
                    return None
                if parsed is None:
                    return None
                parsed.setdefault("dex_name", dex_name)
                return parsed

        enriched = await asyncio.gather(*(_enrich_one(s) for s in fresh_sigs))
        whales = [tx for tx in enriched if tx]
        if not whales:
            return 0

        await self._enrich_token_metadata(whales)

        # Drop non-alpha tokens once symbols are resolved.
        whales = [
            tx for tx in whales
            if is_alpha_token(tx.get("token_address"), tx.get("token_symbol"))
        ]
        if not whales:
            return 0

        try:
            new_sig_list = await self._db.insert_whale_transactions(whales)
        except Exception as e:
            logger.warning("Whale stream %s DB insert failed for %s: %s", source, dex_name, e)
            return 0

        new_sig_set = set(new_sig_list or [])
        for tx in whales:
            if tx.get("signature") in new_sig_set:
                await self._broadcast(tx)
        return len(new_sig_set)

    async def _get_signatures_for_address(
        self,
        session: aiohttp.ClientSession,
        address: str,
        limit: int = 100,
        until: Optional[str] = None,
    ) -> list[str]:
        """Fetch recent signatures for a program via standard JSON-RPC.

        Returns a list of signature strings (newest first). Failed txs and
        malformed entries are dropped.
        """
        url = f"https://mainnet.helius-rpc.com/?api-key={settings.helius_api_key}"
        params: dict[str, Any] = {
            "limit": max(1, min(limit, 1000)),
            "commitment": "confirmed",
        }
        if until:
            params["until"] = until
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [address, params],
        }
        for attempt in range(2):
            try:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status in (429, 500, 502, 503, 504) and attempt == 0:
                        await asyncio.sleep(0.5)
                        continue
                    if resp.status != 200:
                        return []
                    body = await resp.json()
            except Exception:
                if attempt == 0:
                    await asyncio.sleep(0.5)
                    continue
                return []

            result = body.get("result") or []
            out: list[str] = []
            for entry in result:
                if not isinstance(entry, dict):
                    continue
                if entry.get("err") is not None:
                    continue
                sig = entry.get("signature")
                if isinstance(sig, str) and sig:
                    out.append(sig)
            return out
        return []

    # ─── Seed / Reconnect backfill ──────────────────────────────────────

    async def _seed_or_backfill(self) -> None:
        """Seed DB on first connect or backfill missed txs on reconnect.

        On initial startup the DB may be empty because the stream only captures
        future events. This method polls getSignaturesForAddress +
        getTransaction (RPC_CALL budget) per DEX, filters whales via the same
        parser as the live path, and persists them so the /whales and
        /smart-money endpoints return data immediately.

        Uses standard Solana RPC exclusively — zero TRANSACTION_HISTORY
        credits consumed.
        """
        label = "seed" if not self._seeded else "backfill"
        try:
            # Purge legacy non-alpha rows (stables/BTC/ETH/LSTs) before backfill
            # so existing DB data doesn't show noisy tokens.
            try:
                removed = await self._db.cleanup_non_alpha_whale_transactions()
                if removed:
                    logger.info("Whale stream %s: purged %d non-alpha rows", label, removed)
            except Exception as e:
                logger.debug("Whale stream %s non-alpha cleanup failed: %s", label, e)

            new_count = await self._rpc_poll_all_dexes(source=label)
            logger.info("Whale stream %s: %d new transactions persisted", label, new_count)
            # Resolve any legacy '???' rows so existing DB data shows real symbols.
            await self._backfill_unresolved_token_symbols()
            self._seeded = True
        except Exception as e:
            logger.warning("Whale stream %s failed: %s", label, e)

    # ─── Periodic cleanup ────────────────────────────────────────────────

    async def _cleanup_loop(self) -> None:
        """Periodically remove whale transactions older than 24h."""
        while True:
            try:
                await asyncio.sleep(3600)  # every hour
                deleted = await self._db.cleanup_old_whale_transactions(hours=24)
                if deleted:
                    logger.info("Whale stream cleanup: removed %d old transactions", deleted)
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.debug("Whale stream cleanup failed: %s", e)

    # ─── Supplemental periodic poll ─────────────────────────────────────

    async def _supplement_poll_loop(self) -> None:
        """Periodically poll each DEX via getSignaturesForAddress + getTransaction.

        Catches whales that the WS path misses (DEXes without log decoders,
        decoder drift, brief disconnects). Uses standard Solana RPC only —
        no TRANSACTION_HISTORY credits.

        Cadence is set to 2 minutes with limit=100 per DEX. On high-volume
        DEXes this may miss rows between polls; the real-time WS path covers
        Jupiter + Pump.fun losslessly, so the supplement's job is only to
        surface whales on the remaining DEXes.
        """
        # Wait a bit before first poll — seed backfill already ran at connect.
        await asyncio.sleep(60)
        while True:
            try:
                new_count = await self._rpc_poll_all_dexes(source="supplement")
                if new_count:
                    logger.info("Whale supplement poll: %d new transactions persisted", new_count)
                # Clean up any rows that came in before metadata was resolvable.
                await self._backfill_unresolved_token_symbols()
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.debug("Whale supplement poll failed: %s", e)
            await asyncio.sleep(_SUPPLEMENT_POLL_SECONDS)

    # ─── Audit loop ──────────────────────────────────────────────────────

    async def _audit_loop(self) -> None:
        """Periodically sample Jupiter signatures via standard RPC to detect decoder drift."""
        while True:
            try:
                await asyncio.sleep(_AUDIT_INTERVAL_SECONDS)
                await self._audit_once()
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.debug("Whale stream audit failed: %s", e)

    async def _audit_once(self) -> None:
        """Drift probe: read the latest Jupiter sigs via getSignaturesForAddress
        and warn if any recent ones aren't in our dedup set. Uses RPC_CALL budget."""
        if not settings.helius_api_key:
            return
        program_id = DEX_PROGRAM_IDS["Jupiter"]
        try:
            async with aiohttp.ClientSession() as sess:
                sigs = await self._get_signatures_for_address(
                    session=sess,
                    address=program_id,
                    limit=20,
                )
        except Exception:
            return

        if not sigs:
            return

        misses = sum(1 for s in sigs if s not in self._seen_sigs)
        if misses:
            logger.warning(
                "Whale stream audit: %d/%d recent Jupiter sigs missed by WS decoder",
                misses, len(sigs),
            )


# ─── Helper: re-shape getTransaction into Helius-enhanced shape ─────────────


def _shape_getparsed_as_helius(rpc_result: dict, event: SwapEvent) -> dict:
    """Legacy shim retained for test imports — prefer _shape_rpc_result_as_helius."""
    return _shape_rpc_result_as_helius(
        rpc_result,
        signature=event.signature,
        dex_name=event.dex_name,
        block_time_hint=event.block_time,
    )


def _shape_rpc_result_as_helius(
    rpc_result: dict,
    signature: str,
    dex_name: str,
    block_time_hint: Optional[int] = None,
) -> dict:
    """Convert a getTransaction(jsonParsed) result into the dict shape expected
    by SolanaClient._parse_helius_transaction.

    Required fields on the output: signature, timestamp, tokenTransfers[],
    nativeTransfers[], source.
    """
    block_time = rpc_result.get("blockTime") or block_time_hint or 0
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
        "signature": signature,
        "timestamp": int(block_time) if block_time else 0,
        "type": "SWAP",
        "source": dex_name.upper(),
        "tokenTransfers": token_transfers,
        "nativeTransfers": native_transfers,
    }
