import json
import pytest

# Import the assistant module directly (the conftest namespace stub for
# IlyonAi_Wallet_assistant_main does not bind sub-attributes, so we monkeypatch
# the resolved module object instead of using a dotted-string path).
from IlyonAi_Wallet_assistant_main.server.app.agents import crypto_agent

from src.agent.tools._base import ToolCtx
from src.agent.tools.wallet_balance import get_wallet_balance


@pytest.mark.asyncio
async def test_get_wallet_balance(monkeypatch):
    fake = json.dumps({
        "total_usd": 1234.5,
        "by_chain": {"ethereum": "1000", "arbitrum": "234.5"},
        "tokens": [{"symbol": "USDC", "amount": "234.5"}],
    })
    monkeypatch.setattr(
        crypto_agent,
        "get_smart_wallet_balance",
        lambda addr, user_address="", solana_address="": fake,
        raising=True,
    )
    ctx = ToolCtx(services=type("S", (), {})(), user_id=1, wallet="0xUser")
    env = await get_wallet_balance(ctx, wallet="0xUser")
    assert env.ok
    assert env.card_payload["total_usd"] == 1234.5
