"""V7-043 — real receipt-log parsing across adapter verify() methods.

Spec: replace stub ``confirmed=False`` returns with canonical event-topic
match. For each high-traffic adapter we assert:
  1. receipt carrying the expected topic0 → confirmed=True, log_match≥1
  2. empty logs → confirmed=False, log_match=0
  3. wrong topic0 → confirmed=False, log_match=0

These tests do NOT hit a chain — they synthesize EVM receipts so the parser
is fully exercised in CI.
"""
from __future__ import annotations

import asyncio

import pytest

from src.defi.execution.adapters.aave_v3 import AaveV3SupplyAdapter
from src.defi.execution.adapters.balancer import BalancerSingleAssetAdapter
from src.defi.execution.adapters.base import YieldVerifyRequest
from src.defi.execution.adapters.compound_v3 import CompoundV3SupplyAdapter
from src.defi.execution.adapters.curve import CurveSingleSidedAdapter
from src.defi.execution.adapters.erc4626 import ERC4626VaultAdapter
from src.defi.execution.adapters.evm_lst import EvmLstDirectMintAdapter
from src.defi.execution.adapters.pendle_v2 import PendleV2Adapter
from src.defi.execution.adapters.uniswap_v2 import UniswapV2DualTokenAdapter


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _receipt(topic0: str | None) -> dict:
    """Synthesize a minimal EVM-shaped receipt with one log."""
    logs: list[dict] = []
    if topic0 is not None:
        logs.append({
            "address": "0x0000000000000000000000000000000000000001",
            "topics": [topic0, "0x" + "00" * 32, "0x" + "00" * 32],
            "data": "0x" + "00" * 64,
        })
    return {"status": "0x1", "logs": logs, "transactionHash": "0xdeadbeef"}


def _empty_receipt() -> dict:
    return {"status": "0x1", "logs": [], "transactionHash": "0xdeadbeef"}


WRONG_TOPIC = "0xbaadc0debaadc0debaadc0debaadc0debaadc0debaadc0debaadc0debaadc0de"


ADAPTERS = [
    ("aave_v3", AaveV3SupplyAdapter()),
    ("compound_v3", CompoundV3SupplyAdapter()),
    ("uniswap_v2", UniswapV2DualTokenAdapter()),
    ("curve", CurveSingleSidedAdapter()),
    ("pendle_v2", PendleV2Adapter()),
    ("balancer", BalancerSingleAssetAdapter()),
    ("erc4626", ERC4626VaultAdapter()),
    ("evm_lst", EvmLstDirectMintAdapter()),
]


def _verify_request(receipt: dict | None) -> YieldVerifyRequest:
    return YieldVerifyRequest(
        chain="ethereum",
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        expected_position={},
        receipt=receipt,
    )


@pytest.mark.parametrize("name,adapter", ADAPTERS, ids=[n for n, _ in ADAPTERS])
def test_matching_topic0_confirms(name: str, adapter) -> None:
    """A receipt carrying EXPECTED_TOPIC0 must confirm with log_match≥1."""
    assert hasattr(adapter, "EXPECTED_TOPIC0"), f"{name} missing EXPECTED_TOPIC0 const"
    topic0 = adapter.EXPECTED_TOPIC0
    assert isinstance(topic0, str) and topic0.startswith("0x") and len(topic0) == 66, (
        f"{name} EXPECTED_TOPIC0 not a 32-byte hex string"
    )
    req = _verify_request(_receipt(topic0))
    result = _run(adapter.verify(req))
    assert result.confirmed is True, f"{name} did not confirm on matching topic0"
    assert result.log_match >= 1, f"{name} log_match expected ≥1, got {result.log_match}"
    assert result.event_signature == topic0, f"{name} event_signature mismatch"
    assert result.raw_log is not None, f"{name} raw_log missing"


@pytest.mark.parametrize("name,adapter", ADAPTERS, ids=[n for n, _ in ADAPTERS])
def test_empty_logs_do_not_confirm(name: str, adapter) -> None:
    """A receipt with zero logs must report confirmed=False, log_match=0."""
    req = _verify_request(_empty_receipt())
    result = _run(adapter.verify(req))
    assert result.confirmed is False, f"{name} falsely confirmed on empty logs"
    assert result.log_match == 0, f"{name} log_match should be 0 on empty logs"
    assert result.event_signature is None, f"{name} event_signature should be None"


@pytest.mark.parametrize("name,adapter", ADAPTERS, ids=[n for n, _ in ADAPTERS])
def test_wrong_topic0_does_not_confirm(name: str, adapter) -> None:
    """A receipt whose only log has a different topic0 must not confirm."""
    req = _verify_request(_receipt(WRONG_TOPIC))
    result = _run(adapter.verify(req))
    assert result.confirmed is False, f"{name} falsely confirmed on wrong topic0"
    assert result.log_match == 0, f"{name} log_match should be 0 on wrong topic0"


def test_no_receipt_returns_unconfirmed() -> None:
    """Adapters must not crash when no receipt is provided."""
    adapter = AaveV3SupplyAdapter()
    req = _verify_request(None)
    result = _run(adapter.verify(req))
    assert result.confirmed is False
    assert result.log_match == 0


def test_topic0_match_is_case_insensitive() -> None:
    """Receipt logs from RPCs vary in case — match must be case-insensitive."""
    adapter = AaveV3SupplyAdapter()
    upper = adapter.EXPECTED_TOPIC0.upper().replace("0X", "0x")
    req = _verify_request(_receipt(upper))
    result = _run(adapter.verify(req))
    assert result.confirmed is True
    assert result.log_match == 1


def test_receipt_via_expected_position_fallback() -> None:
    """Receipt can also be carried inside expected_position['receipt']."""
    adapter = ERC4626VaultAdapter()
    req = YieldVerifyRequest(
        chain="ethereum",
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        expected_position={"receipt": _receipt(adapter.EXPECTED_TOPIC0)},
        receipt=None,
    )
    result = _run(adapter.verify(req))
    assert result.confirmed is True
    assert result.log_match == 1


def test_multi_log_receipt_counts_only_matching() -> None:
    """Receipts with many logs surface log_match equal to matching count."""
    adapter = AaveV3SupplyAdapter()
    topic0 = adapter.EXPECTED_TOPIC0
    receipt = {
        "status": "0x1",
        "logs": [
            {"topics": [WRONG_TOPIC]},
            {"topics": [topic0, "0x" + "11" * 32]},
            {"topics": [WRONG_TOPIC]},
            {"topics": [topic0, "0x" + "22" * 32]},
        ],
        "transactionHash": "0xfeedface",
    }
    req = _verify_request(receipt)
    result = _run(adapter.verify(req))
    assert result.confirmed is True
    assert result.log_match == 2
