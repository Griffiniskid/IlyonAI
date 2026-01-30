"""
Analytics module for advanced token analysis.

This module provides innovative security features including:
- Developer Wallet Forensics: Track wallets across multiple token launches
- Behavioral Anomaly Detection: Predictive rug pull detection using time-series analysis
"""

from src.analytics.wallet_forensics import (
    WalletForensicsEngine,
    WalletForensicsResult,
)
from src.analytics.anomaly_detector import (
    BehavioralAnomalyDetector,
    AnomalyDetectionResult,
)
from src.analytics.time_series import (
    TimeSeriesDataPoint,
    TimeSeriesCollector,
)

__all__ = [
    "WalletForensicsEngine",
    "WalletForensicsResult",
    "BehavioralAnomalyDetector",
    "AnomalyDetectionResult",
    "TimeSeriesDataPoint",
    "TimeSeriesCollector",
]
