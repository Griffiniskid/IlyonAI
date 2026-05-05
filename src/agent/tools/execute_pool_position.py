"""One-click pool deposit: resolve a DefiLlama pool / protocol-pair into an
ExecutionPlanV3 the user signs in Phantom or MetaMask.

Bridges the gap between `search_defi_opportunities` (which lists pools) and
`build_yield_execution_plan` (which needs structured chain/protocol/action
inputs). The user can say "execute raydium-amm SPACEX-WSOL" or
"execute pool deaaa953-89d8-4c41-ac65-b354ff9d57d1" and this tool figures out
the rest.
"""
from __future__ import annotations

import asyncio
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

import aiohttp

from src.agent.tools._base import err_envelope, ok_envelope
from src.agent.tools.build_yield_execution_plan import build_yield_execution_plan


_DEFILLAMA_POOL_URL = "https://yields.llama.fi/pool/{pool_id}"
_DEFILLAMA_POOLS_URL = "https://yields.llama.fi/pools"
_LLAMA_TIMEOUT = aiohttp.ClientTimeout(total=15)
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_BASE58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def _is_solana_pubkey(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    s = value.strip()
    if s.startswith("0x"):
        return False
    return bool(_BASE58_RE.match(s))


def _coerce_amount(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(0)


def _looks_like_pool_id(value: str) -> bool:
    return bool(_UUID_RE.match(value.strip()))


async def _fetch_pool_meta(pool_id: str) -> Optional[dict[str, Any]]:
    """DefiLlama doesn't have a single-pool endpoint; we hit /pools and filter.
    Cached by adapter, so fine for one-off lookups.
    """
    async with aiohttp.ClientSession(timeout=_LLAMA_TIMEOUT) as sess:
        async with sess.get(_DEFILLAMA_POOLS_URL) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            for entry in data.get("data") or []:
                if str(entry.get("pool", "")).lower() == pool_id.lower():
                    return entry
    return None


async def _resolve_protocol_pair(
    protocol: str,
    pair: str,
    chain: Optional[str],
) -> Optional[dict[str, Any]]:
    """Find first DefiLlama pool whose project matches protocol AND symbol matches pair.

    Used for natural-language lookups like "raydium-amm SPACEX-WSOL".
    """
    proto_norm = protocol.lower().replace("_", "-").strip()
    pair_norm = pair.upper().replace("/", "-").replace("_", "-").strip()
    chain_norm = chain.lower() if chain else None
    looks_like_pair = bool(proto_norm) and "-" in proto_norm and proto_norm.replace("-", "").isupper()
    proto_filter_active = bool(proto_norm) and not looks_like_pair
    # When no protocol hint and no chain hint, bias toward chains we have
    # adapters for, in priority order. Avoids resolving 'USDC-WSOL' to
    # cetus-clmm on Sui when Orca/Raydium on Solana are the right hits.
    SUPPORTED_CHAIN_BIAS = {
        "solana": 1.4,
        "ethereum": 1.3,
        "polygon": 1.2,
        "arbitrum": 1.2,
        "base": 1.2,
        "optimism": 1.1,
        "bsc": 1.05,
        "avalanche": 1.0,
    }
    # Protocol-implied chain when not given.
    SOLANA_PROTOS = {"raydium", "orca", "meteora", "kamino", "marinade", "jito", "sanctum", "drift", "lulo"}
    EVM_PROTOS = {"aave", "compound", "yearn", "lido", "rocket-pool", "ether.fi", "morpho", "spark", "curve", "convex", "pendle", "stargate", "frax"}
    if not chain_norm and proto_norm:
        head = proto_norm.split("-")[0]
        if head in SOLANA_PROTOS:
            chain_norm = "solana"
        elif head in EVM_PROTOS:
            pass
    async with aiohttp.ClientSession(timeout=_LLAMA_TIMEOUT) as sess:
        async with sess.get(_DEFILLAMA_POOLS_URL) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            best: Optional[dict[str, Any]] = None
            best_tvl = -1.0
            for entry in data.get("data") or []:
                project = str(entry.get("project", "")).lower()
                symbol = str(entry.get("symbol", "")).upper().replace("/", "-")
                ec = str(entry.get("chain", "")).lower()
                if proto_filter_active and proto_norm not in project and project not in proto_norm:
                    continue
                if chain_norm and chain_norm not in ec:
                    continue
                if pair_norm and pair_norm not in symbol:
                    continue
                tvl = float(entry.get("tvlUsd") or 0)
                bias = SUPPORTED_CHAIN_BIAS.get(ec, 0.7)
                score = tvl * bias
                if score > best_tvl:
                    best = entry
                    best_tvl = score
            return best


def _split_protocol_pair(arg: str) -> tuple[str, str]:
    """Accept 'raydium-amm · SPACEX-WSOL', 'raydium-amm SPACEX-WSOL',
    'raydium-amm/SPACEX-WSOL', or a bare 'SPACEX-WSOL' pair.
    """
    cleaned = arg.replace("·", " ").replace("|", " ").strip()
    parts = [p for p in re.split(r"\s+", cleaned) if p]
    if len(parts) == 0:
        return "", ""
    if len(parts) == 1:
        only = parts[0]
        # If it has a separator it's already a pair; treat protocol as empty.
        if any(sep in only for sep in ("-", "/", "_")) and only.isupper():
            return "", only
        return only, ""
    # If first chunk hyphenated like "raydium-amm" keep it intact.
    return parts[0], parts[-1]


def _pick_asset_in(meta: dict[str, Any]) -> str:
    """Pick a sensible asset to deposit. Prefer USDC when present, else first
    underlying token, else the symbol's first leg.
    """
    underlying = meta.get("underlyingTokens") or []
    symbols = []
    sym = str(meta.get("symbol", ""))
    if "-" in sym:
        symbols = sym.split("-")
    elif "/" in sym:
        symbols = sym.split("/")
    if any(s.upper() == "USDC" for s in symbols):
        return "USDC"
    if symbols:
        return symbols[0].upper()
    if underlying:
        return "USDC"
    return "USDC"


async def execute_pool_position(
    ctx,
    *,
    pool: str,
    amount: Any,
    asset_in: str | None = None,
    chain: str | None = None,
    user_address: str | None = None,
    slippage_bps: int = 50,
    research_thesis: str | None = None,
):
    """One-shot pool deposit. `pool` may be a DefiLlama pool UUID or a
    'protocol pair' string like 'raydium-amm SPACEX-WSOL'.
    """
    if not pool:
        return err_envelope("missing_pool", "Provide a pool UUID or 'protocol pair' string.")
    amt = _coerce_amount(amount)
    if amt <= 0:
        return err_envelope("invalid_amount", "amount must be a positive decimal value.")

    if not user_address:
        wallet = getattr(ctx, "wallet", None)
        if wallet:
            user_address = str(wallet)
    if not user_address:
        return err_envelope(
            "missing_wallet",
            "Connect a wallet before requesting a pool deposit; the plan needs a destination address.",
        )

    pool_arg = str(pool).strip()
    meta: Optional[dict[str, Any]] = None

    if _looks_like_pool_id(pool_arg):
        meta = await _fetch_pool_meta(pool_arg)
    else:
        protocol_hint, pair_hint = _split_protocol_pair(pool_arg)
        meta = await _resolve_protocol_pair(protocol_hint, pair_hint, chain=chain)
        # Fallback: drop the protocol filter and re-scan by pair only.
        if not meta and pair_hint:
            meta = await _resolve_protocol_pair("", pair_hint, chain=chain)
        # Second fallback: search DefiLlama by symbol prefix loosely.
        if not meta and protocol_hint and not pair_hint:
            meta = await _resolve_protocol_pair("", protocol_hint, chain=chain)

    if not meta:
        return err_envelope(
            "pool_not_found",
            f"Could not resolve `{pool_arg}` to a DefiLlama pool. "
            "Try a tighter reference: paste the DefiLlama pool UUID, or use 'protocol pair' "
            "(e.g. 'raydium-amm SPACEX-WSOL'). For Solana memes, the pair must exist as a "
            "live DefiLlama pool entry.",
        )

    chain = str(meta.get("chain", "")).lower()
    protocol = str(meta.get("project", "")).lower()
    pool_symbol = str(meta.get("symbol", ""))
    final_asset_in = asset_in or _pick_asset_in(meta)

    is_lp = "-" in pool_symbol or "/" in pool_symbol
    action = "deposit_lp" if is_lp else "supply"

    extra: dict[str, Any] = {
        "pool_id": meta.get("pool"),
        "pool_symbol": pool_symbol,
    }
    if meta.get("underlyingTokens"):
        extra["underlying_tokens"] = meta.get("underlyingTokens")
    if chain.lower() in {"solana", "sol"}:
        # Solana yield-builder accepts an optional `lpMint` to skip the
        # prep-swap and route a single one-tx deposit into the LP token.
        # Only attach it when we have a real base58 Solana mint —
        # DefiLlama sometimes returns ETH-style hex strings in
        # `underlyingTokens` for cross-chain mirrors, which would 400 the
        # sidecar with `Invalid Solana public key`. When unsure, drop the
        # field and let the adapter fall through to its prep-swap path.
        candidates = []
        if meta.get("pool_address") or meta.get("poolAddress"):
            candidates.append(meta.get("pool_address") or meta.get("poolAddress"))
        for tok in (meta.get("underlyingTokens") or []):
            candidates.append(tok)
        valid = next((c for c in candidates if _is_solana_pubkey(c)), None)
        if valid:
            extra["lpMint"] = valid

    return await build_yield_execution_plan(
        ctx,
        chain=chain,
        protocol=protocol,
        action=action,
        asset_in=final_asset_in,
        amount_in=amt,
        user_address=user_address,
        slippage_bps=slippage_bps,
        research_thesis=research_thesis or f"Direct deposit into {protocol} {pool_symbol} on {chain}.",
    )
