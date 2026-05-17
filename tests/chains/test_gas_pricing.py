"""V7-005 — Pin test for EIP-1559 vs legacy gas-pricing auto-detection.

Verifies ``src.chains.evm.gas_pricing.build_gas_params`` returns the
correct shape for each chain class:

* BSC (56) and Polygon (137) — forced legacy ``gasPrice``, *no* RPC
  probe (probing them is wasteful and BSC's feeHistory can lie).
* Ethereum mainnet (1) — probes ``eth_feeHistory``; with a
  ``baseFeePerGas`` array present, returns type-2 fields.
* Unknown chain (999) without ``baseFeePerGas`` — falls back to legacy.

A regression here means swap/approve/transfer txs hand the frontend
signer the wrong tx type and either fail outright (BSC rejecting
type-2) or silently overpay (Polygon over-tipping).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pytest

from src.chains.evm import gas_pricing
from src.chains.evm.gas_pricing import build_gas_params, detect_supports_1559


class _FakeClient:
    """Minimal stand-in for ``EVMChainClient`` exposing ``_rpc_call``."""

    def __init__(self, responses: Dict[str, Any]) -> None:
        self._responses = responses
        self.calls: List[Tuple[str, Optional[list]]] = []

    async def _rpc_call(self, method: str, params: Optional[list] = None) -> Any:
        self.calls.append((method, params))
        return self._responses.get(method)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Each test starts with an empty per-chain support cache."""
    gas_pricing._SUPPORTS_1559_CACHE.clear()
    yield
    gas_pricing._SUPPORTS_1559_CACHE.clear()


# ----- BSC (56) ----------------------------------------------------------

@pytest.mark.asyncio
async def test_bsc_returns_legacy_without_probing():
    """Chain 56 must return ``{gasPrice}`` and must NOT call feeHistory."""
    fake = _FakeClient({"eth_gasPrice": "0xb2d05e00"})  # 3 gwei

    params = await build_gas_params(fake, 56)

    assert set(params.keys()) == {"gasPrice"}
    assert params["gasPrice"] == 3_000_000_000
    # No probing of eth_feeHistory for the hard-coded legacy set.
    methods_called = [m for m, _ in fake.calls]
    assert "eth_feeHistory" not in methods_called
    assert methods_called == ["eth_gasPrice"]


@pytest.mark.asyncio
async def test_bsc_supports_1559_returns_false_without_probing():
    fake = _FakeClient({})
    assert await detect_supports_1559(fake, 56) is False
    assert fake.calls == []  # short-circuited


# ----- Polygon classic (137) --------------------------------------------

@pytest.mark.asyncio
async def test_polygon_returns_legacy_without_probing():
    fake = _FakeClient({"eth_gasPrice": "0x77359400"})  # 2 gwei

    params = await build_gas_params(fake, 137)

    assert set(params.keys()) == {"gasPrice"}
    assert params["gasPrice"] == 2_000_000_000
    methods_called = [m for m, _ in fake.calls]
    assert "eth_feeHistory" not in methods_called


# ----- Ethereum mainnet (1) ---------------------------------------------

@pytest.mark.asyncio
async def test_ethereum_returns_eip1559_when_base_fee_present():
    """Mocked feeHistory carries a baseFeePerGas → type-2 envelope."""
    fake = _FakeClient(
        {
            # baseFeePerGas[-1] = 20 gwei
            "eth_feeHistory": {
                "baseFeePerGas": ["0x3b9aca00", "0x4a817c800"],
                "gasUsedRatio": [0.5],
                "oldestBlock": "0x1",
                "reward": [["0x3b9aca00"]],
            },
            # tip = 2 gwei
            "eth_maxPriorityFeePerGas": "0x77359400",
        }
    )

    params = await build_gas_params(fake, 1)

    assert set(params.keys()) == {"maxFeePerGas", "maxPriorityFeePerGas"}
    assert params["maxPriorityFeePerGas"] == 2_000_000_000
    # maxFee = 2 * baseFee + tip = 2 * 20gwei + 2gwei = 42 gwei
    assert params["maxFeePerGas"] == 2 * 20_000_000_000 + 2_000_000_000

    # Probe must have happened.
    methods_called = [m for m, _ in fake.calls]
    assert "eth_feeHistory" in methods_called
    assert "eth_maxPriorityFeePerGas" in methods_called


# ----- Unknown chain (999) ----------------------------------------------

@pytest.mark.asyncio
async def test_unknown_chain_without_base_fee_falls_back_to_legacy():
    """No baseFeePerGas in feeHistory → treat as legacy."""
    fake = _FakeClient(
        {
            "eth_feeHistory": {
                "gasUsedRatio": [0.5],
                "oldestBlock": "0x1",
                # baseFeePerGas intentionally absent
            },
            "eth_gasPrice": "0x12a05f200",  # 5 gwei
        }
    )

    params = await build_gas_params(fake, 999)

    assert set(params.keys()) == {"gasPrice"}
    assert params["gasPrice"] == 5_000_000_000
    methods_called = [m for m, _ in fake.calls]
    # Probe happened, then fell back.
    assert "eth_feeHistory" in methods_called
    assert "eth_gasPrice" in methods_called


@pytest.mark.asyncio
async def test_detect_supports_1559_caches_per_chain():
    """Repeat probes on the same chain reuse the cached answer."""
    fake = _FakeClient(
        {
            "eth_feeHistory": {
                "baseFeePerGas": ["0x1", "0x1"],
                "gasUsedRatio": [0.1],
            }
        }
    )

    first = await detect_supports_1559(fake, 8453)  # Base
    second = await detect_supports_1559(fake, 8453)

    assert first is True and second is True
    # Only one underlying probe.
    assert [m for m, _ in fake.calls].count("eth_feeHistory") == 1
