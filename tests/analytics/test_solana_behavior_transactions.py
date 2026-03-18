from datetime import datetime, timedelta, timezone

import pytest

from src.data.solana import SolanaClient


@pytest.mark.asyncio
async def test_behavior_transactions_add_real_anomaly_flags_and_entity_heuristics(monkeypatch):
    client = SolanaClient(rpc_url="https://rpc.example", helius_api_key="key")
    start = datetime(2026, 3, 18, tzinfo=timezone.utc)
    transactions = []

    for index in range(10):
        is_buy = index < 5
        transactions.append(
            {
                "signature": f"sig-{index}",
                "wallet_address": "deployer-wallet" if index < 4 else ("cluster-wallet" if index < 8 else f"wallet-{index}"),
                "token_address": "token-1",
                "token_symbol": "FOO",
                "token_name": "Foo",
                "type": "buy" if is_buy else "sell",
                "amount_tokens": 10,
                "amount_usd": 100000 if index < 8 else 20000,
                "price_usd": 10,
                "timestamp": (start + timedelta(minutes=index)).isoformat(),
                "dex_name": "Raydium",
            }
        )

    async def fake_whale_transactions(**kwargs):
        return transactions

    async def fake_deployer(token_address, solana_rpc_url):
        return "deployer-wallet"

    monkeypatch.setattr(client, "get_token_whale_transactions", fake_whale_transactions)
    monkeypatch.setattr("src.data.solana.get_token_deployer", fake_deployer)

    result = await client.get_behavior_transactions("token-1", limit=10)

    assert any(flag["code"] == "sell_pressure_buildup" for flag in result[0]["anomaly_flags"])
    assert any(item["code"] == "deployer_retained_supply" for item in result[0]["entity_heuristics"])
