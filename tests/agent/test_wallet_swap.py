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


@pytest.mark.asyncio
async def test_build_swap_tx_success():
    """Test successful swap tx building via wallet assistant."""
    mock_build_swap_tx = MagicMock(return_value=json.dumps({
        "status": "ok",
        "chain_id": 56,
        "from_token_symbol": "BNB",
        "to_token_symbol": "USDT",
        "amount_in_display": 1.0,
        "dst_amount_display": 600.0,
        "route_summary": "Enso Aggregator",
        "price_impact_pct": 0.5,
        "platform_fee_bps": 50,
        "tx": {
            "from": "0xabc",
            "to": "0xdef",
            "data": "0x123",
            "value": "0x0",
        },
    }))

    mock_module = MagicMock()
    mock_module._build_swap_tx = mock_build_swap_tx
    sys.modules["wallet_assistant_crypto_agent"] = mock_module

    services = SimpleNamespace()
    ctx = ToolCtx(services=services, user_id=0, wallet="0xabc")

    result = await build_swap_tx(
        ctx,
        chain_id=56,
        token_in="BNB",
        token_out="USDT",
        amount_in="1000000000000000000",
        from_addr="0xabc",
    )

    assert result.ok is True
    assert result.card_type == "swap_quote"
    assert result.card_payload is not None
    assert result.card_payload["pay"]["address"] == "BNB"
    assert result.card_payload["receive"]["address"] == "USDT"
    assert result.card_payload["router"] == "enso"
    assert result.card_payload["price_impact_pct"] == 0.5
    assert result.card_payload["slippage_bps"] == 100
    assert result.card_payload["spender"] == "0xdef"
    assert result.data is not None
    assert result.data["status"] == "ok"
    assert result.data["chain_id"] == 56

    mock_build_swap_tx.assert_called_once()
    call_args = mock_build_swap_tx.call_args[0]
    assert json.loads(call_args[0])["chain_id"] == 56
    assert call_args[1] == "0xabc"
    assert call_args[2] == 56


@pytest.mark.asyncio
async def test_build_swap_tx_solana():
    """Test Solana swap tx building via wallet assistant."""
    mock_build_swap_tx = MagicMock(return_value=json.dumps({
        "status": "ok",
        "chain_type": "solana",
        "out_amount": "500000000",
        "out_amount_min": "495000000",
        "price_impact_pct": "0.25",
        "platform_fee_bps": 50,
        "fee_account": "FeeAccount111111111111111111111111111111111",
        "tx": {
            "serialized": "base64tx",
            "last_valid_block_height": 123456789,
        },
    }))

    mock_module = MagicMock()
    mock_module._build_swap_tx = mock_build_swap_tx
    sys.modules["wallet_assistant_crypto_agent"] = mock_module

    services = SimpleNamespace()
    ctx = ToolCtx(services=services, user_id=0, wallet="SolanaPubkey")

    result = await build_swap_tx(
        ctx,
        chain_id=101,
        token_in="SOL",
        token_out="USDC",
        amount_in="1000000000",
        from_addr="SolanaPubkey",
    )

    assert result.ok is True
    assert result.card_type == "swap_quote"
    assert result.card_payload["router"] == "jupiter"
    assert result.card_payload["slippage_bps"] == 50
    assert result.card_payload["spender"] == "FeeAccount111111111111111111111111111111111"


@pytest.mark.asyncio
async def test_build_swap_tx_error():
    """Test error handling when wallet assistant returns an error."""
    mock_build_swap_tx = MagicMock(return_value=json.dumps({
        "status": "error",
        "message": "Insufficient liquidity",
    }))

    mock_module = MagicMock()
    mock_module._build_swap_tx = mock_build_swap_tx
    sys.modules["wallet_assistant_crypto_agent"] = mock_module

    services = SimpleNamespace()
    ctx = ToolCtx(services=services, user_id=0, wallet="0xabc")

    result = await build_swap_tx(
        ctx,
        chain_id=56,
        token_in="UNKNOWN",
        token_out="USDT",
        amount_in="1000000000000000000",
        from_addr="0xabc",
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "swap_failed"
    assert "Insufficient liquidity" in result.error.message


@pytest.mark.asyncio
async def test_build_swap_tx_invalid_json():
    """Test error handling when wallet assistant returns invalid JSON."""
    mock_build_swap_tx = MagicMock(return_value="not json at all")

    mock_module = MagicMock()
    mock_module._build_swap_tx = mock_build_swap_tx
    sys.modules["wallet_assistant_crypto_agent"] = mock_module

    services = SimpleNamespace()
    ctx = ToolCtx(services=services, user_id=0, wallet="0xabc")

    result = await build_swap_tx(
        ctx,
        chain_id=56,
        token_in="BNB",
        token_out="USDT",
        amount_in="1000000000000000000",
        from_addr="0xabc",
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "swap_failed"


@pytest.mark.asyncio
async def test_build_swap_tx_exception():
    """Test error handling when wallet assistant raises an exception."""
    mock_build_swap_tx = MagicMock(side_effect=RuntimeError("Network timeout"))

    mock_module = MagicMock()
    mock_module._build_swap_tx = mock_build_swap_tx
    sys.modules["wallet_assistant_crypto_agent"] = mock_module

    services = SimpleNamespace()
    ctx = ToolCtx(services=services, user_id=0, wallet="0xabc")

    result = await build_swap_tx(
        ctx,
        chain_id=56,
        token_in="BNB",
        token_out="USDT",
        amount_in="1000000000000000000",
        from_addr="0xabc",
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "swap_failed"
    assert "Network timeout" in result.error.message
