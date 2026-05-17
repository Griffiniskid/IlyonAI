"""
Merkl rewards live pricing client (V7-034).

Merkl (https://merkl.angle.money) distributes liquidity-mining rewards on
top of pools across many chains. This client fetches opportunity-level
reward token data and prices each reward token via DefiLlama's coins API
(falling back gracefully when unpriced).

Public surface:
    - fetch_merkl_rewards(chain_id, pool_addr, http_session)
    - price_reward_token(token_addr, chain_id, http_session)
    - compute_merkl_apr(chain_id, pool_addr, tvl_usd, http_session)

All HTTP I/O is delegated to the caller-provided aiohttp session so tests
can mock at the session level. No global state, no module-level cache —
the caller owns rate-limiting and freshness.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MERKL_BASE_URL = "https://api.merkl.xyz/v3"
DEFILLAMA_COINS_URL = "https://coins.llama.fi"

# DefiLlama chain slug map for the `chain:address` price-key.
# Mirrors src.data.defillama mapping but keyed by raw EVM chainId
# so callers don't need to import ChainType here.
_DEFILLAMA_CHAIN_SLUG_BY_ID: Dict[int, str] = {
    1: "ethereum",
    10: "optimism",
    56: "bsc",
    100: "xdai",
    137: "polygon",
    250: "fantom",
    324: "era",
    1101: "polygon_zkevm",
    8453: "base",
    42161: "arbitrum",
    43114: "avax",
    59144: "linea",
    534352: "scroll",
    81457: "blast",
}

_HTTP_TIMEOUT_SECS = 10.0


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Coerce arbitrary JSON value to float, returning default on failure."""
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


async def _get_json(http_session: Any, url: str, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
    """GET and decode JSON, returning None on any failure.

    Accepts any object that exposes an aiohttp-compatible `.get()` async
    context manager — keeps the function trivially mockable in tests.
    """
    try:
        async with http_session.get(url, params=params, timeout=_HTTP_TIMEOUT_SECS) as resp:
            status = getattr(resp, "status", 200)
            if status != 200:
                logger.debug("merkl_client: %s returned status=%s", url, status)
                return None
            return await resp.json()
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("merkl_client: GET %s failed: %s", url, exc)
        return None


async def fetch_merkl_rewards(
    chain_id: int,
    pool_addr: str,
    http_session: Any,
) -> List[Dict[str, Any]]:
    """Fetch active Merkl reward streams for a pool.

    Returns a list of reward dicts shaped:
        {
          "token_addr":          "0x...",
          "token_symbol":        "ARB",
          "apr_pct":             3.42,             # APR from Merkl, may be 0
          "daily_token_amount":  123.456,          # tokens distributed per day
          "price_usd":           None,             # filled later via DefiLlama
        }

    Merkl's `/opportunity` endpoint returns one or more opportunities for
    the queried pool. Each opportunity carries a `rewardsRecord.breakdowns`
    list (newer schema) and / or a top-level `aprRecord.cumulated`. We
    normalize across both shapes so the caller doesn't need to know.
    """
    if not pool_addr:
        return []

    url = f"{MERKL_BASE_URL}/opportunity"
    params = {"chainId": chain_id, "pool": pool_addr.lower()}

    payload = await _get_json(http_session, url, params=params)
    if not payload:
        return []

    # Merkl returns either a dict keyed by opportunity-id or a bare list.
    if isinstance(payload, dict):
        opportunities: List[Dict[str, Any]] = list(payload.values())
    elif isinstance(payload, list):
        opportunities = payload
    else:
        return []

    rewards: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for opp in opportunities:
        if not isinstance(opp, dict):
            continue

        breakdowns = (
            (opp.get("rewardsRecord") or {}).get("breakdowns")
            or opp.get("rewardTokens")
            or opp.get("rewards")
            or []
        )
        opp_apr = _safe_float(opp.get("apr"))

        for b in breakdowns:
            if not isinstance(b, dict):
                continue
            token = b.get("token") or {}
            token_addr = (
                b.get("token_addr")
                or token.get("address")
                or b.get("address")
                or ""
            )
            if not token_addr:
                continue
            key = token_addr.lower()
            if key in seen:
                continue
            seen.add(key)

            symbol = (
                b.get("token_symbol")
                or token.get("symbol")
                or b.get("symbol")
                or ""
            )
            apr_pct = _safe_float(b.get("apr"), default=opp_apr)
            daily_amt = _safe_float(
                b.get("dailyRewards")
                or b.get("daily_token_amount")
                or b.get("amount")
            )

            rewards.append({
                "token_addr": token_addr,
                "token_symbol": symbol,
                "apr_pct": apr_pct,
                "daily_token_amount": daily_amt,
                "price_usd": None,
            })

    return rewards


async def price_reward_token(
    token_addr: str,
    chain_id: int,
    http_session: Any,
) -> Optional[float]:
    """Return USD spot price for a reward token via DefiLlama, or None.

    Uses `/prices/current/{chain}:{addr}` which is rate-limit-free and
    serves the vast majority of EVM reward tokens. Chains without a slug
    mapping return None (caller decides whether to skip or fall back).
    """
    if not token_addr:
        return None
    slug = _DEFILLAMA_CHAIN_SLUG_BY_ID.get(chain_id)
    if not slug:
        return None

    key = f"{slug}:{token_addr.lower()}"
    url = f"{DEFILLAMA_COINS_URL}/prices/current/{key}"

    payload = await _get_json(http_session, url)
    if not isinstance(payload, dict):
        return None

    coins = payload.get("coins") or {}
    entry = coins.get(key) or {}
    price = entry.get("price")
    if price is None:
        return None
    out = _safe_float(price, default=0.0)
    return out if out > 0 else None


async def compute_merkl_apr(
    chain_id: int,
    pool_addr: str,
    tvl_usd: float,
    http_session: Any,
) -> float:
    """Compute live Merkl APR (%) for a pool.

    APR = sum(daily_token_amount * price_usd) * 365 / tvl_usd * 100

    Falls back to Merkl-reported `apr_pct` per reward when:
      - DefiLlama has no price for the reward token, OR
      - tvl_usd <= 0 (cannot annualize)

    Returns 0.0 when there are no rewards or no usable signal.
    """
    rewards = await fetch_merkl_rewards(chain_id, pool_addr, http_session)
    if not rewards:
        return 0.0

    total_daily_usd = 0.0
    fallback_apr = 0.0
    priced_any = False

    for r in rewards:
        price = await price_reward_token(r["token_addr"], chain_id, http_session)
        if price is not None and r["daily_token_amount"] > 0:
            r["price_usd"] = price
            total_daily_usd += r["daily_token_amount"] * price
            priced_any = True
        else:
            # Couldn't price it — fall back to Merkl's own APR figure.
            fallback_apr += _safe_float(r.get("apr_pct"))

    if priced_any and tvl_usd > 0:
        live_apr = (total_daily_usd * 365.0 / tvl_usd) * 100.0
        return live_apr + fallback_apr

    return fallback_apr
