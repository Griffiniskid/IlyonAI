"""Tests for wallet_lp wrapper around the wallet assistant _build_deposit_lp_tx."""
import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.agent.tools._base import ToolCtx
from src.agent.tools.wallet_lp import build_deposit_lp_tx


@pytest.fixture(autouse=True)
def _clean_modules():
    """Remove mock module from sys.modules after each test."""
    yield
    sys.modules.pop("wallet_assistant_crypto_agent", None)


@pytest.mark.asyncio
async def test_build_lp_returns_signing_payload():
    """Successful LP deposit returns ok envelope with card_type='lp'."""
    mock_build_deposit_lp_tx = MagicMock(return_value=json.dumps({
        "unsigned_tx": {"to": "0xLP", "data": "0x..."},
        "protocol": "curve",
        "amount_a": "1000",
        "amount_b": "1000",
        "spender": "0xLP",
    }))

    mock_module = MagicMock()
    mock_module._build_deposit_lp_tx = mock_build_deposit_lp_tx
    sys.modules["wallet_assistant_crypto_agent"] = mock_module

    services = SimpleNamespace()
    ctx = ToolCtx(services=services, user_id=1, wallet="0xU")

    env = await build_deposit_lp_tx(
        ctx,
        protocol="curve",
        token_a="USDC",
        token_b="USDT",
        amount_a="1000",
        amount_b="1000",
        user_addr="0xU",
    )

    assert env.ok is True
    assert env.card_type == "lp"
    assert env.card_payload is not None
    assert env.card_payload["pair"] == "USDC/USDT"
    assert env.card_payload["protocol"] == "curve"
    assert env.card_payload["amount_a"] == "1000"
    assert env.card_payload["amount_b"] == "1000"
    assert env.card_payload["spender"] == "0xLP"
    assert env.card_payload["requires_signature"] is True
    assert env.card_payload["steps"] == [
        {
            "step": 1,
            "action": "deposit_lp",
            "detail": "Deposit LP USDC/USDT on curve",
        }
    ]

    mock_build_deposit_lp_tx.assert_called_once()
    call_args = mock_build_deposit_lp_tx.call_args
    # raw_input is positional or keyword, user_address + default_chain_id are kw-eligible
    raw_input = call_args.args[0] if call_args.args else call_args.kwargs.get("raw")
    assert "1000" in raw_input
    assert "USDC" in raw_input
    assert "USDT" in raw_input
    assert "curve" in raw_input


@pytest.mark.asyncio
async def test_build_lp_default_chain_id():
    """Default chain_id=1 is forwarded to the assistant."""
    captured = {}

    def _fake(raw, user_address, default_chain_id):
        captured["raw"] = raw
        captured["user_address"] = user_address
        captured["default_chain_id"] = default_chain_id
        return json.dumps({
            "unsigned_tx": {"to": "0xLP"},
            "protocol": "curve",
            "amount_a": "1",
            "amount_b": "1",
        })

    mock_module = MagicMock()
    mock_module._build_deposit_lp_tx = _fake
    sys.modules["wallet_assistant_crypto_agent"] = mock_module

    services = SimpleNamespace()
    ctx = ToolCtx(services=services, user_id=1, wallet="0xU")

    env = await build_deposit_lp_tx(
        ctx,
        protocol="curve",
        token_a="USDC",
        token_b="USDT",
        amount_a="1",
        amount_b="1",
        user_addr="0xU",
    )

    assert env.ok is True
    assert captured["user_address"] == "0xU"
    assert captured["default_chain_id"] == 1


@pytest.mark.asyncio
async def test_build_lp_invalid_json_returns_err():
    """Invalid JSON from assistant produces an err envelope code='lp_failed'."""
    mock_module = MagicMock()
    mock_module._build_deposit_lp_tx = MagicMock(return_value="not json at all")
    sys.modules["wallet_assistant_crypto_agent"] = mock_module

    services = SimpleNamespace()
    ctx = ToolCtx(services=services, user_id=1, wallet="0xU")

    env = await build_deposit_lp_tx(
        ctx,
        protocol="curve",
        token_a="USDC",
        token_b="USDT",
        amount_a="1",
        amount_b="1",
        user_addr="0xU",
    )

    assert env.ok is False
    assert env.error is not None
    assert env.error.code == "lp_failed"


@pytest.mark.asyncio
async def test_build_lp_assistant_exception_returns_err():
    """Exception from the assistant produces an err envelope code='lp_failed'."""
    mock_module = MagicMock()
    mock_module._build_deposit_lp_tx = MagicMock(side_effect=RuntimeError("boom"))
    sys.modules["wallet_assistant_crypto_agent"] = mock_module

    services = SimpleNamespace()
    ctx = ToolCtx(services=services, user_id=1, wallet="0xU")

    env = await build_deposit_lp_tx(
        ctx,
        protocol="curve",
        token_a="USDC",
        token_b="USDT",
        amount_a="1",
        amount_b="1",
        user_addr="0xU",
    )

    assert env.ok is False
    assert env.error is not None
    assert env.error.code == "lp_failed"
    assert "boom" in env.error.message
