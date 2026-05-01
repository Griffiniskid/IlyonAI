import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.agent.tools._base import ToolCtx
from src.agent.tools.wallet_bridge import build_bridge_tx


@pytest.fixture(autouse=True)
def _clean_modules():
    """Remove mock module from sys.modules after each test."""
    yield
    sys.modules.pop("wallet_assistant_crypto_agent", None)


@pytest.mark.asyncio
async def test_build_bridge_tx_success():
    """Test successful bridge tx building via wallet assistant."""
    mock_build_bridge_tx = MagicMock(return_value=json.dumps({
        "status": "ok",
        "type": "bridge_proposal",
        "chain_type": "evm",
        "src_chain_id": 56,
        "dst_chain_id": 8453,
        "from_token_symbol": "BNB",
        "to_token_symbol": "USDC",
        "amount_in_display": 1.0,
        "dst_amount_display": 0.95,
        "route_summary": "deBridge DLN",
        "estimated_fill_time_seconds": 300,
        "tx": {
            "from": "0xabc",
            "to": "0xdef",
            "data": "0x123",
            "value": "0x0",
            "chain_id": 56,
        },
    }))

    mock_module = MagicMock()
    mock_module._build_bridge_tx = mock_build_bridge_tx
    sys.modules["wallet_assistant_crypto_agent"] = mock_module

    services = SimpleNamespace()
    ctx = ToolCtx(services=services, user_id=0, wallet="0xabc")

    result = await build_bridge_tx(
        ctx,
        src_chain_id=56,
        dst_chain_id=8453,
        token_in="BNB",
        token_out="USDC",
        amount="1000000000000000000",
        from_addr="0xabc",
    )

    assert result.ok is True
    assert result.card_type == "bridge"
    assert result.card_payload is not None
    assert result.card_payload["src_chain_id"] == 56
    assert result.card_payload["dst_chain_id"] == 8453
    assert result.card_payload["amount_in"] == 1.0
    assert result.card_payload["amount_out"] == 0.95
    assert result.card_payload["router"] == "debridge"
    assert result.card_payload["estimated_seconds"] == 300
    assert result.card_payload["spender"] == "0xdef"
    assert result.data is not None
    assert result.data["status"] == "ok"
    assert result.data["src_chain_id"] == 56

    mock_build_bridge_tx.assert_called_once()
    call_args = mock_build_bridge_tx.call_args[0]
    assert json.loads(call_args[0])["src_chain_id"] == 56
    assert call_args[1] == "0xabc"
    assert call_args[2] == 56


@pytest.mark.asyncio
async def test_build_bridge_tx_solana():
    """Test Solana bridge tx building via wallet assistant."""
    mock_build_bridge_tx = MagicMock(return_value=json.dumps({
        "status": "ok",
        "type": "bridge_proposal",
        "chain_type": "solana",
        "src_chain_id": 101,
        "dst_chain_id": 56,
        "from_token_symbol": "SOL",
        "to_token_symbol": "USDC",
        "amount_in_display": 1.0,
        "dst_amount_display": 0.98,
        "route_summary": "deBridge DLN",
        "estimated_fill_time_seconds": 180,
        "tx": {
            "serialized": "base64tx",
            "chain_id": 101,
        },
    }))

    mock_module = MagicMock()
    mock_module._build_bridge_tx = mock_build_bridge_tx
    sys.modules["wallet_assistant_crypto_agent"] = mock_module

    services = SimpleNamespace()
    ctx = ToolCtx(services=services, user_id=0, wallet="SolanaPubkey")

    result = await build_bridge_tx(
        ctx,
        src_chain_id=101,
        dst_chain_id=56,
        token_in="SOL",
        token_out="USDC",
        amount="1000000000",
        from_addr="SolanaPubkey",
    )

    assert result.ok is True
    assert result.card_type == "bridge"
    assert result.card_payload["src_chain_id"] == 101
    assert result.card_payload["dst_chain_id"] == 56
    assert result.card_payload["router"] == "debridge"
    assert result.card_payload["spender"] == ""
    assert result.card_payload["estimated_seconds"] == 180


@pytest.mark.asyncio
async def test_build_bridge_tx_error():
    """Test error handling when wallet assistant returns an error."""
    mock_build_bridge_tx = MagicMock(return_value=json.dumps({
        "status": "error",
        "message": "Insufficient liquidity",
    }))

    mock_module = MagicMock()
    mock_module._build_bridge_tx = mock_build_bridge_tx
    sys.modules["wallet_assistant_crypto_agent"] = mock_module

    services = SimpleNamespace()
    ctx = ToolCtx(services=services, user_id=0, wallet="0xabc")

    result = await build_bridge_tx(
        ctx,
        src_chain_id=56,
        dst_chain_id=8453,
        token_in="UNKNOWN",
        token_out="USDC",
        amount="1000000000000000000",
        from_addr="0xabc",
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "bridge_failed"
    assert "Insufficient liquidity" in result.error.message


@pytest.mark.asyncio
async def test_build_bridge_tx_invalid_json():
    """Test error handling when wallet assistant returns invalid JSON."""
    mock_build_bridge_tx = MagicMock(return_value="not json at all")

    mock_module = MagicMock()
    mock_module._build_bridge_tx = mock_build_bridge_tx
    sys.modules["wallet_assistant_crypto_agent"] = mock_module

    services = SimpleNamespace()
    ctx = ToolCtx(services=services, user_id=0, wallet="0xabc")

    result = await build_bridge_tx(
        ctx,
        src_chain_id=56,
        dst_chain_id=8453,
        token_in="BNB",
        token_out="USDC",
        amount="1000000000000000000",
        from_addr="0xabc",
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "bridge_failed"


@pytest.mark.asyncio
async def test_build_bridge_tx_exception():
    """Test error handling when wallet assistant raises an exception."""
    mock_build_bridge_tx = MagicMock(side_effect=RuntimeError("Network timeout"))

    mock_module = MagicMock()
    mock_module._build_bridge_tx = mock_build_bridge_tx
    sys.modules["wallet_assistant_crypto_agent"] = mock_module

    services = SimpleNamespace()
    ctx = ToolCtx(services=services, user_id=0, wallet="0xabc")

    result = await build_bridge_tx(
        ctx,
        src_chain_id=56,
        dst_chain_id=8453,
        token_in="BNB",
        token_out="USDC",
        amount="1000000000000000000",
        from_addr="0xabc",
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "bridge_failed"
    assert "Network timeout" in result.error.message
