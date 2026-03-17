"""Historical snapshot helpers for DeFi opportunities."""

from __future__ import annotations

import math
import time
from statistics import mean
from typing import Any, Dict, List, Sequence, Tuple

from src.data.defillama import DefiLlamaClient
from src.defi.stores.evidence_store import EvidenceStore


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _delta(values: Sequence[float], window: int) -> float:
    if len(values) <= window:
        return 0.0
    old = values[-window - 1]
    new = values[-1]
    if abs(old) < 1e-9:
        return 0.0
    return round(((new - old) / max(abs(old), 1.0)) * 100, 2)


def _coefficient_of_variation(values: Sequence[float]) -> float:
    cleaned = [value for value in values if value is not None]
    if len(cleaned) < 2:
        return 0.0
    avg = mean(cleaned)
    if abs(avg) < 1e-9:
        return 0.0
    variance = mean((value - avg) ** 2 for value in cleaned)
    return round(math.sqrt(max(variance, 0.0)) / abs(avg), 4)


def _max_drawdown_pct(values: Sequence[float]) -> float:
    peak = None
    drawdown = 0.0
    for value in values:
        numeric = _safe_float(value)
        if peak is None or numeric > peak:
            peak = numeric
        if peak and peak > 0:
            drawdown = max(drawdown, ((peak - numeric) / peak) * 100)
    return round(drawdown, 2)


def _recent_drop_pct(values: Sequence[float], lookback: int = 7) -> float:
    if len(values) < 2:
        return 0.0
    window = list(values[-max(lookback, 2):])
    peak = max(window)
    latest = window[-1]
    if peak <= 0:
        return 0.0
    return round(max(0.0, ((peak - latest) / peak) * 100), 2)


def _trend_score(delta_pct: float, drawdown_pct: float, cv: float) -> int:
    score = 70 + min(18.0, delta_pct * 0.18)
    score -= min(28.0, max(drawdown_pct, 0.0) * 0.35)
    score -= min(22.0, max(cv, 0.0) * 35)
    return max(5, min(100, round(score)))


class DefiHistoryStore:
    def __init__(self, llama: DefiLlamaClient, evidence_store: EvidenceStore | None = None):
        self.llama = llama
        self.evidence_store = evidence_store or EvidenceStore()
        self._cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}

    async def get_pool_history(self, pool_id: str) -> List[Dict[str, Any]]:
        if not pool_id:
            return []
        cached = self._cache.get(pool_id)
        now = time.time()
        if cached and (now - cached[0]) < 1800:
            return cached[1]

        stored = await self.evidence_store.get_pool_history(pool_id)
        if stored is not None:
            history = list(stored)[-90:]
            self._cache[pool_id] = (now, history)
            return history

        points = await self.llama.get_pool_chart(pool_id)
        history = list(points or [])[-90:]
        self._cache[pool_id] = (now, history)
        await self.evidence_store.save_pool_history(pool_id, history)
        return history

    def summarize_pool_history(self, history: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        if not history:
            return {
                "available": False,
                "points": [],
                "observations": 0,
                "apy_change_pct": 0.0,
                "tvl_change_pct": 0.0,
                "apy_delta_7d": 0.0,
                "apy_delta_30d": 0.0,
                "tvl_delta_7d": 0.0,
                "tvl_delta_30d": 0.0,
                "apy_persistence_score": 30,
                "apy_cv": 0.0,
                "tvl_cv": 0.0,
                "apy_drawdown_pct": 0.0,
                "tvl_drawdown_pct": 0.0,
                "recent_apy_drop_pct": 0.0,
                "recent_tvl_drop_pct": 0.0,
                "apy_trend_score": 30,
                "tvl_trend_score": 30,
            }

        apy_values = [_safe_float(item.get("apy")) for item in history if item.get("apy") is not None]
        tvl_values = [
            _safe_float(item.get("tvlUsd") or item.get("tvl_usd"))
            for item in history
            if item.get("tvlUsd") is not None or item.get("tvl_usd") is not None
        ]

        apy_cv = _coefficient_of_variation(apy_values[-30:])
        tvl_cv = _coefficient_of_variation(tvl_values[-30:])
        apy_drawdown = _max_drawdown_pct(apy_values[-60:] or apy_values)
        tvl_drawdown = _max_drawdown_pct(tvl_values[-60:] or tvl_values)
        recent_apy_drop = _recent_drop_pct(apy_values, 7)
        recent_tvl_drop = _recent_drop_pct(tvl_values, 7)
        apy_delta_30d = _delta(apy_values, 30)
        tvl_delta_30d = _delta(tvl_values, 30)
        persistence = self._apy_persistence_score(apy_values)

        return {
            "available": True,
            "points": list(history),
            "observations": len(history),
            "apy_change_pct": _delta(apy_values, len(apy_values) - 1) if len(apy_values) >= 2 else 0.0,
            "tvl_change_pct": _delta(tvl_values, len(tvl_values) - 1) if len(tvl_values) >= 2 else 0.0,
            "apy_delta_7d": _delta(apy_values, 7),
            "apy_delta_30d": apy_delta_30d,
            "tvl_delta_7d": _delta(tvl_values, 7),
            "tvl_delta_30d": tvl_delta_30d,
            "apy_persistence_score": persistence,
            "apy_cv": apy_cv,
            "tvl_cv": tvl_cv,
            "apy_drawdown_pct": apy_drawdown,
            "tvl_drawdown_pct": tvl_drawdown,
            "recent_apy_drop_pct": recent_apy_drop,
            "recent_tvl_drop_pct": recent_tvl_drop,
            "apy_trend_score": _trend_score(apy_delta_30d, apy_drawdown, apy_cv),
            "tvl_trend_score": _trend_score(tvl_delta_30d, tvl_drawdown, tvl_cv),
        }

    def _apy_persistence_score(self, apy_values: Sequence[float]) -> int:
        if len(apy_values) < 5:
            return 40
        recent = list(apy_values[-30:])
        cv = _coefficient_of_variation(recent)
        drawdown = _max_drawdown_pct(recent)
        latest_gap = abs(recent[-1] - mean(recent[-7:])) / max(abs(mean(recent[-7:])), 1.0) if len(recent) >= 7 else cv
        score = 90 - (cv * 60) - (drawdown * 0.18) - (latest_gap * 28)
        return max(10, min(100, round(score)))
