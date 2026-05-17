"""Spec §13 Row 1 — Pyth/Chainlink price-feed staleness preflight.

Many DeFi venues (lending markets, perps, oracle-aware LSTs, peg-bound
stables) quote prices off a Pyth or Chainlink feed. When that feed has not
been pushed on-chain for more than ~60 seconds, a swap/borrow/liquidation
priced against it can transact at a stale mark — the user eats the gap
the moment the next push lands.

This module surfaces the blocker code ``STALE_PRICE_FEED`` whenever any
feed referenced by the plan is older than the configured threshold.

The detectors are intentionally side-effect free and HTTP/RPC-mockable so
the preflight layer can fan out per-feed without dragging in the heavier
adapter graph. Network failures fail-soft (return None) — we never want
the staleness check itself to brick an execution plan.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)


# Default staleness threshold in seconds. Pyth Hermes typically pushes
# every 400ms-2s; Chainlink aggregators heartbeat anywhere from 30m
# (BTC/USD) to 1h+ depending on the deviation threshold, so 60s is the
# right ceiling for the *front-running* / mark-skew risk we care about
# at signing time — not the price-staleness Chainlink heartbeats are
# tuned for. Callers can override per-venue if they need a tighter bound.
STALE_PRICE_FEED_THRESHOLD_SEC: int = 60

# Canonical blocker code surfaced to the execution layer. Pinned here so
# the preflight wiring and the test suite agree on the spelling.
STALE_PRICE_FEED_BLOCKER_CODE: str = "STALE_PRICE_FEED"


def check_feed_age(
    age_seconds: int,
    threshold_sec: int = STALE_PRICE_FEED_THRESHOLD_SEC,
) -> Optional[str]:
    """Return the ``STALE_PRICE_FEED`` blocker code when the feed is older
    than ``threshold_sec`` seconds. Returns ``None`` when the feed is
    fresh enough to sign against.

    This is the leaf comparison every other check_*_age helper funnels
    through, so behavior is uniform across Pyth and Chainlink sources.
    """
    if age_seconds is None:
        return None
    try:
        age = int(age_seconds)
    except (TypeError, ValueError):
        return None
    if age > threshold_sec:
        return STALE_PRICE_FEED_BLOCKER_CODE
    return None


async def check_pyth_age(
    price_id: str,
    http_session: Any,
    hermes_url: str = "https://hermes.pyth.network",
    now_fn=time.time,
) -> Optional[int]:
    """Fetch the latest Pyth Hermes publish_time for ``price_id`` and
    return the age in seconds, or ``None`` if the feed could not be
    resolved. The return is intentionally the *age*, not a blocker code —
    callers feed it through :func:`check_feed_age` so the threshold logic
    stays in one place.

    ``http_session`` is duck-typed against aiohttp.ClientSession so the
    preflight layer can pass its existing pooled session in. Anything
    exposing an async ``get(url)`` context manager returning an object
    with ``.json()`` works (the test suite drops in a tiny stub).
    """
    if not price_id:
        return None
    url = f"{hermes_url.rstrip('/')}/api/latest_price_feeds"
    params = {"ids[]": price_id}
    try:
        async with http_session.get(url, params=params) as resp:
            status = getattr(resp, "status", 200)
            if status != 200:
                logger.debug("pyth hermes returned %s for %s", status, price_id)
                return None
            payload = await resp.json()
    except Exception as exc:  # network errors fail-soft
        logger.debug("pyth hermes fetch failed for %s: %s", price_id, exc)
        return None

    publish_time = _extract_pyth_publish_time(payload)
    if publish_time is None:
        return None
    age = int(now_fn() - publish_time)
    if age < 0:
        # Clock skew or future-stamped payload — treat as fresh.
        return 0
    return age


def _extract_pyth_publish_time(payload: Any) -> Optional[int]:
    """Pyth Hermes wraps publish_time under
    ``[{"price": {"publish_time": <unix_seconds>}, ...}]`` for the v2
    endpoint and ``[{"publish_time": ...}]`` for the legacy shape. We
    accept both so the detector survives the planned Hermes v2 cutover.
    """
    if not payload:
        return None
    if isinstance(payload, dict):
        # The /v2/updates/price/latest shape returns {"parsed": [ ... ]}.
        if "parsed" in payload and isinstance(payload["parsed"], list):
            payload = payload["parsed"]
        else:
            payload = [payload]
    if not isinstance(payload, list) or not payload:
        return None
    first = payload[0]
    if not isinstance(first, dict):
        return None
    price_block = first.get("price")
    if isinstance(price_block, dict) and "publish_time" in price_block:
        try:
            return int(price_block["publish_time"])
        except (TypeError, ValueError):
            return None
    if "publish_time" in first:
        try:
            return int(first["publish_time"])
        except (TypeError, ValueError):
            return None
    return None


async def check_chainlink_age(
    feed_addr: str,
    chain_id: int,
    rpc_client: Any,
    now_fn=time.time,
) -> Optional[int]:
    """Call ``latestRoundData()`` on the Chainlink aggregator at
    ``feed_addr`` and return the age in seconds since ``updatedAt``.
    Returns ``None`` if the call fails or the round payload is missing
    the timestamp.

    ``rpc_client`` is duck-typed against web3.py's AsyncWeb3 — anything
    with an async ``call_function(address, abi, fn_name)`` interface
    works. We deliberately avoid importing web3 here so the preflight
    fan-out stays light.
    """
    if not feed_addr:
        return None
    try:
        result = await rpc_client.call_function(
            address=feed_addr,
            chain_id=chain_id,
            abi=_CHAINLINK_LATEST_ROUND_ABI,
            fn_name="latestRoundData",
        )
    except Exception as exc:
        logger.debug(
            "chainlink latestRoundData failed for %s on chain %s: %s",
            feed_addr, chain_id, exc,
        )
        return None

    updated_at = _extract_chainlink_updated_at(result)
    if updated_at is None:
        return None
    age = int(now_fn() - updated_at)
    if age < 0:
        return 0
    return age


# Minimal ABI fragment — keeps us decoupled from a global ABI registry.
_CHAINLINK_LATEST_ROUND_ABI = [{
    "inputs": [],
    "name": "latestRoundData",
    "outputs": [
        {"internalType": "uint80", "name": "roundId", "type": "uint80"},
        {"internalType": "int256", "name": "answer", "type": "int256"},
        {"internalType": "uint256", "name": "startedAt", "type": "uint256"},
        {"internalType": "uint256", "name": "updatedAt", "type": "uint256"},
        {"internalType": "uint80", "name": "answeredInRound", "type": "uint80"},
    ],
    "stateMutability": "view",
    "type": "function",
}]


def _extract_chainlink_updated_at(result: Any) -> Optional[int]:
    """latestRoundData returns a 5-tuple; updatedAt is index 3. Tolerate
    dict-shaped returns (some RPC wrappers decode by name)."""
    if result is None:
        return None
    if isinstance(result, dict):
        val = result.get("updatedAt") or result.get("updated_at")
        if val is None:
            return None
        try:
            return int(val)
        except (TypeError, ValueError):
            return None
    if isinstance(result, (list, tuple)) and len(result) >= 4:
        try:
            return int(result[3])
        except (TypeError, ValueError):
            return None
    # Last resort — a plain int passed in by a test stub.
    try:
        return int(result)
    except (TypeError, ValueError):
        return None


async def evaluate_feed_age_preflight(
    price_ids: Iterable[str],
    http_session: Any,
    *,
    threshold_sec: int = STALE_PRICE_FEED_THRESHOLD_SEC,
    hermes_url: str = "https://hermes.pyth.network",
    chainlink_feeds: Optional[Iterable[tuple[str, int]]] = None,
    rpc_client: Any = None,
    now_fn=time.time,
) -> list[dict[str, Any]]:
    """Fan out one Pyth Hermes call per ``price_id`` and one Chainlink
    ``latestRoundData`` call per ``(feed_addr, chain_id)`` pair, then
    emit a blocker dict for every feed older than ``threshold_sec``.

    Returns a list of dicts shaped like::

        {"code": "STALE_PRICE_FEED",
         "feed": "<id-or-addr>",
         "source": "pyth"|"chainlink",
         "age_seconds": <int>}

    The preflight layer wraps these into ``ExecutionBlocker`` rows with
    the appropriate ``affected_step_ids`` — keeping this helper
    framework-agnostic so the same fan-out can serve the sidecar and
    plan-builder paths without circular imports.
    """
    blockers: list[dict[str, Any]] = []

    for price_id in price_ids or []:
        age = await check_pyth_age(
            price_id, http_session, hermes_url=hermes_url, now_fn=now_fn,
        )
        if age is None:
            continue
        if check_feed_age(age, threshold_sec) is not None:
            blockers.append({
                "code": STALE_PRICE_FEED_BLOCKER_CODE,
                "feed": price_id,
                "source": "pyth",
                "age_seconds": age,
            })

    if chainlink_feeds and rpc_client is not None:
        for feed_addr, chain_id in chainlink_feeds:
            age = await check_chainlink_age(
                feed_addr, chain_id, rpc_client, now_fn=now_fn,
            )
            if age is None:
                continue
            if check_feed_age(age, threshold_sec) is not None:
                blockers.append({
                    "code": STALE_PRICE_FEED_BLOCKER_CODE,
                    "feed": feed_addr,
                    "source": "chainlink",
                    "chain_id": chain_id,
                    "age_seconds": age,
                })

    return blockers


__all__ = [
    "STALE_PRICE_FEED_THRESHOLD_SEC",
    "STALE_PRICE_FEED_BLOCKER_CODE",
    "check_feed_age",
    "check_pyth_age",
    "check_chainlink_age",
    "evaluate_feed_age_preflight",
]
