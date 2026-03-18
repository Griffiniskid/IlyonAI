from datetime import datetime, timedelta

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
    assert summary["repeat_wallet_share"] == 0.25


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
