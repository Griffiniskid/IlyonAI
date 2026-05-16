"""Pin: deBridge DLN CreatedOrder extraction from EVM receipt logs."""
from __future__ import annotations

from src.agent.debridge_order_extractor import (
    DLN_SOURCE_ADDRESSES,
    extract_order_id_from_logs,
    is_dln_source,
)


_DLN_ETH = "0xeF4fB24aD0916217251F553c0596F8Edc630EB66"


def test_is_dln_source_recognises_canonical_addresses():
    assert is_dln_source(1, _DLN_ETH)
    assert is_dln_source(8453, _DLN_ETH)
    assert is_dln_source(42161, _DLN_ETH)
    assert not is_dln_source(1, "0x0000000000000000000000000000000000000000")
    assert not is_dln_source(9999, _DLN_ETH)  # unknown chain
    assert not is_dln_source(1, None)


def test_extract_order_id_from_data_first_word():
    """First 32 bytes of the data section is treated as the orderId."""
    order_id = "abcdef0123456789" * 4  # 64 hex chars = 32 bytes
    logs = [
        {
            "address": _DLN_ETH,
            "topics": ["0xdeadbeef"],
            "data": "0x" + order_id + "ff" * 32,
        }
    ]
    out = extract_order_id_from_logs(1, logs)
    assert out == "0x" + order_id


def test_extract_returns_none_when_no_dln_log():
    logs = [
        {"address": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", "topics": [], "data": "0x"},
    ]
    assert extract_order_id_from_logs(1, logs) is None


def test_extract_returns_none_when_logs_empty():
    assert extract_order_id_from_logs(1, []) is None


def test_dln_source_addresses_uniform_per_canonical_chains():
    """deBridge uses the same proxy address across all canonical chains."""
    addrs = set(a.lower() for a in DLN_SOURCE_ADDRESSES.values())
    assert len(addrs) == 1  # all chains share same proxy
