"""F10 AGGREGATOR_CIRCUIT size-cap pin tests.

Pass-4 hand-read confirmed a $1M USDC→ETH swap was getting through with
no size cap. This test pins the fix: any swap whose USD notional exceeds
$500K must return err_envelope(code='aggregator_circuit', ...) unless the
caller passes extra.confirm_megaswap=True.
"""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.agent.tools._base import ToolCtx
from src.agent.tools.wallet_swap import build_swap_tx


@pytest.fixture(autouse=True)
def _clean_modules():
    """Remove mock module from sys.modules after each test."""
    yield
    sys.modules.pop("wallet_assistant_crypto_agent", None)


def _make_mock_assistant():
    """Returns a `_build_swap_tx` mock that emits a valid swap_quote payload.

    Wired into sys.modules so the wallet-assistant import resolves. We need
    this even for tests that expect early rejection (size cap fires AFTER
    address validation but BEFORE the assistant is invoked), so the import
    chain doesn't itself raise.
    """
    return MagicMock(return_value=json.dumps({
        "status": "ok",
        "chain_id": 1,
        "from_token_symbol": "USDC",
        "to_token_symbol": "ETH",
        "amount_in_display": 1_000_000.0,
        "dst_amount_display": 434.78,
        "route_summary": "Enso Aggregator",
        "price_impact_pct": 0.5,
        "tx": {"from": "0xabc", "to": "0xdef", "data": "0x1", "value": "0x0"},
    }))


@pytest.mark.asyncio
async def test_megaswap_rejected_by_size_cap():
    """$1M USDC→ETH on Ethereum mainnet must trip the aggregator_circuit cap."""
    mock_module = SimpleNamespace(_build_swap_tx=_make_mock_assistant())
    sys.modules["wallet_assistant_crypto_agent"] = mock_module

    services = SimpleNamespace()
    ctx = ToolCtx(
        services=services,
        user_id=0,
        wallet="0x0000000000000000000000000000000000000abc",
        evm_wallet="0x0000000000000000000000000000000000000abc",
    )

    # 1,000,000 USDC at 6 decimals = 1e12 base units. USDC stable fallback
    # ($1) ensures the cap fires even without a live price client.
    result = await build_swap_tx(
        ctx,
        chain_id=1,
        token_in="USDC",
        token_out="ETH",
        amount_in=str(1_000_000 * (10 ** 6)),
        from_addr="0x0000000000000000000000000000000000000abc",
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "AGGREGATOR_CIRCUIT_BREAKER"
    assert "500K" in result.error.message
    assert "confirm_megaswap" in result.error.message


@pytest.mark.asyncio
async def test_megaswap_allowed_with_confirm_override():
    """extra.confirm_megaswap=True bypasses the cap so power users can ship."""
    mock_build = _make_mock_assistant()
    mock_module = SimpleNamespace(_build_swap_tx=mock_build)
    sys.modules["wallet_assistant_crypto_agent"] = mock_module

    services = SimpleNamespace()
    ctx = ToolCtx(
        services=services,
        user_id=0,
        wallet="0x0000000000000000000000000000000000000abc",
        evm_wallet="0x0000000000000000000000000000000000000abc",
    )

    result = await build_swap_tx(
        ctx,
        chain_id=1,
        token_in="USDC",
        token_out="ETH",
        amount_in=str(1_000_000 * (10 ** 6)),
        from_addr="0x0000000000000000000000000000000000000abc",
        extra={"confirm_megaswap": True},
    )

    # With the override the swap should proceed to the assistant call.
    assert result.ok is True
    assert result.card_type == "swap_quote"
    mock_build.assert_called_once()


@pytest.mark.asyncio
async def test_small_swap_under_cap_proceeds():
    """100 USDC swap is well under the cap and must go through unchanged."""
    mock_build = MagicMock(return_value=json.dumps({
        "status": "ok",
        "chain_id": 1,
        "from_token_symbol": "USDC",
        "to_token_symbol": "ETH",
        "amount_in_display": 100.0,
        "dst_amount_display": 0.0434,
        "route_summary": "Enso Aggregator",
        "price_impact_pct": 0.1,
        "tx": {"from": "0xabc", "to": "0xdef", "data": "0x1", "value": "0x0"},
    }))
    mock_module = SimpleNamespace(_build_swap_tx=mock_build)
    sys.modules["wallet_assistant_crypto_agent"] = mock_module

    services = SimpleNamespace()
    ctx = ToolCtx(
        services=services,
        user_id=0,
        wallet="0x0000000000000000000000000000000000000abc",
        evm_wallet="0x0000000000000000000000000000000000000abc",
    )

    result = await build_swap_tx(
        ctx,
        chain_id=1,
        token_in="USDC",
        token_out="ETH",
        amount_in=str(100 * (10 ** 6)),
        from_addr="0x0000000000000000000000000000000000000abc",
    )

    assert result.ok is True
    assert result.card_type == "swap_quote"
