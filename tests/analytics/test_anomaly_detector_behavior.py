from datetime import datetime, timedelta

from src.analytics.anomaly_detector import BehavioralAnomalyDetector
from src.analytics.time_series import TimeSeriesDataPoint


def test_anomaly_detector_exposes_first_layer_behavior_flags():
    detector = BehavioralAnomalyDetector()
    now = datetime.utcnow()
    time_series = [
        TimeSeriesDataPoint(timestamp=now - timedelta(hours=2), liquidity_usd=100000, buy_count=8, sell_count=2),
        TimeSeriesDataPoint(timestamp=now - timedelta(hours=1), liquidity_usd=80000, buy_count=5, sell_count=4),
        TimeSeriesDataPoint(timestamp=now, liquidity_usd=50000, buy_count=1, sell_count=8, large_sells=3),
    ]

    result = detector.detect_behavior_flags(time_series)

    assert any(flag.code == "liquidity_drain" for flag in result)
    assert any(flag.code == "sell_pressure_buildup" for flag in result)
