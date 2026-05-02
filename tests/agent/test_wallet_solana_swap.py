import json
import pytest

from src.agent.tools._base import ToolCtx
from src.agent.tools.wallet_solana_swap import build_solana_swap


@pytest.mark.asyncio
async def test_build_solana_swap(monkeypatch):
    fake = json.dumps({
        "unsigned_tx": {"serialized": "...base64..."},
        "rate": "180.5",
        "pay": {"symbol": "SOL", "amount": "1.0"},
        "receive": {"symbol": "USDC", "amount": "180.5"},
        "price_impact_pct": 0.1,
    })
    monkeypatch.setattr(
        "IlyonAi_Wallet_assistant_main.server.app.agents.crypto_agent.build_solana_swap",
        lambda raw: fake,
        raising=True,
    )
    ctx = ToolCtx(services=type("S", (), {})(), user_id=1, wallet="SoLAddr")
    env = await build_solana_swap(
        ctx, token_in="SOL", token_out="USDC", amount_in="1.0", from_addr="SoLAddr",
    )
    assert env.ok
    assert env.card_payload["chain"] == "solana"
    assert env.card_payload["router"] == "Jupiter"
