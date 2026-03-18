from datetime import datetime, timedelta

from src.analytics.behavior_adapters.evm import EVMBehaviorAdapter
from src.analytics.time_series import TimeSeriesDataPoint, TimeSeriesStore


def test_time_series_store_tracks_behavior_snapshots_and_repeat_wallet_share():
    store = TimeSeriesStore()
    now = datetime.utcnow()

    store.add_behavior_snapshot(
        "token-1",
        {
            "timestamp": now - timedelta(hours=1),
            "wallets": ["w1", "w2"],
        },
    )
    store.add_behavior_snapshot(
        "token-1",
        {
            "timestamp": now,
            "wallets": ["w1", "w3"],
        },
    )

    summary = store.get_behavior_summary("token-1")

    assert summary["snapshot_count"] == 2
    assert summary["repeat_wallet_share"] == 0.5


def test_time_series_store_repeat_wallet_share_matches_adapter_semantics():
    store = TimeSeriesStore()
    adapter = EVMBehaviorAdapter()

    wallets = ["w1", "w1", "w2", "w3"]
    store.add_behavior_snapshot("token-1", {"timestamp": datetime.utcnow(), "wallets": wallets})

    adapted = adapter.adapt(
        [
            {"wallet_address": wallet, "type": "buy", "amount_usd": 1}
            for wallet in wallets
        ]
    )

    assert store.get_behavior_summary("token-1")["repeat_wallet_share"] == adapted["whale_summary"]["repeat_wallet_share"]


def test_time_series_data_point_round_trips_whale_flow_fields():
    point = TimeSeriesDataPoint(
        timestamp=datetime.utcnow(),
        liquidity_usd=1000,
        whale_net_flow_usd=125000,
        repeat_wallet_share=0.4,
    )

    restored = TimeSeriesDataPoint.from_dict(point.to_dict())

    assert restored.whale_net_flow_usd == 125000
    assert restored.repeat_wallet_share == 0.4
