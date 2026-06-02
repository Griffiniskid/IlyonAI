"""Authoritative on-chain / protocol-API resolution of a pool's exact address.

DefiLlama gives only a UUID + token mints — never the pool contract address.
To deep-link "Open pool" to the EXACT pool (not the protocol's pools list) we
resolve the real address from the protocol's own truth:

  - EVM AMMs  → the protocol's factory on-chain (deterministic):
                  V3: factory.getPool(t0, t1, fee)
                  V2: factory.getPair(t0, t1)
  - Solana    → the protocol's own API (Orca / Raydium) by token mints.

Returns the address (str) or None. None → caller falls back to DexScreener /
DefiLlama. All network calls are time-bounded.
"""
from __future__ import annotations

import re
from typing import Optional

import aiohttp

_TIMEOUT = aiohttp.ClientTimeout(total=6)
_UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

# Multiple EVM RPCs per chain — public endpoints rate-limit (429) at random,
# so we try them in order until one answers. This is what makes resolution
# reliable without a paid key (a single endpoint silently failing was sending
# pools to the DefiLlama fallback).
_RPCS = {
    "ethereum": ["https://eth.drpc.org", "https://ethereum-rpc.publicnode.com", "https://1rpc.io/eth", "https://rpc.flashbots.net"],
    "arbitrum": ["https://arbitrum-one-rpc.publicnode.com", "https://arb1.arbitrum.io/rpc", "https://arbitrum.drpc.org", "https://1rpc.io/arb"],
    "base": ["https://base-rpc.publicnode.com", "https://mainnet.base.org", "https://base.drpc.org", "https://1rpc.io/base"],
    "optimism": ["https://optimism-rpc.publicnode.com", "https://mainnet.optimism.io", "https://optimism.drpc.org"],
    "polygon": ["https://polygon-bor-rpc.publicnode.com", "https://polygon-rpc.com", "https://polygon.drpc.org"],
    "bsc": ["https://bsc-rpc.publicnode.com", "https://bsc-dataseed.binance.org", "https://bsc-dataseed1.defibit.io", "https://binance.llamarpc.com", "https://bsc.drpc.org"],
    "avalanche": ["https://avalanche-c-chain-rpc.publicnode.com", "https://api.avax.network/ext/bc/C/rpc", "https://avalanche.drpc.org"],
}

# (protocol_head, chain) → (factory_address, kind). kind ∈ {"v3","v2"}.
_FACTORY: dict[tuple[str, str], tuple[str, str]] = {
    # Uniswap V3
    ("uniswap-v3", "ethereum"): ("0x1F98431c8aD98523631AE4a59f267346ea31F984", "v3"),
    ("uniswap-v3", "arbitrum"): ("0x1F98431c8aD98523631AE4a59f267346ea31F984", "v3"),
    ("uniswap-v3", "optimism"): ("0x1F98431c8aD98523631AE4a59f267346ea31F984", "v3"),
    ("uniswap-v3", "polygon"): ("0x1F98431c8aD98523631AE4a59f267346ea31F984", "v3"),
    ("uniswap-v3", "base"): ("0x33128a8fC17869897dcE68Ed026d694621f6FDfD", "v3"),
    ("uniswap-v3", "bsc"): ("0xdB1d10011AD0Ff90774D0C6Bb92e5C5c8b4461F7", "v3"),
    # Uniswap V2
    ("uniswap-v2", "ethereum"): ("0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f", "v2"),
    ("uniswap-v2", "base"): ("0x8909Dc15e40173Ff4699343b6eB8132c65e18eC6", "v2"),
    # SushiSwap
    ("sushiswap", "ethereum"): ("0xC0AEe478e3658e2610c5F7A4A2E1777cE9e4f2Ac", "v2"),
    ("sushiswap", "arbitrum"): ("0xc35DADB65012eC5796536bD9864eD8773aBc74C4", "v2"),
    ("sushiswap-v3", "ethereum"): ("0xbACEB8eC6b9355Dfc0269C18bac9d6E2Bdc29C4F", "v3"),
    # PancakeSwap
    ("pancakeswap-amm", "bsc"): ("0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73", "v2"),
    ("pancakeswap-v2", "bsc"): ("0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73", "v2"),
    ("pancakeswap-v3", "bsc"): ("0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865", "v3"),
    # QuickSwap (polygon, V2)
    ("quickswap", "polygon"): ("0x5757371414417b8C6CAad45bAeF941aBc7d3Ab32", "v2"),
}

# Valid V3 fee tiers (Uniswap: 100/500/3000/10000; PancakeSwap adds 2500).
# Used to validate a caller-supplied fee tier before probing the factory. We
# no longer guess a tier when the fee is unknown — see _evm_factory_pool.
_V3_FEES = frozenset({100, 500, 2500, 3000, 10000})
_ZERO_ADDR = "0x0000000000000000000000000000000000000000"

# Resolved-address cache (process-lifetime). A pool's address never changes.
_CACHE: dict[tuple, str] = {}


def fee_bps_from_meta(meta) -> Optional[int]:
    """Parse a Uniswap/Pancake V3 fee tier from a DefiLlama poolMeta string
    ('0.05%' → 500, '0.3%' → 3000, '1%' → 10000). Returns None when the string
    isn't a recognised fee tier, so callers fall back to DexScreener."""
    if not meta:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", str(meta))
    if not m:
        return None
    try:
        tier = round(float(m.group(1)) * 10000)
    except ValueError:
        return None
    return tier if tier in _V3_FEES else None


def _factory_key(protocol: str) -> str:
    p = (protocol or "").lower().strip()
    # normalise common DefiLlama slugs
    if p == "uniswap":
        return "uniswap-v3"  # bare 'uniswap' → assume v3 (the common case)
    # NOTE: 'uniswap-v4' is intentionally NOT remapped to v3. V4 has no
    # per-pool contract (pools live in the singleton PoolManager, keyed by a
    # poolId hash), so factory getPool can't resolve it and would return an
    # unrelated V3 pool. It falls through; _FACTORY has no v4 entry, so
    # resolution returns None and the caller defers to DexScreener (which does
    # index V4 pairs).
    if p in {"pancakeswap", "pancake", "pancakeswap-amm-v3"}:
        return "pancakeswap-amm"
    if p in {"sushi", "sushiswap-v2"}:
        return "sushiswap"
    return p


def _enc_addr(a: str) -> str:
    return a.lower().replace("0x", "").rjust(64, "0")


async def _raw_call(sess: aiohttp.ClientSession, rpc: str, to: str, data: str):
    """Returns (ok, addr). ok=False → RPC unusable (429/timeout/error), try the
    next one. ok=True → valid response (addr, or None for the zero address =
    'no such pool')."""
    body = {"jsonrpc": "2.0", "id": 1, "method": "eth_call",
            "params": [{"to": to, "data": data}, "latest"]}
    try:
        async with sess.post(rpc, json=body, headers=_UA, timeout=_TIMEOUT) as r:
            if r.status != 200:
                return (False, None)
            d = await r.json()
        if "error" in d:
            return (False, None)
        res = d.get("result")
        if not res or len(res) < 42:
            return (True, None)
        addr = "0x" + res[-40:]
        return (True, None if addr.lower() == _ZERO_ADDR else addr)
    except Exception:
        return (False, None)


async def _eth_call(sess: aiohttp.ClientSession, chain: str, to: str, data: str) -> Optional[str]:
    """Try each RPC for the chain until one gives a valid response."""
    for rpc in _RPCS.get(chain, []):
        ok, addr = await _raw_call(sess, rpc, to, data)
        if ok:
            return addr
    return None


_DEX_BY_CHAIN = {
    "ethereum": "ethereum", "bsc": "bsc", "base": "base", "arbitrum": "arbitrum",
    "polygon": "polygon", "optimism": "optimism", "avalanche": "avalanche",
}

# V3 factories per (protocol-head, chain). getPool(t0,t1,fee) returns the pool
# for a given fee tier — probing the tiers tells us the exact pool address AND
# its fee, deterministically (no DexScreener dependency, reliable for common
# tokens like USDC where the token-pairs endpoint truncates).
_V3_FACTORIES: dict[tuple[str, str], str] = {
    ("pancakeswap", "ethereum"): "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865",
    ("pancakeswap", "bsc"): "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865",
    ("pancakeswap", "base"): "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865",
    ("pancakeswap", "arbitrum"): "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865",
    ("uniswap", "ethereum"): "0x1F98431c8aD98523631AE4a59f267346ea31F984",
    ("uniswap", "arbitrum"): "0x1F98431c8aD98523631AE4a59f267346ea31F984",
    ("uniswap", "optimism"): "0x1F98431c8aD98523631AE4a59f267346ea31F984",
    ("uniswap", "polygon"): "0x1F98431c8aD98523631AE4a59f267346ea31F984",
    ("uniswap", "base"): "0x33128a8fC17869897dcE68Ed026d694621f6FDfD",
    ("uniswap", "bsc"): "0xdB1d10011AD0Ff90774D0C6Bb92e5C5c8b4461F7",
}
_PCS_V3_FEES = [500, 100, 2500, 10000]
_UNI_V3_FEES = [500, 100, 3000, 10000]


async def resolve_v3_factory(
    sess: aiohttp.ClientSession, chain: str | None, protocol: str | None, tokens: list[str] | None
) -> tuple[Optional[str], Optional[int]]:
    """Deterministic V3 resolution: probe the protocol's V3 factory
    getPool(t0,t1,fee) across fee tiers; the first tier with a pool gives the
    exact (address, fee). Order doesn't matter (factory sorts internally).
    Returns (pool_address, fee_bps) — the fee that actually has a pool, so the
    add link never shows 'Not Created'."""
    ch = (chain or "").lower()
    head = (protocol or "").lower().split("-")[0]
    fac = _V3_FACTORIES.get((head, ch))
    toks = [t for t in (tokens or []) if isinstance(t, str) and t.lower().startswith("0x") and len(t) == 42]
    if not fac or len(toks) < 2 or ch not in _RPCS:
        return None, None
    fees = _PCS_V3_FEES if head == "pancakeswap" else _UNI_V3_FEES
    t0, t1 = toks[0], toks[1]
    for fee in fees:
        data = "0x1698ee82" + _enc_addr(t0) + _enc_addr(t1) + hex(fee)[2:].rjust(64, "0")
        addr = await _eth_call(sess, ch, fac, data)
        if addr:
            return addr, fee
    return None, None


async def resolve_v3_pool(
    sess: aiohttp.ClientSession, chain: str | None, protocol: str | None, tokens: list[str] | None
) -> tuple[Optional[str], Optional[int]]:
    """Robust V3 pool resolution: find the EXACT pool address via DexScreener's
    token-pairs endpoint (complete — returns every pair for a token with its
    address + liquidity), then read the fee tier on-chain via pool.fee(). This
    is what makes a correct PancakeSwap/Uniswap V3 add link (right pool, right
    fee) instead of guessing the fee from unreliable metadata. Returns
    (pool_address, fee_bps) — either may be None."""
    ch = (chain or "").lower()
    dch = _DEX_BY_CHAIN.get(ch)
    toks = [t for t in (tokens or []) if isinstance(t, str) and t.lower().startswith("0x") and len(t) == 42]
    if not dch or len(toks) < 2:
        return None, None
    proto_head = (protocol or "").lower().split("-")[0]
    want = {toks[0].lower(), toks[1].lower()}
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{toks[0]}"
        async with sess.get(url, headers=_UA, timeout=_TIMEOUT) as r:
            if r.status != 200:
                return None, None
            data = await r.json()
    except Exception:
        return None, None
    best, best_liq = None, -1.0
    for pr in (data.get("pairs") or []):
        if str(pr.get("chainId", "")).lower() != dch:
            continue
        dex = str(pr.get("dexId", "")).lower()
        if proto_head and proto_head not in dex and dex not in proto_head:
            continue
        base = str((pr.get("baseToken") or {}).get("address", "")).lower()
        quote = str((pr.get("quoteToken") or {}).get("address", "")).lower()
        if {base, quote} != want:
            continue
        try:
            liq = float((pr.get("liquidity") or {}).get("usd") or 0)
        except (TypeError, ValueError):
            liq = 0.0
        if liq > best_liq and pr.get("pairAddress"):
            best_liq, best = liq, pr.get("pairAddress")
    if not best:
        return None, None
    fee = await fee_bps_onchain(sess, chain, best)
    return best, fee


async def fee_bps_onchain(sess: aiohttp.ClientSession, chain: str | None, pool_addr: str | None) -> Optional[int]:
    """Read a V3 pool's fee tier directly from the pool contract — pool.fee()
    (selector 0xddca3f43, returns uint24). The contract is the GROUND TRUTH:
    DefiLlama's fee metadata is frequently wrong, which made the PancakeSwap V3
    add link show '0.01% fee tier · Not Created · Invalid pair'. Returns the
    real tier (e.g. 500), or None if it can't be read."""
    ch = (chain or "").lower()
    if ch not in _RPCS or not (isinstance(pool_addr, str) and pool_addr.lower().startswith("0x")):
        return None
    body = {"jsonrpc": "2.0", "id": 1, "method": "eth_call",
            "params": [{"to": pool_addr, "data": "0xddca3f43"}, "latest"]}
    for rpc in _RPCS.get(ch, []):
        try:
            async with sess.post(rpc, json=body, headers=_UA, timeout=_TIMEOUT) as r:
                if r.status != 200:
                    continue
                d = await r.json()
            if "error" in d:
                continue
            res = d.get("result")
            if res and res not in ("0x", "0x0"):
                fee = int(res, 16)
                if 0 < fee <= 100000:  # sane uint24 fee tier
                    return fee
        except Exception:
            continue
    return None


async def _evm_factory_pool(sess, chain, fkey, tokens, fee_bps=None) -> Optional[str]:
    spec = _FACTORY.get((fkey, chain))
    if not spec or len(tokens) < 2:
        return None
    factory, kind = spec
    if chain not in _RPCS:
        return None
    t0, t1 = tokens[0], tokens[1]
    if kind == "v2":
        # getPair(address,address) selector 0xe6a43905
        data = "0xe6a43905" + _enc_addr(t0) + _enc_addr(t1)
        return await _eth_call(sess, chain, factory, data)
    # v3: getPool(address,address,uint24) selector 0x1698ee82. We resolve ONLY
    # when the exact fee tier is known. A pair like USDC/WETH exists at several
    # tiers (100/500/3000/10000) simultaneously; without the tier we can't tell
    # which pool the caller means, and guessing (e.g. always the lowest tier)
    # sends users to the wrong pool. When the tier is unknown we return None so
    # the caller falls back to DexScreener, which returns the deepest-liquidity
    # (canonical) pool for the pair.
    try:
        fee = int(fee_bps) if fee_bps is not None else None
    except (TypeError, ValueError):
        fee = None
    if fee is None or fee not in _V3_FEES:
        return None
    data = "0x1698ee82" + _enc_addr(t0) + _enc_addr(t1) + hex(fee)[2:].rjust(64, "0")
    return await _eth_call(sess, chain, factory, data)


# Curve MetaRegistry per chain — find_pool_for_coins(a,b) selector 0xa87df06c.
_CURVE_METAREGISTRY = {
    "ethereum": "0xF98B45FA17DE75FB1aD0e7aFD971b0ca00e379fC",
    "arbitrum": "0x13526206545e2DC7CcfBaF28cC631b7d2b2275CF",
    "optimism": "0x9d14C0c4cf6Bf4D14E13bB4D7c2A75f5BdB8C2A0",
    "polygon": "0x47bB542B9dE58b970bA50c9dae444DDB4c16751a",
}


async def _curve_pool(sess, chain, tokens) -> Optional[str]:
    reg = _CURVE_METAREGISTRY.get(chain)
    if not reg or len(tokens) < 2 or chain not in _RPCS:
        return None
    data = "0xa87df06c" + _enc_addr(tokens[0]) + _enc_addr(tokens[1])
    return await _eth_call(sess, chain, reg, data)


async def _orca_pool(sess, tokens) -> Optional[str]:
    if len(tokens) < 2:
        return None
    url = "https://api.orca.so/v2/solana/pools"
    try:
        async with sess.get(url, params={"tokens": f"{tokens[0]},{tokens[1]}"}, headers=_UA, timeout=_TIMEOUT) as r:
            if r.status != 200:
                return None
            d = await r.json()
    except Exception:
        return None
    pools = d.get("data") or []
    # The API ignores ?tokens server-side (returns a broad list), so filter to
    # pools whose BOTH mints match the requested pair, then pick the deepest.
    want = {tokens[0].lower(), tokens[1].lower()}
    best, best_liq = None, -1.0
    for p in pools:
        a = str(p.get("tokenMintA") or "").lower()
        b = str(p.get("tokenMintB") or "").lower()
        if {a, b} != want:
            continue
        try:
            liq = float(p.get("liquidity") or 0)
        except (TypeError, ValueError):
            liq = 0.0
        if liq > best_liq and p.get("address"):
            best_liq, best = liq, p.get("address")
    return best


async def _raydium_pool(sess, tokens) -> Optional[str]:
    if len(tokens) < 2:
        return None
    url = "https://api-v3.raydium.io/pools/info/mint"
    params = {"mint1": tokens[0], "mint2": tokens[1], "poolType": "all",
              "poolSortField": "liquidity", "sortType": "desc", "pageSize": "1", "page": "1"}
    try:
        async with sess.get(url, params=params, headers=_UA, timeout=_TIMEOUT) as r:
            if r.status != 200:
                return None
            d = await r.json()
    except Exception:
        return None
    rows = ((d.get("data") or {}).get("data")) or []
    return rows[0].get("id") if rows and rows[0].get("id") else None


async def resolve_exact_pool_address(
    *,
    protocol: str | None,
    chain: str | None,
    token_addrs: list[str] | None,
    fee_bps: int | None = None,
    sess: aiohttp.ClientSession | None = None,
) -> Optional[str]:
    """Authoritative exact pool address, or None. Token order doesn't matter
    (factories sort internally; the APIs match either order).

    `fee_bps` is the V3 fee tier (e.g. 500 for 0.05%). It is REQUIRED to
    resolve a Uniswap/Pancake V3 pool on-chain — without it we return None and
    the caller falls back to DexScreener (deepest-liquidity pair). It is ignored
    for V2 AMMs, Curve, and Solana protocols (which have a single pool per
    pair / their own API)."""
    toks = [t for t in (token_addrs or []) if isinstance(t, str) and t]
    if len(toks) < 2:
        return None
    c = (chain or "").lower()
    # Cache (consistency + speed): once a pool's exact address is resolved it
    # never changes, so a repeat search returns the same address instantly. The
    # fee tier is part of the key — different tiers are different pools.
    ckey = ((protocol or "").lower(), c, fee_bps, frozenset(t.lower() for t in toks[:4]))
    if ckey in _CACHE:
        return _CACHE[ckey]
    own = sess is None
    if own:
        sess = aiohttp.ClientSession()
    try:
        _result = None
        if c == "solana":
            if "orca" in (protocol or "").lower():
                _result = await _orca_pool(sess, toks)
            elif "raydium" in (protocol or "").lower():
                _result = await _raydium_pool(sess, toks)
        elif "curve" in (protocol or "").lower() or "convex" in (protocol or "").lower():
            _proto_l = (protocol or "").lower()
            if "llamalend" in _proto_l or "lend" in _proto_l:
                # Curve LENDING markets (llamalend) are NOT in the AMM registry.
                # Resolving by token pair returns an UNRELATED AMM pool that
                # merely shares a token (crvUSD/cbBTC → "Yield Basis cbBTC") — a
                # WRONG pool. Don't resolve; the caller links to the protocol app
                # / DefiLlama exact pool instead.
                _result = None
            else:
                _result = await _curve_pool(sess, c, toks)
        else:
            fkey = _factory_key(protocol or "")
            _result = await _evm_factory_pool(sess, c, fkey, toks, fee_bps=fee_bps)
        if _result:
            _CACHE[ckey] = _result
        return _result
    finally:
        if own:
            await sess.close()
