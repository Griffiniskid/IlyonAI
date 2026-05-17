"""V7-039 — Pending-nonce management for EVM transaction broadcast.

When the agent constructs an outbound transaction (swap, approve,
transfer, bridge) the wallet/signer needs a fresh ``nonce``. Using the
``latest`` block tag misses any tx already in the mempool from the same
EOA, producing ``nonce too low`` errors and silently dropped sends.

This helper standardises on ``eth_getTransactionCount(addr, 'pending')``
which counts mined + pending transactions, giving the next slot any
broadcast can safely occupy.

The function tolerates either a hex string (``"0x5"``) or a raw integer
result, since different JSON-RPC providers and our internal mocks return
the value in different shapes.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def get_next_nonce(client: Any, address: str) -> int:
    """Return the next-available transaction nonce for ``address``.

    Issues ``eth_getTransactionCount(address, 'pending')`` against the
    supplied RPC client and normalises the result to ``int``.

    Args:
        client: An object exposing either ``async call_rpc(method, params)``
            or ``async _rpc_call(method, params)``. ``call_rpc`` is
            preferred (matches the V7-039 spec); ``_rpc_call`` is the
            fallback so existing :class:`EVMChainClient` instances work
            without renaming their internal helper.
        address: 0x-prefixed EVM address (case-insensitive).

    Returns:
        The next nonce as a non-negative ``int``.

    Raises:
        ValueError: If the RPC response cannot be decoded as an integer.
    """
    rpc = getattr(client, "call_rpc", None) or getattr(client, "_rpc_call", None)
    if rpc is None:
        raise AttributeError(
            "client must expose async call_rpc or _rpc_call(method, params)"
        )

    result = await rpc("eth_getTransactionCount", [address, "pending"])

    if isinstance(result, str):
        return int(result, 16) if result.startswith("0x") else int(result)
    return int(result)
