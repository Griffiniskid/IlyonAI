from typing import Any, Dict, Iterable, List, Optional

from src.analytics.signal_models import BehaviorSignals, EntityHeuristic, SignalFlag
from src.quality.feedback_store import FeedbackStore


class BehaviorSignalBuilder:
    def __init__(self, feedback_store: Optional[FeedbackStore] = None) -> None:
        self._feedback_store = feedback_store

    def build(
        self,
        whale_summary: Optional[Dict[str, Any]] = None,
        concentration: Optional[Dict[str, Any]] = None,
        anomalies: Optional[Iterable[Dict[str, Any]]] = None,
        heuristics: Optional[Iterable[Dict[str, Any]]] = None,
        usefulness_votes: Optional[Dict[str, bool]] = None,
    ) -> BehaviorSignals:
        whale_summary = whale_summary or {}
        concentration = concentration or {}

        signals = BehaviorSignals(
            whale_flow_direction=self._flow_direction(whale_summary),
            capital_concentration_score=round(float(concentration.get("top_wallet_share", 0.0)) * 100, 2),
            wallet_stickiness_score=round(float(whale_summary.get("repeat_wallet_share", 0.0)) * 100, 2),
            anomaly_flags=self._flags(anomalies or []),
            entity_heuristics=self._heuristics(heuristics or []),
        )
        self._record_usefulness_votes(signals, usefulness_votes or {})
        return signals

    def _flow_direction(self, whale_summary: Dict[str, Any]) -> str:
        net_flow = float(whale_summary.get("net_flow_usd", 0.0) or 0.0)
        buys = int(whale_summary.get("buy_count", 0) or 0)
        sells = int(whale_summary.get("sell_count", 0) or 0)

        if net_flow > 0 and buys >= sells:
            return "accumulating"
        if net_flow < 0 and sells >= buys:
            return "distributing"
        if buys == sells == 0:
            return "neutral"
        return "mixed"

    def _flags(self, anomalies: Iterable[Dict[str, Any]]) -> List[SignalFlag]:
        return [
            SignalFlag(
                code=str(item.get("code") or item.get("pattern") or item.get("anomaly_type") or "unknown"),
                severity=str(item.get("severity") or "medium").lower(),
                description=str(item.get("description") or ""),
                metadata=dict(item.get("metadata") or {}),
            )
            for item in anomalies
        ]

    def _heuristics(self, heuristics: Iterable[Dict[str, Any]]) -> List[EntityHeuristic]:
        return [
            EntityHeuristic(
                code=str(item.get("code") or "unknown"),
                severity=str(item.get("severity") or "medium").lower(),
                confidence=float(item.get("confidence") or 0.0),
                description=str(item.get("description") or ""),
                metadata=dict(item.get("metadata") or {}),
            )
            for item in heuristics
        ]

    def _record_usefulness_votes(self, signals: BehaviorSignals, usefulness_votes: Dict[str, bool]) -> None:
        if not self._feedback_store or not usefulness_votes:
            return

        for flag in signals.anomaly_flags:
            vote = usefulness_votes.get(flag.code)
            if isinstance(vote, bool):
                self._feedback_store.record(signal_code=flag.code, useful=vote)

        for heuristic in signals.entity_heuristics:
            vote = usefulness_votes.get(heuristic.code)
            if isinstance(vote, bool):
                self._feedback_store.record(signal_code=heuristic.code, useful=vote)
