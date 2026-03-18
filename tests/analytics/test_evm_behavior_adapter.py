from src.analytics.behavior_adapters.evm import EVMBehaviorAdapter


def test_evm_behavior_adapter_builds_first_layer_summary_from_transactions():
    adapter = EVMBehaviorAdapter()

    result = adapter.adapt(
        [
            {"wallet_address": "0xaaa", "type": "buy", "amount_usd": 90000},
            {"wallet_address": "0xaaa", "type": "buy", "amount_usd": 40000},
            {"wallet_address": "0xbbb", "type": "sell", "amount_usd": 20000},
            {"wallet_address": "0xccc", "type": "buy", "amount_usd": 10000},
        ]
    )

    assert result["whale_summary"]["net_flow_usd"] == 120000
    assert result["whale_summary"]["buy_count"] == 3
    assert result["concentration"]["top_wallet_share"] == 0.8125
    assert result["whale_summary"]["repeat_wallet_share"] == 0.5
