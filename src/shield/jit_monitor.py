"""Spec §13 Row 17 — JIT_ATTACK_ADJACENCY mempool monitor.

A "Just-In-Time" (JIT) liquidity attack is a class of MEV where a searcher
front-runs a large incoming swap by minting a tight concentrated-liquidity
position one block before the swap, capturing the bulk of the fee, then
burning the position one block after. The honest LP earns near-zero fees
for the same block; the searcher walks away with most of the rebate.

The Shield monitor here is a *defensive* counterpart: when a user is about
to add or increase an LP position on an EVM pool, we peek the pending-tx
mempool for a same-block swap above a notional threshold (default $100k)
that would route through the *same* pool. If one is detected, we emit a
``JIT_ATTACK_ADJACENCY`` blocker so the runtime can insert a 1-block delay
and re-simulate after the searcher's tx (or the victim swap) lands. By
that point the searcher's mint+burn pair has either fired (in which case
the LP would now be backing a pool with normalized state) or aborted (in
which case there's nothing to dodge).

The implementation is intentionally split into two layers:

  * ``JitMonitor`` — holds the WebSocket subscription and an in-memory
    ring buffer of recently-seen pending swaps with their decoded pool
    target and USD notional. Production deployments inject a real
    ``aiohttp.ClientSession`` / ``websockets`` client; unit tests inject
    a stub that pre-populates the ring buffer.
  * ``check_jit_adjacency`` — the pure, opt-in check the preflight layer
    calls. When ``monitor`` is ``None`` or the monitor hasn't been
    ``start()``-ed, this returns ``None`` silently. This is the
    "fail-soft" contract: a missing monitor must never block a user.

The monitor is keyed by pool address (lowercased hex). Multi-pool routes
(aggregator splits) decode to multiple pool entries — we record each leg
separately so the check sees the worst-case notional per pool.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Spec §6c blocker code. Re-exported so callers can compare without
# pulling in execution.models just for a string literal.
JIT_BLOCKER_CODE = "JIT_ATTACK_ADJACENCY"

# Default threshold above which we consider a same-block swap adjacency a
# JIT-attack risk. The number comes from spec §13 row 17 and matches the
# economic break-even where searcher rebate > gas+slippage on Ethereum
# mainnet at ~30gwei base fee.
DEFAULT_THRESHOLD_USD = 100_000.0

# How long we retain a pending tx in the ring buffer before evicting it.
# 24 seconds covers ~2 Ethereum blocks at 12s; Solana / L2 callers should
# tune via the constructor.
DEFAULT_PENDING_TTL_S = 24.0


def _norm_addr(addr: Optional[str]) -> Optional[str]:
    """Lowercase + 0x-prefix a hex address. Returns None for falsy input."""
    if not addr:
        return None
    s = str(addr).strip().lower()
    if not s:
        return None
    if not s.startswith("0x"):
        s = "0x" + s
    return s


@dataclass
class PendingSwap:
    """A pending swap observed on the mempool socket.

    Attributes
    ----------
    pool_addr:
        Lowercased hex pool address the swap will route through.
    notional_usd:
        Best-effort USD notional of the swap leg. Decoders may estimate
        this from amount_in × spot price, or from amount_out × spot price
        for exact-out swaps. The check uses ``max(legs)``.
    seen_at:
        Unix epoch seconds the monitor decoded the tx. Used for TTL
        eviction so stale rows don't trigger phantom adjacency.
    tx_hash:
        Optional tx hash for audit-log correlation. Not load-bearing for
        the detection logic itself.
    """
    pool_addr: str
    notional_usd: float
    seen_at: float = field(default_factory=time.time)
    tx_hash: Optional[str] = None


class JitMonitor:
    """In-memory pending-tx ring buffer with an optional WS subscription.

    The class is designed so the WebSocket layer is fully optional: a
    test (or a smoke harness) can construct a ``JitMonitor``, mark it
    started, push a few :class:`PendingSwap` rows, and exercise the
    adjacency check without ever touching a network socket.

    Production callers wire ``start()`` to ``aiohttp.ClientSession.ws_connect``
    against an RPC ``newPendingTransactions`` subscription with full-tx
    mode (``["newPendingTransactions", true]``), then decode each tx via
    the chain-specific router ABI to extract ``(pool_addr, notional_usd)``.

    The class is intentionally lightweight — it owns no decoder state of
    its own; the decoder is injected on push so the same monitor can fan
    out across chains.
    """

    def __init__(
        self,
        *,
        pending_ttl_s: float = DEFAULT_PENDING_TTL_S,
        max_pending: int = 4096,
    ) -> None:
        self._pending: list[PendingSwap] = []
        self._pending_ttl_s = float(pending_ttl_s)
        self._max_pending = int(max_pending)
        self._started: bool = False
        self._ws_task: Optional[asyncio.Task[None]] = None
        self._ws_url: Optional[str] = None
        self._stop_evt: asyncio.Event = asyncio.Event()

    # -- lifecycle ----------------------------------------------------------

    async def start(self, rpc_ws_url: Optional[str] = None) -> None:
        """Open the WebSocket subscription and begin buffering pending swaps.

        ``rpc_ws_url`` may be ``None`` in tests / smoke runs — in that case
        the monitor is marked "started" but no network I/O is performed.
        Callers (or fixtures) are expected to populate the ring buffer via
        :meth:`push_pending` directly.
        """
        if self._started:
            return
        self._ws_url = rpc_ws_url
        self._stop_evt.clear()
        self._started = True
        if rpc_ws_url:
            # Production path: spin the WS reader on the running loop. We
            # do not import aiohttp at module scope so this stays safe to
            # import in environments that don't ship the websocket extras.
            try:
                self._ws_task = asyncio.create_task(self._ws_reader_loop(rpc_ws_url))
            except RuntimeError:
                # No running loop — defer task creation; the caller is
                # responsible for scheduling _ws_reader_loop themselves.
                self._ws_task = None
        logger.info(
            "JitMonitor started (url=%s, ttl=%.1fs)",
            "<offline>" if not rpc_ws_url else "ws",
            self._pending_ttl_s,
        )

    async def stop(self) -> None:
        """Tear down the WebSocket subscription and clear buffered state."""
        if not self._started:
            return
        self._stop_evt.set()
        task = self._ws_task
        self._ws_task = None
        if task is not None:
            try:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
            except Exception as exc:  # pragma: no cover — defensive
                logger.debug("JitMonitor stop cancel raised: %s", exc)
        self._pending.clear()
        self._started = False
        logger.info("JitMonitor stopped")

    @property
    def started(self) -> bool:
        return self._started

    # -- ring buffer --------------------------------------------------------

    def push_pending(self, swap: PendingSwap) -> None:
        """Record a freshly-decoded pending swap.

        Called by the WS reader after decoding the raw tx, or by tests
        injecting canned rows. Enforces the ring-buffer cap by dropping
        the oldest entry when full.
        """
        if not self._started:
            # Silently drop — fail-soft contract. We never want a JIT
            # decoder thread to keep buffering after stop().
            return
        if len(self._pending) >= self._max_pending:
            # Evict the oldest. We could use collections.deque for O(1)
            # popleft, but list-pop(0) is fine at our cap (<5k).
            self._pending.pop(0)
        self._pending.append(swap)

    def _evict_stale(self, now: Optional[float] = None) -> None:
        """Drop pending rows older than TTL. Called from the read path."""
        cutoff = (now or time.time()) - self._pending_ttl_s
        if not self._pending:
            return
        # Quick check — if the oldest is fresh, skip the linear scan.
        if self._pending[0].seen_at >= cutoff:
            return
        self._pending = [p for p in self._pending if p.seen_at >= cutoff]

    # -- detection ----------------------------------------------------------

    def get_adjacent_swap_usd(
        self,
        target_pool: str,
        lookahead_blocks: int = 1,  # noqa: ARG002 - reserved for future block-tagging
    ) -> float:
        """Return the max USD notional of any pending swap targeting ``target_pool``.

        ``lookahead_blocks`` is currently a no-op (we treat every buffered
        pending tx as "same-block adjacent" since the ring buffer's TTL
        bounds the window). Reserved for future block-tagged adjacency
        once the decoder stamps block_number on each row.
        """
        if not self._started:
            return 0.0
        target = _norm_addr(target_pool)
        if not target:
            return 0.0
        self._evict_stale()
        best = 0.0
        for swap in self._pending:
            if swap.pool_addr == target and swap.notional_usd > best:
                best = float(swap.notional_usd)
        return best

    # -- WS reader stub -----------------------------------------------------

    async def _ws_reader_loop(self, rpc_ws_url: str) -> None:
        """Production WebSocket reader. Held behind an optional import so
        this module remains import-safe without aiohttp.

        Subscribes to ``newPendingTransactions`` with full-tx mode, decodes
        each tx through the injected decoder, and pushes the result into
        the ring buffer. Reconnects with exponential backoff on socket
        drop; bails when ``stop()`` flips ``_stop_evt``.

        The decode step is intentionally a placeholder — chains differ in
        router ABI shape, and the production caller wires the right
        decoder (Uniswap V3/V4 router, 1inch, 0x, Cowswap, etc.). The
        decoder contract is: given a raw tx dict, return zero or more
        :class:`PendingSwap` rows.
        """
        backoff = 1.0
        while not self._stop_evt.is_set():
            try:
                # Lazy import — keeps the module import-safe in environments
                # without aiohttp installed (test rigs, lambda cold-start).
                import aiohttp  # type: ignore[import-not-found]
            except Exception:
                logger.warning("JitMonitor: aiohttp not available, WS reader idle")
                return
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(rpc_ws_url, heartbeat=20.0) as ws:
                        # Subscribe — full-tx mode means each notification
                        # ships the decoded tx body, not just the hash.
                        await ws.send_json({
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "eth_subscribe",
                            "params": ["newPendingTransactions", True],
                        })
                        backoff = 1.0  # reset on successful connect
                        async for msg in ws:
                            if self._stop_evt.is_set():
                                break
                            if msg.type != aiohttp.WSMsgType.TEXT:
                                continue
                            try:
                                payload = msg.json()
                            except Exception:
                                continue
                            # Decoder is decoupled — production path injects
                            # a chain-specific router decoder via subclass /
                            # composition. The base class is a no-op here.
                            self._on_pending_message(payload)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("JitMonitor WS error: %s (retry in %.1fs)", exc, backoff)
                try:
                    await asyncio.wait_for(self._stop_evt.wait(), timeout=backoff)
                    break  # stop requested during backoff
                except asyncio.TimeoutError:
                    pass
                backoff = min(backoff * 2.0, 60.0)

    def _on_pending_message(self, payload: dict[str, Any]) -> None:
        """Hook for subclasses / decoders. Base class is a no-op so the
        loop is safe to run without a decoder; tests bypass this entirely
        by calling :meth:`push_pending` directly."""
        return None


async def check_jit_adjacency(
    target_pool: str,
    threshold_usd: float = DEFAULT_THRESHOLD_USD,
    monitor: Optional[JitMonitor] = None,
) -> Optional[str]:
    """Return ``JIT_ATTACK_ADJACENCY`` when a same-block swap above the
    threshold is queued against ``target_pool``. Returns ``None`` otherwise.

    Fail-soft contract:
      * ``monitor is None`` → ``None`` (no false positives when the
        monitor isn't wired)
      * ``not monitor.started`` → ``None`` (no false positives before
        ``start()`` has been awaited)
      * ``target_pool`` falsy → ``None``

    Parameters
    ----------
    target_pool:
        The pool the user's LP add/increase will be created against.
        Case-insensitive hex string.
    threshold_usd:
        Minimum same-block swap notional that constitutes a JIT-attack
        adjacency. Defaults to $100k per spec §13 row 17.
    monitor:
        The shared :class:`JitMonitor` instance held by the runtime.
        Optional — when omitted the check is a no-op.
    """
    if monitor is None or not monitor.started:
        return None
    if not target_pool:
        return None
    try:
        notional = monitor.get_adjacent_swap_usd(target_pool)
    except Exception as exc:  # never let a §13 detector crash preflight
        logger.debug("check_jit_adjacency raised: %s", exc)
        return None
    if notional >= float(threshold_usd):
        return JIT_BLOCKER_CODE
    return None


def check_jit_adjacency_sync(
    target_pool: str,
    threshold_usd: float = DEFAULT_THRESHOLD_USD,
    monitor: Optional[JitMonitor] = None,
) -> Optional[str]:
    """Synchronous variant — the ring-buffer read is pure, so the async
    wrapper is mostly cosmetic. Preflight (which runs sync) uses this
    variant to avoid an event-loop dance.
    """
    if monitor is None or not monitor.started:
        return None
    if not target_pool:
        return None
    try:
        notional = monitor.get_adjacent_swap_usd(target_pool)
    except Exception as exc:
        logger.debug("check_jit_adjacency_sync raised: %s", exc)
        return None
    if notional >= float(threshold_usd):
        return JIT_BLOCKER_CODE
    return None
