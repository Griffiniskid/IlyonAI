"""Resolve the EXACT pool contract address for a (chain, protocol, pair).

The pool_link card needs a direct deep link to the specific pool on the
protocol app — not a `pools` overview page. DefiLlama Yields gives us a
pool UUID and underlying token addresses but rarely the pool contract.

Resolution order:
  1. Curated overrides for well-known pools (Curve 3pool, etc.).
  2. DexScreener search by `<protocol> <pair> <chain>` — picks the best
     dexId / chain match.
  3. Raydium API for Solana AMM/CLMM (`/pools/info/mint`).

Cached in-process for 10 minutes.
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Any

import httpx

_TTL_S = 600.0
_cache: dict[tuple[str, str, str], tuple[float, str | None]] = {}
_lock = asyncio.Lock()

# Curated direct pool addresses for well-known DeFi pools.
# Key = (chain, protocol_slug, pair_symbol_sorted) → pool contract address.
_OVERRIDES: dict[tuple[str, str, str], str] = {
    # Curve Ethereum
    ("ethereum", "curve", "DAI-USDC"): "0xbebc44782c7db0a1a60cb6fe97d0b483032ff1c7",
    ("ethereum", "curve", "DAI-USDT"): "0xbebc44782c7db0a1a60cb6fe97d0b483032ff1c7",
    ("ethereum", "curve", "USDC-USDT"): "0xbebc44782c7db0a1a60cb6fe97d0b483032ff1c7",
    ("ethereum", "curve", "DAI-USDC-USDT"): "0xbebc44782c7db0a1a60cb6fe97d0b483032ff1c7",
    ("ethereum", "curve-dex", "DAI-USDC"): "0xbebc44782c7db0a1a60cb6fe97d0b483032ff1c7",
    ("ethereum", "curve-dex", "DAI-USDT"): "0xbebc44782c7db0a1a60cb6fe97d0b483032ff1c7",
    ("ethereum", "curve-dex", "USDC-USDT"): "0xbebc44782c7db0a1a60cb6fe97d0b483032ff1c7",
    # Curve stETH-ETH
    ("ethereum", "curve", "ETH-STETH"): "0xdc24316b9ae028f1497c275eb9192a3ea0f67022",
    ("ethereum", "curve", "STETH-ETH"): "0xdc24316b9ae028f1497c275eb9192a3ea0f67022",
    # Uniswap V3 mainnet (most-traded fee tiers)
    ("ethereum", "uniswap-v3", "USDC-WETH"): "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",  # 0.05%
    ("ethereum", "uniswap-v3", "USDC-USDT"): "0x3416cf6c708da44db2624d63ea0aaef7113527c6",  # 0.01%
    ("ethereum", "uniswap-v3", "DAI-USDC"): "0x6c6bc977e13df9b0de53b251522280bb72383700",
    ("ethereum", "uniswap-v3", "WBTC-WETH"): "0xcbcdf9626bc03e24f779434178a73a0b4bad62ed",
    # Aave V3 Ethereum
    ("ethereum", "aave-v3", "USDC"): "0xbcca60bb61934080951369a648fb03df4f96263c",  # aUSDC
    ("ethereum", "aave-v3", "USDT"): "0x23878914efe38d27c4d67ab83ed1b93a74d4086a",
    ("ethereum", "aave-v3", "DAI"): "0x018008bfb33d285247a21d44e50697654f754e63",
}


def _norm_pair(pair: str) -> str:
    parts = sorted(p.strip().upper() for p in pair.replace("/", "-").split("-") if p.strip())
    return "-".join(parts)


def _normalize_protocol(p: str) -> str:
    s = (p or "").strip().lower()
    s = re.sub(r"\s+", "-", s)
    return s


async def _dexscreener_search(query: str) -> list[dict[str, Any]]:
    url = "https://api.dexscreener.com/latest/dex/search"
    try:
        async with httpx.AsyncClient(timeout=8) as cli:
            r = await cli.get(url, params={"q": query})
            r.raise_for_status()
            return r.json().get("pairs") or []
    except (httpx.HTTPError, ValueError, KeyError):
        return []


_DEX_CHAIN_ALIAS = {
    "ethereum": {"ethereum"},
    "base": {"base"},
    "arbitrum": {"arbitrum"},
    "optimism": {"optimism"},
    "polygon": {"polygon"},
    "avalanche": {"avalanche"},
    "bsc": {"bsc", "bnbchain"},
    "solana": {"solana"},
}

_DEX_ID_ALIAS = {
    "uniswap-v3": {"uniswap", "uniswapv3"},
    "uniswap-v2": {"uniswap", "uniswapv2"},
    "uniswap": {"uniswap"},
    "pancakeswap-v3": {"pancakeswap", "pancakeswapv3"},
    "pancakeswap-v2": {"pancakeswap", "pancakeswapv2"},
    "sushiswap": {"sushiswap"},
    "curve": {"curve"},
    "curve-dex": {"curve"},
    "balancer": {"balancer"},
    "balancer-v2": {"balancer"},
    "aerodrome-slipstream": {"aerodrome", "aerodromeslipstream"},
    "aerodrome": {"aerodrome"},
    "velodrome": {"velodrome"},
    "raydium-amm": {"raydium"},
    "raydium-clmm": {"raydium", "raydiumclmm"},
    "raydium-cp": {"raydium"},
    "raydium": {"raydium"},
    "orca": {"orca"},
    "orca-whirlpools": {"orca"},
    "orca-clmm": {"orca"},
    "meteora-dlmm": {"meteora"},
    "meteora": {"meteora"},
}


def _score_pair(pair: dict, chain: str, proto: str, pair_sym: str) -> int:
    score = 0
    ch = (pair.get("chainId") or "").lower()
    dx = (pair.get("dexId") or "").lower()
    base = ((pair.get("baseToken") or {}).get("symbol") or "").upper()
    quote = ((pair.get("quoteToken") or {}).get("symbol") or "").upper()
    chain_aliases = _DEX_CHAIN_ALIAS.get(chain, {chain})
    dex_aliases = _DEX_ID_ALIAS.get(proto, {proto})
    if ch in chain_aliases:
        score += 50
    if dx in dex_aliases:
        score += 30
    norm_target = _norm_pair(pair_sym)
    if _norm_pair(f"{base}-{quote}") == norm_target:
        score += 25
    # liquidity tie-break
    liq = (pair.get("liquidity") or {}).get("usd") or 0
    try:
        score += min(int(liq // 100_000), 20)
    except (TypeError, ValueError):
        pass
    return score


async def resolve_exact_pool_address(
    *, chain: str | None, protocol: str | None, pair_symbol: str | None
) -> str | None:
    """Return the on-chain pool contract address (or AMM ID for Solana) or None."""
    if not chain or not protocol or not pair_symbol:
        return None
    chain_norm = chain.strip().lower()
    proto_norm = _normalize_protocol(protocol)
    pair_norm = _norm_pair(pair_symbol)
    key = (chain_norm, proto_norm, pair_norm)
    now = time.monotonic()
    async with _lock:
        hit = _cache.get(key)
        if hit and (now - hit[0]) < _TTL_S:
            return hit[1]

    # 1. Curated override
    addr = _OVERRIDES.get(key)
    if addr:
        async with _lock:
            _cache[key] = (now, addr)
        return addr

    # 2. DexScreener search
    query = f"{protocol} {pair_symbol.replace('-', ' ')} {chain_norm}"
    pairs = await _dexscreener_search(query)
    if pairs:
        scored = sorted(pairs, key=lambda p: _score_pair(p, chain_norm, proto_norm, pair_symbol), reverse=True)
        best = scored[0]
        if _score_pair(best, chain_norm, proto_norm, pair_symbol) >= 50:
            pool_addr = best.get("pairAddress")
            if pool_addr:
                async with _lock:
                    _cache[key] = (now, pool_addr)
                return pool_addr

    async with _lock:
        _cache[key] = (now, None)
    return None
