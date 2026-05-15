"""Spec §6e — empirical 30-day price-ratio CDF for V3 / CLMM range cards.

The spec requires the in-range probability come from empirical history,
NOT a Gaussian-tanh fit. Real distributions have fat tails on exotic
pairs and step-function-near-1.0 shapes on stable pairs. The synthetic
CDF systematically over-promises stables and under-promises volatiles.

This module fetches 30 days of hourly token-USD prices from DefiLlama
coins/chart, builds price-ratio time series (token0/token1), and emits
the empirical CDF over the same 30-bucket ratio grid the frontend
already consumes. Returns None on data fetch failure so the synthetic
CDF in build_yield_execution_plan stays the safety fallback.

Cache 5 minutes per (sym0, sym1) — the curve is expensive to recompute
hourly and the user's range-slider feedback loop is sub-second.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

# CoinGecko slugs used by DefiLlama for the most common LP tokens.
# Extend conservatively — a missing slug returns synth fallback, not crash.
_COINGECKO_SLUG: dict[str, str] = {
    "ETH": "ethereum", "WETH": "weth",
    "BTC": "bitcoin", "WBTC": "wrapped-bitcoin", "CBBTC": "coinbase-wrapped-btc",
    "SOL": "solana", "WSOL": "wrapped-solana",
    "USDC": "usd-coin", "USDT": "tether", "DAI": "dai", "FRAX": "frax",
    "LUSD": "liquity-usd", "USDS": "usds", "USDE": "ethena-usde",
    "SUSDE": "ethena-staked-usde", "TUSD": "true-usd", "FDUSD": "first-digital-usd",
    "BUSD": "binance-usd", "USDBC": "bridged-usd-coin-base",
    "BNB": "binancecoin", "WBNB": "wbnb",
    "MATIC": "matic-network", "WMATIC": "wmatic", "POL": "matic-network",
    "AVAX": "avalanche-2", "WAVAX": "wrapped-avax",
    "ARB": "arbitrum", "OP": "optimism", "LINK": "chainlink",
    "AERO": "aerodrome-finance", "VELO": "velodrome-finance",
    "CAKE": "pancakeswap-token", "UNI": "uniswap", "CRV": "curve-dao-token",
    "BAL": "balancer", "LDO": "lido-dao", "RDNT": "radiant-capital",
    "AAVE": "aave", "COMP": "compound-governance-token", "MKR": "maker",
    "STETH": "staked-ether", "WSTETH": "wrapped-steth", "RETH": "rocket-pool-eth",
    "SFRXETH": "staked-frax-ether", "FRXETH": "frax-ether", "EZETH": "renzo-restaked-eth",
    "RSETH": "kelp-dao-restaked-eth", "WEETH": "wrapped-eeth", "EETH": "ether-fi-staked-eth",
    "PUFFER": "puffer-finance", "PUFETH": "pufeth", "JLP": "jupiter-perpetuals-liquidity-provider-token",
    "JITOSOL": "jito-staked-sol", "MSOL": "marinade-staked-sol", "INF": "infinity-sol",
    "JTO": "jito-governance-token", "BONK": "bonk", "WIF": "dogwifcoin",
    "JUP": "jupiter-exchange-solana", "PYTH": "pyth-network",
}

_STABLE_SYMBOLS = frozenset({
    "USDC", "USDT", "DAI", "FRAX", "LUSD", "USDS", "TUSD", "BUSD", "FDUSD",
    "USDBC", "USDE", "SDAI", "SUSDE",
})

_CACHE: dict[tuple[str, str], tuple[float, list[dict[str, float]]]] = {}
_CACHE_TTL_S = 300.0  # 5 minutes


def _slug_for(symbol: str) -> str | None:
    return _COINGECKO_SLUG.get(symbol.upper())


async def _fetch_hourly_prices(slugs: list[str], *, span_samples: int = 180, period: str = "4h", timeout_s: float = 6.0) -> dict[str, list[tuple[int, float]]] | None:
    """Return {slug: [(ts_s, usd_price), ...]} for the requested slugs.

    DefiLlama coins/chart caps each request at 500 total data points
    (samples × coins). Default period=4h, span=180 fits 2 coins comfortably
    (360 ≤ 500) and covers 30 days at 4-hour resolution — enough granularity
    for the in-range probability CDF without breaking the API limit.
    """
    coin_keys = ",".join(f"coingecko:{s}" for s in slugs)
    url = (
        f"https://coins.llama.fi/chart/{coin_keys}"
        f"?period={period}&span={span_samples}&searchWidth=600"
    )
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_s)) as sess:
            async with sess.get(url) as resp:
                if resp.status != 200:
                    return None
                body = await resp.json()
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return None
    coins = (body or {}).get("coins") or {}
    out: dict[str, list[tuple[int, float]]] = {}
    for key, entry in coins.items():
        # key is "coingecko:slug"; strip the prefix.
        if ":" in key:
            slug = key.split(":", 1)[1]
        else:
            slug = key
        prices = entry.get("prices") or []
        series: list[tuple[int, float]] = []
        for p in prices:
            try:
                ts = int(p.get("timestamp") or 0)
                px = float(p.get("price") or 0.0)
                if ts > 0 and px > 0:
                    series.append((ts, px))
            except (TypeError, ValueError):
                continue
        if series:
            out[slug] = series
    return out or None


def _align_ratio_series(
    series_a: list[tuple[int, float]],
    series_b: list[tuple[int, float]],
    *,
    bucket_seconds: int = 14_400,
) -> list[float]:
    """Inner-join two timestamp series on `bucket_seconds` buckets, return
    ratio series = price_a / price_b. Default bucket=4 hours matches the
    DefiLlama coins/chart period=4h cadence; pass bucket_seconds=3600 for
    1h cadence. Tolerates ±1 bucket of drift between the two feeds.
    """
    if not series_a or not series_b:
        return []
    b_by_bucket = {ts // bucket_seconds: px for ts, px in series_b}
    ratios: list[float] = []
    for ts_a, px_a in series_a:
        bucket = ts_a // bucket_seconds
        px_b = b_by_bucket.get(bucket)
        if px_b is None:
            px_b = b_by_bucket.get(bucket - 1) or b_by_bucket.get(bucket + 1)
        if px_b and px_b > 0 and px_a > 0:
            ratios.append(px_a / px_b)
    return ratios


def _empirical_cdf_buckets(ratios: list[float]) -> list[dict[str, float]]:
    """Emit the 30-bucket CDF the frontend already consumes (range
    0.4–2.5 of the current ratio). Each bucket's cdf = fraction of
    samples whose normalized ratio ≤ bucket center.
    """
    if not ratios:
        return []
    current = ratios[-1] if ratios[-1] > 0 else (sum(ratios) / len(ratios))
    if current <= 0:
        return []
    normalised = sorted(r / current for r in ratios if r > 0)
    if not normalised:
        return []
    total = len(normalised)
    samples: list[dict[str, float]] = []
    for i in range(30):
        t = i / 29.0
        bucket = 0.4 + (2.5 - 0.4) * t
        # Count of normalised values <= bucket; binary search.
        lo, hi = 0, total
        while lo < hi:
            mid = (lo + hi) // 2
            if normalised[mid] <= bucket:
                lo = mid + 1
            else:
                hi = mid
        cdf = lo / total
        samples.append({"ratio": round(bucket, 4), "cdf": round(cdf, 6)})
    return samples


async def compute_empirical_cdf_30d(sym0: str, sym1: str) -> list[dict[str, float]] | None:
    """Return the empirical 30-day CDF for the (sym0/sym1) ratio.

    Returns None when one of the symbols isn't slug-mapped or DefiLlama
    can't return data — caller falls back to _synth_cdf_30d.
    """
    a = (sym0 or "").upper()
    b = (sym1 or "").upper()
    if not a or not b or a == b:
        return None

    cache_key = (a, b)
    now = time.time()
    cached = _CACHE.get(cache_key)
    if cached and (now - cached[0]) < _CACHE_TTL_S:
        return list(cached[1])

    slug_a = _slug_for(a)
    slug_b = _slug_for(b)
    if not slug_a or not slug_b:
        return None

    try:
        chart = await _fetch_hourly_prices([slug_a, slug_b])
    except Exception:  # noqa: BLE001 — defensive
        return None
    if not chart:
        return None
    series_a = chart.get(slug_a) or []
    series_b = chart.get(slug_b) or []
    if not series_a or not series_b:
        return None

    ratios = _align_ratio_series(series_a, series_b)
    if len(ratios) < 24:  # need at least a day of data
        return None
    cdf = _empirical_cdf_buckets(ratios)
    if not cdf:
        return None

    _CACHE[cache_key] = (now, cdf)
    return list(cdf)


def _synth_cdf_30d_local(sym0: str, sym1: str) -> list[dict[str, float]]:
    """Synthetic fallback — duplicated from build_yield_execution_plan
    so this module is self-contained. Kept in sync intentionally.
    """
    a, b = (sym0 or "").upper(), (sym1 or "").upper()
    if a in _STABLE_SYMBOLS and b in _STABLE_SYMBOLS:
        sigma = 0.003
    elif a in _STABLE_SYMBOLS or b in _STABLE_SYMBOLS:
        sigma = 0.18
    else:
        sigma = 0.30

    samples = []
    for i in range(30):
        t = i / 29.0
        ratio = 0.4 + (2.5 - 0.4) * t
        z = (math.log(ratio)) / sigma
        cdf = 0.5 * (1.0 + math.tanh(z * 0.7978))
        samples.append({"ratio": round(ratio, 4), "cdf": round(cdf, 6)})
    return samples


async def empirical_cdf_or_fallback(sym0: str, sym1: str) -> list[dict[str, float]]:
    """Convenience: empirical CDF if available, synth fallback otherwise.

    This is the function build_yield_execution_plan should call instead
    of `_synth_cdf_30d`. The frontend signature is unchanged.
    """
    try:
        real = await asyncio.wait_for(compute_empirical_cdf_30d(sym0, sym1), timeout=6.0)
    except (asyncio.TimeoutError, Exception):  # noqa: BLE001
        real = None
    if real:
        return real
    return _synth_cdf_30d_local(sym0, sym1)
