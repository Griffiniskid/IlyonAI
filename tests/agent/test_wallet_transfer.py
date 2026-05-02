import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.agent.tools._base import ToolCtx
from src.agent.tools.wallet_transfer import build_transfer_tx


@pytest.fixture(autouse=True)
def _clean_modules():
    """Remove mock module from sys.modules after each test."""
    yield
    sys.modules.pop("wallet_assistant_crypto_agent", None)


@pytest.mark.asyncio
async def test_build_transfer_returns_payload():
    """Test successful transfer tx building via wallet assistant."""
    mock_build_transfer = MagicMock(return_value=json.dumps({
        "unsigned_tx": {
            "to": "0xRecipient",
            "value": "1000000000000000000",
        },
        "amount": "1.0",
    }))

    mock_module = MagicMock()
    mock_module._build_transfer_transaction = mock_build_transfer
    sys.modules["wallet_assistant_crypto_agent"] = mock_module

    services = SimpleNamespace()
    ctx = ToolCtx(services=services, user_id=1, wallet="0xSender")

    env = await build_transfer_tx(
        ctx,
        to_addr="0xRecipient",
        amount="1.0",
        chain="ethereum",
        from_addr="0xSender",
    )

    assert env.ok
    assert env.card_type == "transfer"
    assert env.card_payload["to"] == "0xRecipient"
