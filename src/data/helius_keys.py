"""Shared Helius API-key pool with automatic failover.

All Helius consumers in this process — the whale poller, the portfolio scan and
the token-analysis holder lookups — share ONE pool. When a key hits its usage
cap, Helius responds with HTTP 429 and a body like::

    {"error": {"code": -32429, "message": "max usage reached"}}

The consumer that sees the 429 calls :func:`mark_helius_key_exhausted`, which
parks that key for a cooldown and hands back the next key in priority order.
Because the pool is process-wide, one consumer tripping the cap immediately
rotates the key for every other consumer too — the next call any of them makes
picks the new active key.

Usage caps reset monthly, so a parked key won't actually recover within the
cooldown; the cooldown exists only so a *transient* per-second 429 (rate limit,
not the monthly cap) is retried after a short wait. Re-probing a still-capped
key costs at most one wasted request per cooldown window.

Keys come from :pyattr:`src.config.Settings.helius_api_keys` (the
``HELIUS_API_KEYS`` comma-separated env var, falling back to the single
``HELIUS_API_KEY``). To add a new key, append it to ``HELIUS_API_KEYS`` — do
NOT replace the existing one; failover needs more than one key to fail over to.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# How long to skip a key after a MONTHLY-CAP 429 ("max usage reached"). The cap
# only clears on the monthly reset, so a long park avoids hammering a dead key;
# re-probing every 30 min wastes at most one request per parked key.
DEFAULT_COOLDOWN_S = 1800.0

# How long to skip a key after a TRANSIENT per-second rate-limit 429. The key is
# healthy and recovers in seconds, so park it only briefly — just long enough to
# shed load within a burst — then let it serve the next poll normally. (Kept well
# under the 300 s poll interval so a rate-limited key is always back by next poll.)
RATE_LIMIT_COOLDOWN_S = 12.0


def is_cap_exhaustion(status: int, body_text: Optional[str]) -> bool:
    """True if a 429 is the monthly *credit cap* (key dead until reset) rather
    than a transient *per-second rate limit* (key fine in seconds).

    Helius signals the cap on its JSON-RPC endpoints with
    ``{"error":{"code":-32429,"message":"max usage reached"}}``; the enhanced
    REST API's rate-limit 429s carry an empty or generic body. Cap → long
    cooldown; rate limit → short cooldown.
    """
    if status != 429:
        return False
    t = (body_text or "").lower()
    return (
        "max usage" in t
        or "usage limit" in t
        or "monthly" in t
        or "-32429" in t
    )


def _mask(key: Optional[str]) -> str:
    """Render a key for logs without leaking it (e.g. ``a1b2…f9e0``)."""
    if not key:
        return "<none>"
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}…{key[-4:]}"


class HeliusKeyPool:
    """Process-wide rotating pool of Helius API keys.

    Thread-safe (a plain lock guards the small key/cooldown state). Async-safe by
    consequence — the critical sections are synchronous dict/list reads.
    """

    def __init__(self, keys: Optional[List[str]] = None):
        self._lock = threading.Lock()
        self._keys: List[str] = []
        # key -> monotonic timestamp until which the key is considered exhausted.
        self._cooldown_until: Dict[str, float] = {}
        if keys:
            self.set_keys(keys)

    def set_keys(self, keys: List[str]) -> None:
        """Replace the key list (priority order preserved, blanks/dupes dropped)."""
        seen = set()
        clean: List[str] = []
        for raw in keys:
            k = (raw or "").strip()
            if k and k not in seen:
                seen.add(k)
                clean.append(k)
        with self._lock:
            self._keys = clean
            # Forget cooldowns for keys that are no longer configured.
            self._cooldown_until = {
                k: t for k, t in self._cooldown_until.items() if k in seen
            }

    def key_count(self) -> int:
        with self._lock:
            return len(self._keys)

    def all_keys(self) -> List[str]:
        with self._lock:
            return list(self._keys)

    def active(self) -> Optional[str]:
        """Return the first key not in cooldown.

        If every key is cooling (all capped), return the one whose cooldown
        expires soonest — degraded service beats no service, and it lets a key
        recover the moment its window passes.
        """
        now = time.monotonic()
        with self._lock:
            if not self._keys:
                return None
            for k in self._keys:
                if self._cooldown_until.get(k, 0.0) <= now:
                    return k
            return min(self._keys, key=lambda k: self._cooldown_until.get(k, 0.0))

    def mark_exhausted(
        self, key: Optional[str], cooldown_s: float = DEFAULT_COOLDOWN_S
    ) -> Optional[str]:
        """Park ``key`` for ``cooldown_s`` and return the next active key.

        The returned key may equal ``key`` when it is the only one configured
        (single-key setups keep working unchanged — there is nothing to fail
        over to, so the same key is handed back).
        """
        now = time.monotonic()
        with self._lock:
            if key and key in self._keys:
                self._cooldown_until[key] = now + cooldown_s
            keys = list(self._keys)
            cooldown = dict(self._cooldown_until)

        if not keys:
            return None
        nxt: Optional[str] = None
        for k in keys:
            if cooldown.get(k, 0.0) <= now:
                nxt = k
                break
        if nxt is None:
            nxt = min(keys, key=lambda k: cooldown.get(k, 0.0))

        if key and nxt and nxt != key:
            logger.warning(
                "Helius key %s exhausted (429/cap) — failing over to %s",
                _mask(key),
                _mask(nxt),
            )
        elif key:
            logger.warning(
                "Helius key %s exhausted (429/cap) — no alternate key available; "
                "add another to HELIUS_API_KEYS",
                _mask(key),
            )
        return nxt


# --- Process-wide singleton -------------------------------------------------

_pool: Optional[HeliusKeyPool] = None
_pool_lock = threading.Lock()


def get_helius_pool() -> HeliusKeyPool:
    """Return the shared pool, lazily seeded from settings on first use."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                try:
                    from src.config import settings

                    _pool = HeliusKeyPool(settings.helius_api_keys)
                except Exception:  # pragma: no cover - config import guard
                    _pool = HeliusKeyPool([])
    return _pool


def reload_helius_pool() -> HeliusKeyPool:
    """Re-read keys from settings into the existing pool (e.g. after env reload)."""
    from src.config import settings

    pool = get_helius_pool()
    pool.set_keys(settings.helius_api_keys)
    return pool


def get_active_helius_key() -> Optional[str]:
    """The Helius key callers should use right now (None if none configured)."""
    return get_helius_pool().active()


def mark_helius_key_exhausted(
    key: Optional[str], cooldown_s: float = DEFAULT_COOLDOWN_S
) -> Optional[str]:
    """Mark ``key`` exhausted and return the next key to use."""
    return get_helius_pool().mark_exhausted(key, cooldown_s)
