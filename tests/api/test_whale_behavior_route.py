import json
from types import SimpleNamespace

import pytest

from src.api.routes import whale
from src.api.schemas.responses import WhaleActivityResponse


@pytest.mark.asyncio
async def test_token_whale_route_includes_anomaly_flags_and_entity_heuristics(monkeypatch):
    whale._whale_cache.clear()
    whale._whale_cache_locks.clear()

    class DexStub:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get_token(self, token_address):
            return {"main": {"baseToken": {"symbol": "FOO", "name": "Foo"}}}

    class SolanaStub:
        def __init__(self, rpc_url, helius_api_key):
            self.rpc_url = rpc_url
            self.helius_api_key = helius_api_key

        async def get_behavior_transactions(self, **kwargs):
            return [
                {
                    "signature": "sig-1",
                    "wallet_address": "wallet-1",
                    "token_address": kwargs["token_address"],
                    "token_symbol": "FOO",
                    "token_name": "Foo",
                    "type": "buy",
                    "amount_tokens": 10,
                    "amount_usd": 100000,
                    "price_usd": 10,
                    "timestamp": "2026-03-18T00:00:00+00:00",
                    "dex_name": "Raydium",
                    "anomaly_flags": [{"code": "liquidity_drain", "severity": "high"}],
                    "entity_heuristics": [{"code": "deployer_retained_supply", "severity": "medium", "confidence": 0.8}],
                }
            ]

        async def close(self):
            return None

    monkeypatch.setattr(whale, "DexScreenerClient", DexStub)
    monkeypatch.setattr(whale, "SolanaClient", SolanaStub)

    request = SimpleNamespace(
        match_info={"address": "token-1"},
        query={"force_refresh": "1"},
    )

    response = await whale.get_whale_activity_for_token(request)
    payload = json.loads(response.text)

    assert payload["behavior"]["anomaly_flags"][0]["code"] == "liquidity_drain"
    assert payload["behavior"]["entity_heuristics"][0]["code"] == "deployer_retained_supply"


def test_whale_activity_response_schema_includes_behavior_payload():
    payload = WhaleActivityResponse(
        transactions=[],
        behavior={
            "whale_flow_direction": "accumulating",
            "capital_concentration_score": 40,
            "wallet_stickiness_score": 50,
            "anomaly_flags": [{"code": "liquidity_drain", "severity": "high"}],
            "entity_heuristics": [{"code": "deployer_retained_supply", "severity": "medium", "confidence": 0.8}],
        },
    ).model_dump(mode="json")

    assert payload["behavior"]["anomaly_flags"][0]["code"] == "liquidity_drain"
    assert payload["behavior"]["entity_heuristics"][0]["code"] == "deployer_retained_supply"
