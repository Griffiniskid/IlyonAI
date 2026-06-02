"""Resolve a REAL on-chain pool/pair contract address (what users paste from
DexScreener / Etherscan / a protocol UI) into the meta shape
`execute_pool_position` expects.

The pool resolver previously only accepted DefiLlama pool UUIDs or
"protocol pair" strings, so an `0x…` (EVM) or base58 (Solana) pool address
either errored ("pool not found") or fell into a generic search that returned
an unrelated pool. This module closes that gap by looking the address up on
DexScreener (chain + dex + both tokens), returning a DefiLlama-compatible meta
dict so the rest of the execution pipeline is unchanged.
"""
from __future__ import annotations

import re
from typing import Any, Optional

import aiohttp

_EVM_ADDR_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
_BASE58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")

_DEXSCREENER_SEARCH = "https://api.dexscreener.com/latest/dex/search"
_TIMEOUT = aiohttp.ClientTimeout(total=10)
_UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

# DexScreener chainId → canonical chain name used by our adapters. Only chains
# we can actually build for; others resolve but the adapter layer gates them.
_SUPPORTED_CHAINS = {
    "ethereum": "ethereum", "bsc": "bsc", "base": "base", "arbitrum": "arbitrum",
    "polygon": "polygon", "optimism": "optimism", "avalanche": "avalanche",
    "solana": "solana",
}

# DexScreener dexId (+ v2/v3 label) → our protocol slug.
_DEX_TO_PROJECT = {
    "uniswap": {"v3": "uniswap-v3", "v2": "uniswap-v2", None: "uniswap-v3"},
    "pancakeswap": {"v3": "pancakeswap-v3", "v2": "pancakeswap-amm", None: "pancakeswap-amm"},
    "sushiswap": {"v3": "sushiswap-v3", "v2": "sushiswap", None: "sushiswap"},
    "curve": {None: "curve-dex"},
    "balancer": {None: "balancer-v2"},
    "aerodrome": {None: "aerodrome"},
    "velodrome": {None: "velodrome"},
    "camelot": {None: "camelot"},
    "quickswap": {None: "quickswap"},
    "raydium": {None: "raydium-amm"},
    "orca": {None: "orca-dex"},
    "meteora": {None: "meteora-dlmm"},
}


def looks_like_onchain_pool_address(value: str) -> bool:
    """True for an `0x…40hex` EVM address or a base58 Solana pubkey — and NOT a
    DefiLlama UUID (those are routed by the existing path)."""
    if not isinstance(value, str):
        return False
    s = value.strip()
    if _EVM_ADDR_RE.match(s):
        return True
    # Base58 pubkey, but exclude anything containing a hyphen (UUID / protocol-pair).
    if "-" not in s and " " not in s and _BASE58_RE.match(s):
        return True
    return False


def _map_project(dex_id: str, labels: Optional[list]) -> str:
    dex = (dex_id or "").lower()
    label = None
    for lab in (labels or []):
        ll = str(lab).lower()
        if ll in ("v2", "v3", "v4"):
            label = ll
            break
    table = _DEX_TO_PROJECT.get(dex)
    if not table:
        return dex or "unknown"
    return table.get(label) or table.get(None) or dex


async def resolve_pool_address(address: str, chain_hint: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Resolve a pool/pair contract address → DefiLlama-compatible meta dict, or
    None when DexScreener has no record. Picks the EXACT-address match on a
    supported chain with the deepest liquidity (so the same address deployed on
    an unsupported fork — e.g. PulseChain — doesn't win)."""
    addr = (address or "").strip()
    if not looks_like_onchain_pool_address(addr):
        return None
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as sess:
            async with sess.get(_DEXSCREENER_SEARCH, params={"q": addr}, headers=_UA) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
    except Exception:
        return None

    pairs = data.get("pairs") or []
    if not pairs:
        return None

    # Prefer pairs whose pairAddress matches the queried address exactly.
    exact = [p for p in pairs if str(p.get("pairAddress", "")).lower() == addr.lower()]
    candidates = exact or pairs
    # Keep only chains we support.
    supported = [p for p in candidates if str(p.get("chainId", "")).lower() in _SUPPORTED_CHAINS]
    candidates = supported or candidates
    # Honor an explicit chain hint when it produces a match.
    if chain_hint:
        ch = chain_hint.lower()
        hinted = [p for p in candidates if str(p.get("chainId", "")).lower() == ch]
        if hinted:
            candidates = hinted

    def _liq(p: dict) -> float:
        try:
            return float((p.get("liquidity") or {}).get("usd") or 0)
        except (TypeError, ValueError):
            return 0.0

    best = max(candidates, key=_liq)
    chain_id = str(best.get("chainId", "")).lower()
    chain = _SUPPORTED_CHAINS.get(chain_id, chain_id)
    project = _map_project(best.get("dexId"), best.get("labels"))
    base = best.get("baseToken") or {}
    quote = best.get("quoteToken") or {}
    underlying = [a for a in (base.get("address"), quote.get("address")) if a]
    symbol = "-".join(s for s in (base.get("symbol"), quote.get("symbol")) if s)

    return {
        "chain": chain,
        "project": project,
        "symbol": symbol or addr[:10],
        "underlyingTokens": underlying,
        "pool": addr,
        "pool_address": addr,
        "tvlUsd": _liq(best),
        "apy": None,
        "source": "dexscreener_address",
    }
