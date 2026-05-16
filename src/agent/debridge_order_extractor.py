"""deBridge DLN OrderCreated extraction from EVM receipts.

When a bridge step's tx confirms, scan the receipt logs for events emitted
by known DLN source contracts. The DLN protocol emits `CreatedOrder` with
the orderId as one of its fields. We extract that orderId and the runtime
calls `pending_plans.rekey(quote_id, real_order_id)` so the webhook fill
later matches the plan.

DLN Source addresses are uniform across chains (deBridge deploys the same
proxy at the same address). See https://docs.debridge.finance for refs.

Topic0 for `CreatedOrder` is provisionally registered here. When verified
against a real bridge tx, update _DLN_ORDER_TOPIC0.
"""
from __future__ import annotations

from typing import Any


# DLN Source proxy addresses per chain (deBridge canonical deploys).
# Source: https://docs.debridge.finance/contracts/dln-protocol-contracts
DLN_SOURCE_ADDRESSES: dict[int, str] = {
    1:     "0xeF4fB24aD0916217251F553c0596F8Edc630EB66",  # Ethereum
    56:    "0xeF4fB24aD0916217251F553c0596F8Edc630EB66",  # BSC
    137:   "0xeF4fB24aD0916217251F553c0596F8Edc630EB66",  # Polygon
    42161: "0xeF4fB24aD0916217251F553c0596F8Edc630EB66",  # Arbitrum
    10:    "0xeF4fB24aD0916217251F553c0596F8Edc630EB66",  # Optimism
    43114: "0xeF4fB24aD0916217251F553c0596F8Edc630EB66",  # Avalanche
    8453:  "0xeF4fB24aD0916217251F553c0596F8Edc630EB66",  # Base
    59144: "0xeF4fB24aD0916217251F553c0596F8Edc630EB66",  # Linea
}

# Provisional event topic0 hash for `CreatedOrder` — pending on-chain verify.
# When a real fill is observed in staging, replace with the actual keccak256
# of the canonical CreatedOrder signature.
_DLN_ORDER_TOPIC0_CANDIDATES: set[str] = {
    # keccak256("CreatedOrder((uint64,bytes,uint256,bytes,uint256,bytes,uint256,uint256,uint256,bytes,bytes,bytes,bytes,bytes,bytes,bytes,bytes,bytes,bytes,bytes),bytes32,bytes,uint256,uint32)")
    # placeholder — replace post-on-chain verification
    "0xfbabd6b3f9c9d4b40e21c5d8b1adfb44b0b65b9d0e07a8be5a9eaaaaaaaaaaaa",
}


def is_dln_source(chain_id: int, address: str | None) -> bool:
    """Return True when the log address matches the DLN Source proxy for the chain."""
    if not address:
        return False
    canonical = DLN_SOURCE_ADDRESSES.get(chain_id)
    if not canonical:
        return False
    return address.lower() == canonical.lower()


def extract_order_id_from_logs(
    chain_id: int,
    logs: list[dict[str, Any]],
) -> str | None:
    """Scan EVM receipt logs for a DLN CreatedOrder event and return the
    orderId (bytes32, 0x-prefixed 66-char hex). Returns None when no DLN
    log is present or when the orderId can't be located.

    Best-effort: matches log.address ∈ DLN_SOURCE_ADDRESSES, then looks
    for a bytes32 candidate in the data section.
    """
    if not logs:
        return None
    for log in logs:
        addr = log.get("address") or ""
        if not is_dln_source(chain_id, addr):
            continue
        topics = log.get("topics") or []
        data = (log.get("data") or "0x").removeprefix("0x")
        # DLN encodes orderId in the data section as the first bytes32
        # word (the Order struct is the indexed/data leading field).
        # We pull the first 32 bytes from `data` when present.
        if len(data) >= 64:
            order_id_hex = "0x" + data[:64]
            return order_id_hex
        # Fallback: if topic0 is a known CreatedOrder hash and topic1 exists,
        # use topic1.
        if topics and topics[0] in _DLN_ORDER_TOPIC0_CANDIDATES and len(topics) >= 2:
            return topics[1]
    return None


def register_topic(topic0: str) -> None:
    """Test/runtime helper to add a discovered CreatedOrder topic0 hash."""
    _DLN_ORDER_TOPIC0_CANDIDATES.add(topic0.lower())
