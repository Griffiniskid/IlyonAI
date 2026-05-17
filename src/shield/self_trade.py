"""Spec §13 Row 26 — SELF_TRADE_AGAINST_OWN_LP detector.

A user holding an open Uniswap-V3 (or any fee-keyed CL fork) LP NFT can be
silently sandwiched by their own prep-swap when an aggregator routes the
swap leg through the same pool their LP is concentrated in. The LP earns
the swap fee on one side but loses inventory on the other; net IL/MEV
exposure usually exceeds fee capture for any non-trivial trade size.

This detector takes the (wallet, swap_pool_addr, chain_id) tuple, fetches
the wallet's open V3-family positions on that chain, derives the on-chain
pool address for each position via `factory.getPool(token0, token1, fee)`,
and short-circuits with `SELF_TRADE_AGAINST_OWN_LP` if the swap pool
appears in the user's open-LP pool set.

The detector is intentionally async so the preflight layer can fan-out
the per-position `getPool` calls in parallel, but the hot path here is a
single function suitable for unit-mocking. The `find_user_positions` and
`get_pool_addr` callables are injected to keep this module testable
without a live RPC or DB session.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Iterable, Optional

logger = logging.getLogger(__name__)

# Re-export the spec §6c blocker code so callers don't have to import
# from execution.models just to compare a string literal.
SELF_TRADE_BLOCKER_CODE = "SELF_TRADE_AGAINST_OWN_LP"

# Chain-id → (chain_name, default_v3_protocol) — used to pick the right
# entry in V3_FACTORIES when the caller only knows the EVM chain id.
# Mirrors the canonical Uniswap-V3 deploys; PancakeSwap-V3 on BSC keeps
# the secondary protocol slot for completeness.
_CHAIN_ID_TO_NAME: dict[int, str] = {
    1: "ethereum",
    10: "optimism",
    56: "bsc",
    100: "gnosis",
    130: "unichain",
    137: "polygon",
    146: "sonic",
    324: "zksync",
    5000: "mantle",
    8453: "base",
    42161: "arbitrum",
    42220: "celo",
    43114: "avalanche",
    59144: "linea",
    80094: "berachain",
    81457: "blast",
    534352: "scroll",
}

# V3-family receipt_kinds (see src/defi/verification/receipt_table.py) we
# treat as eligible for the self-trade check. NFP positions own a single
# fee-tier mapped pool; AMM-V2 / Balancer / Curve receipts don't.
_V3_RECEIPT_KINDS = frozenset({
    "UniswapV3NFP",
    "PancakeV3NFP",
    "SlipstreamNFP",
    "AlgebraNFP",
    "KodiakV3NFP",
    "SwapXV4NFP",
    # generic — many adapters write the lowercase shorthand
    "v3_nft",
    "univ3_nft",
})

# Protocols that key their factory by tickSpacing (int24) rather than the
# uint24 fee_bps. Self-trade detection on these protocols needs the
# tick-spacing variant; we mirror the v3_pool_resolver list here so this
# module doesn't reach back into a heavier import.
_TICKSPACING_KEYED_PROTOCOLS = frozenset({
    "aerodrome-slipstream",
    "velodrome-cl",
    "velodrome-slipstream",
})


# Type aliases for the two injection points the pin test exercises.
FindUserPositions = Callable[
    [str, int], Awaitable[list[dict[str, Any]]]
]
GetPoolAddr = Callable[
    [str, str, str, str, int], Awaitable[Optional[str]]
]


def _norm_addr(addr: Optional[str]) -> Optional[str]:
    if not addr:
        return None
    s = str(addr).strip().lower()
    if not s:
        return None
    if not s.startswith("0x"):
        s = "0x" + s
    return s


def _pick_chain_name(chain_id: int) -> Optional[str]:
    return _CHAIN_ID_TO_NAME.get(int(chain_id))


def _is_v3_position(pos: dict[str, Any]) -> bool:
    """Heuristic match — any of receipt_kind / protocol family suggests V3."""
    rk = (pos.get("receipt_kind") or "").strip()
    if rk in _V3_RECEIPT_KINDS:
        return True
    proto = (pos.get("protocol") or "").lower()
    if not proto:
        return False
    if proto in {
        "uniswap-v3", "pancakeswap-v3", "pancake-v3",
        "aerodrome-slipstream", "aerodrome-cl",
        "velodrome-cl", "velodrome-slipstream",
        "kodiak-v3", "swapx-v4",
    }:
        return True
    # Generic match: anything that ends in -v3 / -clmm / -cl
    return proto.endswith("-v3") or proto.endswith("-clmm") or proto.endswith("-cl")


async def _default_get_pool_addr(
    chain_name: str,
    protocol: str,
    token0: str,
    token1: str,
    fee_or_spacing: int,
) -> Optional[str]:
    """Production path: call into v3_pool_resolver.resolve_v3_pool.

    Returns the pool address as a lowercased hex string, or None when the
    pool doesn't exist on the requested factory. Live RPC — the pin test
    must inject a mock instead of relying on this default.
    """
    try:
        from src.data.v3_pool_resolver import resolve_v3_pool
    except Exception:  # pragma: no cover — import safety
        return None
    state = await resolve_v3_pool(
        chain=chain_name,
        protocol=protocol,
        token_a=token0,
        token_b=token1,
        fee_bps=int(fee_or_spacing),
    )
    if state is None:
        return None
    return _norm_addr(state.pool_address)


async def _default_find_user_positions(
    wallet_address: str,
    chain_id: int,
) -> list[dict[str, Any]]:
    """Production path: pull open V3 NFT positions from the position store.

    Returns an empty list when the DB session isn't available — this keeps
    the detector safe in offline / smoke-test paths. The pin test injects
    a mock that returns canned rows.
    """
    try:
        from src.storage.database import get_database  # type: ignore
        from src.defi.position_store import find_open_positions
    except Exception:
        return []
    try:
        db = get_database()
    except Exception:
        return []
    if db is None or not getattr(db, "_initialized", False):
        return []
    try:
        async with db.session() as session:  # type: ignore[attr-defined]
            return await find_open_positions(
                session,
                wallet_address=wallet_address,
                chain_id=chain_id,
            )
    except Exception as exc:  # pragma: no cover — defensive
        logger.debug("self_trade default find_user_positions failed: %s", exc)
        return []


async def detect_self_trade(
    user_wallet: str,
    swap_pool_addr: str,
    chain_id: int,
    *,
    find_user_positions: FindUserPositions | None = None,
    get_pool_addr: GetPoolAddr | None = None,
) -> Optional[str]:
    """Return ``SELF_TRADE_AGAINST_OWN_LP`` when the swap routes through a
    pool the user already provides liquidity to. Returns ``None`` when no
    overlap is found.

    Parameters
    ----------
    user_wallet:
        EVM address (0x...) of the signer. Case-insensitive.
    swap_pool_addr:
        Pool address the swap leg would touch. Case-insensitive.
    chain_id:
        EVM chain id (e.g. 1 = ethereum, 8453 = base).
    find_user_positions, get_pool_addr:
        Optional injection hooks for unit tests. When omitted, the
        production wiring (position_store + v3_pool_resolver) is used.
    """
    swap_pool_norm = _norm_addr(swap_pool_addr)
    wallet_norm = _norm_addr(user_wallet)
    if not swap_pool_norm or not wallet_norm:
        return None

    chain_name = _pick_chain_name(chain_id)
    if chain_name is None:
        # Unknown EVM chain → cannot derive factory; skip silently.
        return None

    fup = find_user_positions or _default_find_user_positions
    gpa = get_pool_addr or _default_get_pool_addr

    try:
        positions = await fup(wallet_norm, int(chain_id))
    except Exception as exc:
        logger.debug("self_trade find_user_positions raised: %s", exc)
        return None
    if not positions:
        return None

    # Build per-position getPool tasks. Skip rows that aren't V3-family.
    tasks: list[Awaitable[Optional[str]]] = []
    coords: list[tuple[str, str, str, int]] = []
    for pos in positions:
        if not _is_v3_position(pos):
            continue
        meta = pos.get("metadata") or {}
        token0 = _norm_addr(pos.get("token0") or meta.get("token0"))
        token1 = _norm_addr(pos.get("token1") or meta.get("token1"))
        proto = (pos.get("protocol") or "uniswap-v3").lower()
        # Caller may store fee_bps (e.g. 500 for 0.05%) or tickSpacing on
        # Slipstream factories. We forward whichever is set; getPool's
        # routing inside the resolver handles the discriminator.
        fee_or_spacing = (
            pos.get("fee_bps")
            or pos.get("fee")
            or meta.get("fee_bps")
            or meta.get("fee")
            or pos.get("tick_spacing")
            or meta.get("tick_spacing")
        )
        if token0 is None or token1 is None or fee_or_spacing is None:
            continue
        try:
            fee_int = int(fee_or_spacing)
        except (TypeError, ValueError):
            continue
        coords.append((proto, token0, token1, fee_int))
        tasks.append(gpa(chain_name, proto, token0, token1, fee_int))

    if not tasks:
        return None

    resolved = await asyncio.gather(*tasks, return_exceptions=True)
    owned_pool_addrs: set[str] = set()
    for coord, res in zip(coords, resolved):
        if isinstance(res, Exception):
            logger.debug("self_trade getPool error for %s: %s", coord, res)
            continue
        n = _norm_addr(res)
        if n:
            owned_pool_addrs.add(n)

    if swap_pool_norm in owned_pool_addrs:
        return SELF_TRADE_BLOCKER_CODE
    return None


def detect_self_trade_sync(
    user_wallet: str,
    swap_pool_addr: str,
    chain_id: int,
    *,
    owned_pool_addrs: Iterable[str],
) -> Optional[str]:
    """Synchronous, pure-Python variant for callers that already know
    the user's open-LP pool set (e.g. cached upstream). Useful inside
    preflight when the inventory dict already carries `existing_positions`
    with a resolved `pool_address` column."""
    swap_pool_norm = _norm_addr(swap_pool_addr)
    if not swap_pool_norm:
        return None
    owned = {p for p in (_norm_addr(x) for x in owned_pool_addrs) if p}
    if swap_pool_norm in owned:
        return SELF_TRADE_BLOCKER_CODE
    return None
