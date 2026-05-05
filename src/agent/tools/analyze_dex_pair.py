"""DexScreener pair analysis — handles addresses pasted from DexScreener
that are actually *pair* addresses (not token mints). Probes DexScreener
first; if the address is a real pair, surfaces a Sentinel-grade pool
report. If it's a mint, delegates to analyze_token_full_sentinel.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any, Optional
from uuid import uuid4

import aiohttp

from src.agent.tools._base import err_envelope, ok_envelope


_DEXS_PAIR_URL = "https://api.dexscreener.com/latest/dex/pairs/{chain}/{address}"
_DEXS_TOKENS_URL = "https://api.dexscreener.com/latest/dex/tokens/{address}"
_TIMEOUT = aiohttp.ClientTimeout(total=12)
_BASE58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
_HEX_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


def _looks_solana(addr: str) -> bool:
    return bool(_BASE58_RE.match(addr or ""))


def _looks_evm(addr: str) -> bool:
    return bool(_HEX_RE.match(addr or ""))


async def _probe_pair(chain: str, addr: str) -> Optional[dict[str, Any]]:
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as sess:
            async with sess.get(_DEXS_PAIR_URL.format(chain=chain, address=addr)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                pairs = data.get("pairs") or data.get("pair")
                if isinstance(pairs, list) and pairs:
                    return pairs[0]
                if isinstance(pairs, dict):
                    return pairs
                return None
    except Exception:
        return None


async def _probe_tokens(addr: str) -> Optional[list[dict[str, Any]]]:
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as sess:
            async with sess.get(_DEXS_TOKENS_URL.format(address=addr)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                pairs = data.get("pairs")
                if isinstance(pairs, list) and pairs:
                    return pairs
                return None
    except Exception:
        return None


async def analyze_dex_pair(
    ctx,
    *,
    address: str,
    chain: str | None = None,
):
    """Auto-route a pasted address to pair-or-token analysis.

    1. Probe DexScreener `pairs` endpoint with the explicit chain (or
       solana/ethereum/bsc/polygon/base/arbitrum).
    2. If pair found, return a sentinel_pool_report card with live data.
    3. Else fall through to analyze_token_full_sentinel.
    """
    if not address:
        return err_envelope("missing_address", "Pass a pair or token address.")
    addr = str(address).strip()
    chains_to_try: list[str] = []
    if chain:
        chains_to_try.append(chain.lower())
    elif _looks_solana(addr):
        chains_to_try = ["solana"]
    elif _looks_evm(addr):
        chains_to_try = ["ethereum", "base", "arbitrum", "bsc", "polygon", "optimism", "avalanche"]
    else:
        return err_envelope("invalid_address", "Address format not recognised.")

    pair = None
    for c in chains_to_try:
        pair = await _probe_pair(c, addr)
        if pair:
            break

    if not pair:
        # Maybe user pasted a mint that has DexScreener pair entries.
        token_pairs = await _probe_tokens(addr)
        if token_pairs:
            pair = token_pairs[0]

    if not pair:
        # Not a pair — fall through to token analyzer.
        from src.agent.tools.sentinel_features import analyze_token_full_sentinel
        return await analyze_token_full_sentinel(
            ctx,
            address=addr,
            chain=chain or ("solana" if _looks_solana(addr) else "ethereum"),
        )

    base = pair.get("baseToken") or {}
    quote = pair.get("quoteToken") or {}
    symbol = f"{(base.get('symbol') or '?').upper()}-{(quote.get('symbol') or '?').upper()}"
    chain_id = (pair.get("chainId") or "").lower()
    dex_id = pair.get("dexId") or ""
    liquidity_usd = (pair.get("liquidity") or {}).get("usd") if isinstance(pair.get("liquidity"), dict) else None
    volume_24h = (pair.get("volume") or {}).get("h24") if isinstance(pair.get("volume"), dict) else None
    price_change = (pair.get("priceChange") or {}).get("h24") if isinstance(pair.get("priceChange"), dict) else None
    price_usd = pair.get("priceUsd")
    fdv = pair.get("fdv")

    payload = {
        "pool_id": pair.get("pairAddress") or addr,
        "protocol": dex_id or "dex",
        "symbol": symbol,
        "chain": chain_id or chain or "?",
        "apy": None,
        "apy_base": None,
        "apy_reward": None,
        "tvl_usd": float(liquidity_usd) if liquidity_usd is not None else None,
        "volume_24h_usd": float(volume_24h) if volume_24h is not None else None,
        "il_risk": None,
        "predicted_class": None,
        "underlying_tokens": [base.get("address") or "", quote.get("address") or ""],
        "links": [
            {"label": "DexScreener pair", "url": pair.get("url") or f"https://dexscreener.com/{chain_id}/{addr}"},
            {"label": f"{base.get('symbol','?')} on {chain_id}", "url": f"https://dexscreener.com/{chain_id}/{base.get('address','')}"},
        ],
        "price_usd": float(price_usd) if price_usd else None,
        "fdv_usd": float(fdv) if fdv else None,
        "price_change_24h": float(price_change) if price_change is not None else None,
    }
    return ok_envelope(
        data={"pair": pair, "address": addr, "chain": chain_id},
        card_type="sentinel_pool_report",
        card_payload=payload,
    )
