import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.agent.tools._base import ToolCtx
from src.agent.tools.wallet_stake import build_stake_tx


@pytest.fixture(autouse=True)
def _clean_modules():
    """Remove mock module from sys.modules after each test."""
    yield
    sys.modules.pop("wallet_assistant_crypto_agent", None)


@pytest.mark.asyncio
async def test_build_stake_tx_success():
    """Test successful stake tx building via wallet assistant."""
    mock_build_stake_tx = MagicMock(return_value=json.dumps({
        "status": "ok",
        "action": "stake",
        "protocol": "lido",
        "asset": "ETH",
        "amount": "1.0",
        "spender": "0xStakeContract",
        "unsigned_tx": {
            "to": "0xStakeContract",
            "data": "0xabcd",
            "value": "0x0",
        },
    }))

    mock_module = MagicMock()
    mock_module._build_stake_tx = mock_build_stake_tx
    sys.modules["wallet_assistant_crypto_agent"] = mock_module

    services = SimpleNamespace()
    ctx = ToolCtx(services=services, user_id=0, wallet="0xUser")

    result = await build_stake_tx(
        ctx,
        protocol="lido",
        amount="1.0",
        user_addr="0xUser",
        chain_id=1,
        asset="ETH",
    )

    assert result.ok is True
    assert result.card_type == "stake"
    assert result.card_payload is not None
    assert result.card_payload["protocol"] == "lido"
    assert result.card_payload["asset"] == "ETH"
    assert result.card_payload["amount"] == "1.0"
    assert result.card_payload["spender"] == "0xStakeContract"
    assert result.card_payload["requires_signature"] is True
    assert result.card_payload["steps"] == [
        {
            "step": 1,
            "action": "stake",
            "detail": "Stake 1.0 on lido",
        }
    ]
    assert result.data is not None
    assert result.data["status"] == "ok"
    assert result.data["action"] == "stake"

    mock_build_stake_tx.assert_called_once()
    call_args = mock_build_stake_tx.call_args[0]
    parsed_input = json.loads(call_args[0])
    assert parsed_input["token"] == "ETH"
    assert parsed_input["protocol"] == "lido"
    assert parsed_input["amount"] == "1.0"
    assert parsed_input["chain_id"] == 1
    assert call_args[1] == "0xUser"
    assert call_args[2] == 1


@pytest.mark.asyncio
async def test_build_stake_tx_no_asset():
    """Test stake tx building without explicit asset."""
    mock_build_stake_tx = MagicMock(return_value=json.dumps({
        "status": "ok",
        "action": "stake",
        "protocol": "lido",
        "asset": "ETH",
        "amount": "1.0",
        "spender": "0xStakeContract",
        "unsigned_tx": {
            "to": "0xStakeContract",
            "data": "0xabcd",
            "value": "0x0",
        },
    }))

    mock_module = MagicMock()
    mock_module._build_stake_tx = mock_build_stake_tx
    sys.modules["wallet_assistant_crypto_agent"] = mock_module

    services = SimpleNamespace()
    ctx = ToolCtx(services=services, user_id=0, wallet="0xUser")

    result = await build_stake_tx(
        ctx,
        protocol="lido",
        amount="1.0",
        user_addr="0xUser",
        chain_id=1,
    )

    assert result.ok is True
    assert result.card_type == "stake"
    assert result.card_payload["protocol"] == "lido"
    assert result.card_payload["asset"] == "ETH"


@pytest.mark.asyncio
async def test_build_stake_tx_error():
    """Test error handling when wallet assistant returns an error."""
    mock_build_stake_tx = MagicMock(return_value=json.dumps({
        "status": "error",
        "message": "No staking protocols available for UNKNOWN on chain 1.",
    }))

    mock_module = MagicMock()
    mock_module._build_stake_tx = mock_build_stake_tx
    sys.modules["wallet_assistant_crypto_agent"] = mock_module

    services = SimpleNamespace()
    ctx = ToolCtx(services=services, user_id=0, wallet="0xUser")

    result = await build_stake_tx(
        ctx,
        protocol="unknown",
        amount="1.0",
        user_addr="0xUser",
        chain_id=1,
        asset="UNKNOWN",
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "stake_failed"
    assert "No staking protocols available" in result.error.message


@pytest.mark.asyncio
async def test_build_stake_tx_invalid_json():
    """Test error handling when wallet assistant returns invalid JSON."""
    mock_build_stake_tx = MagicMock(return_value="not json at all")

    mock_module = MagicMock()
    mock_module._build_stake_tx = mock_build_stake_tx
    sys.modules["wallet_assistant_crypto_agent"] = mock_module

    services = SimpleNamespace()
    ctx = ToolCtx(services=services, user_id=0, wallet="0xUser")

    result = await build_stake_tx(
        ctx,
        protocol="lido",
        amount="1.0",
        user_addr="0xUser",
        chain_id=1,
        asset="ETH",
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "stake_failed"


@pytest.mark.asyncio
async def test_build_stake_tx_exception():
    """Test error handling when wallet assistant raises an exception."""
    mock_build_stake_tx = MagicMock(side_effect=RuntimeError("Network timeout"))

    mock_module = MagicMock()
    mock_module._build_stake_tx = mock_build_stake_tx
    sys.modules["wallet_assistant_crypto_agent"] = mock_module

    services = SimpleNamespace()
    ctx = ToolCtx(services=services, user_id=0, wallet="0xUser")

    result = await build_stake_tx(
        ctx,
        protocol="lido",
        amount="1.0",
        user_addr="0xUser",
        chain_id=1,
        asset="ETH",
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "stake_failed"
    assert "Network timeout" in result.error.message
