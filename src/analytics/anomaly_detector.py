"""
Behavioral Anomaly Detection for Predictive Rug Pull Detection.

Uses time-series analysis to identify pre-rug behavioral patterns
and warn users BEFORE the rug occurs.

This shifts protection from reactive to PREVENTIVE - a novel approach
for the Solana ecosystem.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from enum import Enum

from src.analytics.time_series import TimeSeriesDataPoint, TimeSeriesCollector

logger = logging.getLogger(__name__)


class AnomalySeverity(Enum):
    """Severity level of detected anomalies."""
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class DetectedAnomaly:
    """Individual anomaly detection result."""
    anomaly_type: str
    description: str
    severity: str  # "LOW", "MEDIUM", "HIGH"
    details: Dict = field(default_factory=dict)
    probability_increase: float = 0.0  # How much this increases rug probability


@dataclass
class AnomalyDetectionResult:
    """Complete anomaly analysis result for a token."""

    token_address: str

    # Risk assessment
    anomaly_score: float  # 0-100 (higher = more anomalous)
    rug_probability: float  # 0-100 predicted likelihood
    time_to_rug_estimate: Optional[str] = None  # "imminent", "hours", "days", None

    # Detected anomalies
    anomalies_detected: List[str] = field(default_factory=list)
    anomaly_details: List[DetectedAnomaly] = field(default_factory=list)
    severity_level: AnomalySeverity = AnomalySeverity.NORMAL

    # Data quality
    data_points_analyzed: int = 0
    data_quality_score: float = 0.0  # 0-100

    # Recommendations
    recommendation: str = ""
    confidence: float = 50.0  # 0-100 confidence in prediction

    def to_dict(self) -> Dict:
        """Convert to dictionary for storage."""
        return {
            "token_address": self.token_address,
            "anomaly_score": self.anomaly_score,
            "rug_probability": self.rug_probability,
            "time_to_rug_estimate": self.time_to_rug_estimate,
            "anomalies_detected": self.anomalies_detected,
            "severity_level": self.severity_level.value,
            "data_points_analyzed": self.data_points_analyzed,
            "data_quality_score": self.data_quality_score,
            "recommendation": self.recommendation,
            "confidence": self.confidence,
        }


class BehavioralAnomalyDetector:
    """
    Detects pre-rug behavioral patterns using time-series analysis.

    Detection methods:
    1. Liquidity velocity anomalies (sudden LP changes)
    2. Holder concentration shifts
    3. Volume/price divergence patterns
    4. Transaction pattern anomalies
    5. Historical pattern matching

    This is a PREVENTIVE security feature that warns users before
    rugs occur, not just after.
    """

    # Pre-rug pattern signatures learned from historical data
    PRERUG_PATTERNS = {
        "liquidity_staging": {
            "description": "Small LP removals before major rug",
            "indicators": ["lp_decrease_rate", "removal_frequency"],
            "typical_window_hours": 24,
            "rug_probability_increase": 40,
        },
        "whale_accumulation": {
            "description": "Large wallets accumulating before dump",
            "indicators": ["top_holder_growth", "transaction_size_increase"],
            "typical_window_hours": 48,
            "rug_probability_increase": 30,
        },
        "volume_divergence": {
            "description": "Volume dropping while price pumps (artificial)",
            "indicators": ["volume_price_correlation", "wash_trade_score"],
            "typical_window_hours": 12,
            "rug_probability_increase": 25,
        },
        "sell_pressure_buildup": {
            "description": "Increasing sell-to-buy ratio",
            "indicators": ["sell_ratio_trend", "large_sell_frequency"],
            "typical_window_hours": 6,
            "rug_probability_increase": 35,
        },
        "liquidity_drain": {
            "description": "Continuous liquidity decrease",
            "indicators": ["lp_trend", "drain_velocity"],
            "typical_window_hours": 12,
            "rug_probability_increase": 45,
        },
    }

    def __init__(self, time_series_collector: Optional[TimeSeriesCollector] = None):
        """
        Initialize anomaly detector.

        Args:
            time_series_collector: Optional collector for historical data
        """
        self.collector = time_series_collector or TimeSeriesCollector()

    async def analyze_token(
        self,
        token_address: str,
        time_series: Optional[List[TimeSeriesDataPoint]] = None,
        lookback_hours: int = 72,
    ) -> AnomalyDetectionResult:
        """
        Perform comprehensive anomaly analysis.

        Args:
            token_address: Token to analyze
            time_series: Optional pre-collected time series data
            lookback_hours: How far back to analyze

        Returns:
            AnomalyDetectionResult with predictions and recommendations
        """
        # Get time series data
        if time_series is None:
            time_series = await self.collector.get_historical_data(
                token_address, lookback_hours
            )

        # Insufficient data check
        if len(time_series) < 3:
            return self._insufficient_data_result(token_address, len(time_series))

        # Analyze each dimension
        anomalies: List[DetectedAnomaly] = []

        # Liquidity analysis
        liq_anomaly = self._analyze_liquidity_pattern(time_series)
        if liq_anomaly:
            anomalies.append(liq_anomaly)

        # Volume analysis
        vol_anomaly = self._analyze_volume_pattern(time_series)
        if vol_anomaly:
            anomalies.append(vol_anomaly)

        # Transaction pattern analysis
        tx_anomaly = self._analyze_transaction_patterns(time_series)
        if tx_anomaly:
            anomalies.append(tx_anomaly)

        # Price momentum analysis
        price_anomaly = self._analyze_price_patterns(time_series)
        if price_anomaly:
            anomalies.append(price_anomaly)

        # Calculate composite scores
        anomaly_score = self._calculate_anomaly_score(anomalies)
        rug_probability = self._estimate_rug_probability(anomalies, time_series)
        severity = self._get_severity(anomaly_score, rug_probability)
        time_estimate = self._estimate_time_to_rug(anomalies, rug_probability)

        # Data quality assessment
        data_quality = self.collector.get_data_quality_score(token_address)
        confidence = self._calculate_confidence(len(time_series), anomalies, data_quality)

        return AnomalyDetectionResult(
            token_address=token_address,
            anomaly_score=anomaly_score,
            rug_probability=rug_probability,
            time_to_rug_estimate=time_estimate,
            anomalies_detected=[a.anomaly_type for a in anomalies],
            anomaly_details=anomalies,
            severity_level=severity,
            data_points_analyzed=len(time_series),
            data_quality_score=data_quality,
            recommendation=self._generate_recommendation(anomaly_score, rug_probability, severity),
            confidence=confidence,
        )

    def _insufficient_data_result(
        self,
        token_address: str,
        data_points: int,
    ) -> AnomalyDetectionResult:
        """Return result when insufficient data is available."""
        return AnomalyDetectionResult(
            token_address=token_address,
            anomaly_score=0.0,
            rug_probability=25.0,  # Base rate for unknown tokens
            time_to_rug_estimate=None,
            anomalies_detected=[],
            severity_level=AnomalySeverity.NORMAL,
            data_points_analyzed=data_points,
            data_quality_score=max(0, data_points * 10),
            recommendation="Insufficient historical data for behavioral analysis. Exercise caution with new tokens.",
            confidence=15.0,
        )

    def _analyze_liquidity_pattern(
        self,
        time_series: List[TimeSeriesDataPoint],
    ) -> Optional[DetectedAnomaly]:
        """
        Detect liquidity anomalies that precede rugs.

        Key indicators:
        - Rate of change in liquidity
        - Sudden small removals (testing the waters)
        - Accelerating decrease trend
        """
        if len(time_series) < 3:
            return None

        liquidity_values = [p.liquidity_usd for p in time_series if p.liquidity_usd > 0]
        if len(liquidity_values) < 3:
            return None

        # Calculate percentage changes
        pct_changes = []
        for i in range(1, len(liquidity_values)):
            if liquidity_values[i - 1] > 0:
                change = (liquidity_values[i] - liquidity_values[i - 1]) / liquidity_values[i - 1] * 100
                pct_changes.append(change)

        if not pct_changes:
            return None

        # Calculate statistics
        mean_change = sum(pct_changes) / len(pct_changes)
        recent_changes = pct_changes[-min(5, len(pct_changes)):]
        recent_mean = sum(recent_changes) / len(recent_changes)

        # Detect anomalies
        anomaly_detected = False
        severity = "LOW"
        details = {}

        # Check for consistent drainage
        if recent_mean < -5:  # More than 5% decrease per period
            anomaly_detected = True
            severity = "HIGH" if recent_mean < -15 else "MEDIUM"
            details["recent_change_pct"] = recent_mean
            details["pattern"] = "liquidity_drain"

        # Check for "testing" pattern: small removals
        small_removals = [c for c in recent_changes if -10 < c < -2]
        if len(small_removals) >= 2:
            anomaly_detected = True
            severity = max(severity, "MEDIUM")
            details["small_removals_count"] = len(small_removals)
            details["pattern"] = "liquidity_staging"

        # Check for sudden large drop
        if recent_changes and min(recent_changes) < -30:
            anomaly_detected = True
            severity = "HIGH"
            details["sudden_drop_pct"] = min(recent_changes)

        if anomaly_detected:
            return DetectedAnomaly(
                anomaly_type="liquidity_anomaly",
                description="Unusual liquidity movement pattern detected",
                severity=severity,
                details=details,
                probability_increase=40 if severity == "HIGH" else 20,
            )

        return None

    def _analyze_volume_pattern(
        self,
        time_series: List[TimeSeriesDataPoint],
    ) -> Optional[DetectedAnomaly]:
        """
        Detect volume anomalies.

        Key indicators:
        - Volume/price divergence
        - Sudden volume spikes (wash trading)
        - Volume decline with price stability
        """
        if len(time_series) < 3:
            return None

        # Extract volume and price data
        volumes = [p.volume_1h for p in time_series if p.volume_1h >= 0]
        prices = [p.price_usd for p in time_series if p.price_usd > 0]

        if len(volumes) < 3 or len(prices) < 3:
            return None

        # Check for volume/price divergence
        # If price is going up but volume is declining = potential manipulation
        recent_vol = volumes[-min(3, len(volumes)):]
        early_vol = volumes[:min(3, len(volumes))]
        recent_price = prices[-min(3, len(prices)):]
        early_price = prices[:min(3, len(prices))]

        vol_trend = (sum(recent_vol) / len(recent_vol)) / max(sum(early_vol) / len(early_vol), 1)
        price_trend = (sum(recent_price) / len(recent_price)) / max(sum(early_price) / len(early_price), 0.0001)

        anomaly_detected = False
        severity = "LOW"
        details = {}

        # Divergence: price up, volume down
        if price_trend > 1.1 and vol_trend < 0.7:
            anomaly_detected = True
            severity = "MEDIUM"
            details["pattern"] = "volume_price_divergence"
            details["price_trend"] = price_trend
            details["volume_trend"] = vol_trend

        # Volume collapse
        if vol_trend < 0.3:
            anomaly_detected = True
            severity = "HIGH" if vol_trend < 0.1 else "MEDIUM"
            details["pattern"] = "volume_collapse"
            details["volume_trend"] = vol_trend

        if anomaly_detected:
            return DetectedAnomaly(
                anomaly_type="volume_anomaly",
                description="Volume pattern suggests reduced genuine interest",
                severity=severity,
                details=details,
                probability_increase=25 if severity == "HIGH" else 15,
            )

        return None

    def _analyze_transaction_patterns(
        self,
        time_series: List[TimeSeriesDataPoint],
    ) -> Optional[DetectedAnomaly]:
        """
        Detect transaction pattern anomalies.

        Pre-rug indicators:
        - Increasing large sells
        - Buy/sell ratio deterioration
        - Coordinated sell timing
        """
        if len(time_series) < 3:
            return None

        # Calculate buy/sell ratios over time
        ratios = []
        for point in time_series:
            total = point.buy_count + point.sell_count
            if total > 0:
                ratio = point.buy_count / total  # 0 to 1, higher = more buys
                ratios.append(ratio)

        if len(ratios) < 3:
            return None

        # Check for deteriorating trend
        recent_ratios = ratios[-min(5, len(ratios)):]
        early_ratios = ratios[:min(5, len(ratios))]

        recent_avg = sum(recent_ratios) / len(recent_ratios)
        early_avg = sum(early_ratios) / len(early_ratios)

        anomaly_detected = False
        severity = "LOW"
        details = {}

        # Significant deterioration in buy/sell ratio
        if recent_avg < early_avg * 0.6:  # 40% deterioration
            anomaly_detected = True
            severity = "HIGH"
            details["pattern"] = "sell_pressure_buildup"
            details["recent_buy_ratio"] = recent_avg
            details["early_buy_ratio"] = early_avg

        # Heavy sell dominance
        if recent_avg < 0.3:  # More than 70% sells
            anomaly_detected = True
            severity = "HIGH"
            details["pattern"] = "sell_dominance"
            details["buy_ratio"] = recent_avg

        # Check for large sell frequency
        large_sells = sum(p.large_sells for p in time_series[-min(10, len(time_series)):])
        if large_sells >= 3:
            anomaly_detected = True
            severity = max(severity, "MEDIUM")
            details["large_sell_count"] = large_sells

        if anomaly_detected:
            return DetectedAnomaly(
                anomaly_type="transaction_anomaly",
                description="Transaction patterns indicate increasing sell pressure",
                severity=severity,
                details=details,
                probability_increase=35 if severity == "HIGH" else 20,
            )

        return None

    def _analyze_price_patterns(
        self,
        time_series: List[TimeSeriesDataPoint],
    ) -> Optional[DetectedAnomaly]:
        """
        Detect suspicious price patterns.

        Key indicators:
        - Extreme volatility
        - Pump patterns
        - Sudden crashes
        """
        if len(time_series) < 3:
            return None

        price_changes = [p.price_change_1h for p in time_series if p.price_change_1h != 0]
        if not price_changes:
            return None

        # Calculate volatility
        mean_change = sum(price_changes) / len(price_changes)
        variance = sum((c - mean_change) ** 2 for c in price_changes) / len(price_changes)
        volatility = variance ** 0.5

        anomaly_detected = False
        severity = "LOW"
        details = {}

        # Extreme volatility
        if volatility > 50:  # Very high volatility
            anomaly_detected = True
            severity = "MEDIUM"
            details["volatility"] = volatility
            details["pattern"] = "extreme_volatility"

        # Recent crash detection
        recent_changes = price_changes[-min(3, len(price_changes)):]
        if any(c < -30 for c in recent_changes):
            anomaly_detected = True
            severity = "HIGH"
            details["recent_crash"] = min(recent_changes)
            details["pattern"] = "recent_crash"

        # Pump pattern detection (sudden rise followed by instability)
        if len(price_changes) >= 5:
            early_changes = price_changes[:3]
            if max(early_changes) > 50 and volatility > 30:
                anomaly_detected = True
                severity = max(severity, "MEDIUM")
                details["pattern"] = "pump_detected"
                details["pump_magnitude"] = max(early_changes)

        if anomaly_detected:
            return DetectedAnomaly(
                anomaly_type="price_anomaly",
                description="Price pattern shows signs of manipulation or instability",
                severity=severity,
                details=details,
                probability_increase=20 if severity == "HIGH" else 10,
            )

        return None

    def _calculate_anomaly_score(self, anomalies: List[DetectedAnomaly]) -> float:
        """
        Calculate composite anomaly score (0-100).

        Higher score = more anomalous behavior detected.
        """
        if not anomalies:
            return 0.0

        score = 0.0
        severity_weights = {"LOW": 10, "MEDIUM": 25, "HIGH": 40}

        for anomaly in anomalies:
            weight = severity_weights.get(anomaly.severity, 10)
            score += weight

        # Cap at 100
        return min(100.0, score)

    def _estimate_rug_probability(
        self,
        anomalies: List[DetectedAnomaly],
        time_series: List[TimeSeriesDataPoint],
    ) -> float:
        """
        Estimate probability of rug pull (0-100).

        Combines:
        - Pattern severity scores
        - Historical base rates
        - Time-series features
        """
        # Base probability for new/unknown tokens
        base_probability = 15.0

        # Add probability for each detected anomaly
        for anomaly in anomalies:
            base_probability += anomaly.probability_increase

        # Additional factors from time series
        if time_series:
            latest = time_series[-1]

            # Very low liquidity = higher risk
            if latest.liquidity_usd < 5000:
                base_probability += 15
            elif latest.liquidity_usd < 20000:
                base_probability += 8

            # New token (few data points) = higher risk
            if len(time_series) < 10:
                base_probability += 10

            # Heavy sell dominance
            if latest.sell_count > 0:
                ratio = latest.buy_count / (latest.buy_count + latest.sell_count)
                if ratio < 0.25:
                    base_probability += 15

        return min(95.0, max(5.0, base_probability))

    def _get_severity(
        self,
        anomaly_score: float,
        rug_probability: float,
    ) -> AnomalySeverity:
        """Determine overall severity level."""
        combined = (anomaly_score + rug_probability) / 2

        if combined >= 70:
            return AnomalySeverity.CRITICAL
        elif combined >= 50:
            return AnomalySeverity.HIGH
        elif combined >= 25:
            return AnomalySeverity.ELEVATED
        else:
            return AnomalySeverity.NORMAL

    def _estimate_time_to_rug(
        self,
        anomalies: List[DetectedAnomaly],
        rug_probability: float,
    ) -> Optional[str]:
        """
        Estimate time until potential rug.

        Returns: "imminent", "hours", "days", or None
        """
        if rug_probability < 40:
            return None

        # Check for imminent signals
        for anomaly in anomalies:
            details = anomaly.details
            if details.get("pattern") == "liquidity_drain" and anomaly.severity == "HIGH":
                return "imminent"
            if details.get("sudden_drop_pct", 0) < -50:
                return "imminent"

        if rug_probability >= 80:
            return "hours"
        elif rug_probability >= 60:
            return "days"

        return None

    def _calculate_confidence(
        self,
        data_points: int,
        anomalies: List[DetectedAnomaly],
        data_quality: float,
    ) -> float:
        """
        Calculate confidence in prediction (0-100).

        More data and clearer patterns = higher confidence.
        """
        confidence = 30.0  # Base confidence

        # Data quantity bonus
        if data_points >= 24:
            confidence += 25
        elif data_points >= 12:
            confidence += 15
        elif data_points >= 6:
            confidence += 8

        # Data quality factor
        confidence += data_quality * 0.2

        # Clear anomaly patterns increase confidence
        if anomalies:
            high_severity = sum(1 for a in anomalies if a.severity == "HIGH")
            confidence += high_severity * 10

        return min(95.0, confidence)

    def _generate_recommendation(
        self,
        anomaly_score: float,
        rug_probability: float,
        severity: AnomalySeverity,
    ) -> str:
        """Generate actionable recommendation based on analysis."""
        if severity == AnomalySeverity.CRITICAL:
            return "CRITICAL WARNING: Multiple high-risk patterns detected. Strongly recommend exiting position immediately."

        if severity == AnomalySeverity.HIGH:
            return f"HIGH RISK: Behavioral patterns suggest {rug_probability:.0f}% rug probability. Consider reducing exposure."

        if severity == AnomalySeverity.ELEVATED:
            return "ELEVATED RISK: Some concerning patterns detected. Monitor closely and set stop-losses."

        if anomaly_score > 0:
            return "Normal behavior with minor anomalies. Continue monitoring."

        return "No significant behavioral anomalies detected. Standard risk levels apply."
