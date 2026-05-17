"""
V7-005 — Auto-detect EIP-1559 vs legacy gas pricing per EVM chain.

Some chains (BNB Smart Chain, classic Polygon PoS) reject type-2
(``maxFeePerGas`` / ``maxPriorityFeePerGas``) transactions or accept
them but mis-price gas, leading to silent overpayment or failed sends.
Other chains (Ethereum mainnet, Base, Arbitrum, etc.) require type-2 to
land in a reasonable time once London is active.

Strategy:

1. A small hard-coded ``_LEGACY_CHAINS`` set short-circuits the known
   "type-0 only" networks so we never probe them.
2. For any other chain, probe ``eth_feeHistory`` once. If the response
   includes a ``baseFeePerGas`` array, the chain has activated London
   and we use type-2; otherwise we fall back to legacy ``gasPrice``.
3. Results are cached per chain-id on the calling client so repeated
   sends in the same process do not re-probe.

The helper returns a dict suitable for spreading into a
JSON-RPC ``eth_sendTransaction`` / wallet ``eth_signTransaction``
parameter object.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Set

logger = logging.getLogger(__name__)


# Chains that MUST receive legacy ``gasPrice`` only. BSC's validators
# accept type-2 but ignore the priority component; Polygon PoS pre-Bhilai
# has the same behaviour and over-pays. Keep this set conservative — we
# would rather probe and discover 1559-capable than silently underpay.
_LEGACY_CHAINS: Set[int] = {
    56,   # BNB Smart Chain
    137,  # Polygon PoS (classic)
}


# Cache: chain_id -> bool ("True = supports 1559"). Process-local.
_SUPPORTS_1559_CACHE: Dict[int, bool] = {}


async def detect_supports_1559(client: Any, chain_id: int) -> bool:
    """Return True iff ``chain_id`` supports EIP-1559 (type-2) txs.

    Args:
        client: An object exposing ``async _rpc_call(method, params)``
            (typically ``EVMChainClient``). The signature matches the
            existing client's helper so we avoid creating yet another
            HTTP session.
        chain_id: EVM chain id.

    Returns:
        True if the chain accepts ``maxFeePerGas`` / ``maxPriorityFeePerGas``,
        False otherwise.
    """
    # 1. Hard override for known legacy chains.
    if chain_id in _LEGACY_CHAINS:
        return False

    # 2. Cached result.
    cached = _SUPPORTS_1559_CACHE.get(chain_id)
    if cached is not None:
        return cached

    # 3. Probe via eth_feeHistory(1, "latest", [25]).
    try:
        result = await client._rpc_call(
            "eth_feeHistory", [1, "latest", [25]]
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"eth_feeHistory probe failed on chain {chain_id}: {exc}")
        _SUPPORTS_1559_CACHE[chain_id] = False
        return False

    supports = bool(
        result
        and isinstance(result, dict)
        and result.get("baseFeePerGas")
    )
    _SUPPORTS_1559_CACHE[chain_id] = supports
    return supports


def _hex_to_int(value: Any) -> int:
    """Best-effort hex/int decode for RPC numeric fields."""
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 16) if value.startswith("0x") else int(value)
        except ValueError:
            return 0
    return 0


async def _legacy_gas_price(client: Any) -> int:
    """Read ``eth_gasPrice`` and decode to wei."""
    raw = await client._rpc_call("eth_gasPrice", [])
    return _hex_to_int(raw)


async def _eip1559_params(client: Any) -> Dict[str, int]:
    """Compute ``maxFeePerGas`` and ``maxPriorityFeePerGas`` (wei).

    Uses the latest ``baseFeePerGas`` from ``eth_feeHistory`` plus an
    ``eth_maxPriorityFeePerGas`` tip (with a 1 gwei fallback). The
    ``maxFeePerGas`` is set to ``2 * baseFee + tip`` so the tx survives
    one full block of base-fee escalation.
    """
    fee_history = await client._rpc_call(
        "eth_feeHistory", [1, "latest", [25]]
    )

    base_fee = 0
    if (
        fee_history
        and isinstance(fee_history, dict)
        and fee_history.get("baseFeePerGas")
    ):
        # baseFeePerGas is an array of length blockCount+1; take the last
        # entry which is the *next* block's base fee.
        try:
            base_fee = _hex_to_int(fee_history["baseFeePerGas"][-1])
        except (IndexError, TypeError):
            base_fee = 0

    tip_raw = await client._rpc_call("eth_maxPriorityFeePerGas", [])
    tip = _hex_to_int(tip_raw)
    if tip <= 0:
        tip = 1_000_000_000  # 1 gwei fallback

    max_fee = base_fee * 2 + tip if base_fee > 0 else tip * 2

    return {
        "maxFeePerGas": max_fee,
        "maxPriorityFeePerGas": tip,
    }


async def build_gas_params(client: Any, chain_id: int) -> Dict[str, int]:
    """Build the gas-pricing fields for an outbound tx on ``chain_id``.

    Returns either ``{"gasPrice": wei}`` for legacy chains or
    ``{"maxFeePerGas": wei, "maxPriorityFeePerGas": wei}`` for
    EIP-1559-capable chains.

    The caller is responsible for merging these fields into the rest of
    the tx envelope and for setting the matching ``type`` field
    (``0x0`` for legacy, ``0x2`` for 1559) if the downstream signer
    requires it.
    """
    supports_1559 = await detect_supports_1559(client, chain_id)
    if supports_1559:
        return await _eip1559_params(client)

    return {"gasPrice": await _legacy_gas_price(client)}


__all__ = [
    "_LEGACY_CHAINS",
    "detect_supports_1559",
    "build_gas_params",
]
