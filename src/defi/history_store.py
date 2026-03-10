"""Historical snapshot helpers for DeFi opportunities."""

from __future__ import annotations

import time
from statistics import mean
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.data.defillama import DefiLlamaClient


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


class DefiHistoryStore:
    def __init__(self, llama: DefiLlamaClient):
        self.llama = llama
        self._cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}

    async def get_pool_history(self, pool_id: str) -> List[Dict[str, Any]]:
        if not pool_id:
            return []
        cached = self._cache.get(pool_id)
        now = time.time()
        if cached and (now - cached[0]) < 1800:
            return cached[1]

        points = await self.llama.get_pool_chart(pool_id)
        history = list(points or [])[-90:]
        self._cache[pool_id] = (now, history)
        return history

    def summarize_pool_history(self, history: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        if not history:
            return {
                "available": False,
                "points": [],
                "apy_change_pct": 0.0,
                "tvl_change_pct": 0.0,
                "apy_delta_7d": 0.0,
                "apy_delta_30d": 0.0,
                "tvl_delta_7d": 0.0,
                "tvl_delta_30d": 0.0,
                "apy_persistence_score": 35,
            }

        apy_values = [_safe_float(item.get("apy")) for item in history if item.get("apy") is not None]
        tvl_values = [_safe_float(item.get("tvlUsd") or item.get("tvl_usd")) for item in history if item.get("tvlUsd") is not None or item.get("tvl_usd") is not None]

        def delta(values: Sequence[float], window: int) -> float:
            if len(values) <= window:
                return 0.0
            old = values[-window - 1]
            new = values[-1]
            if abs(old) < 1e-9:
                return 0.0
            return round(((new - old) / max(abs(old), 1.0)) * 100, 2)

        persistence = self._apy_persistence_score(apy_values)
        return {
            "available": True,
            "points": list(history),
            "apy_change_pct": delta(apy_values, len(apy_values) - 1) if len(apy_values) >= 2 else 0.0,
            "tvl_change_pct": delta(tvl_values, len(tvl_values) - 1) if len(tvl_values) >= 2 else 0.0,
            "apy_delta_7d": delta(apy_values, 7),
            "apy_delta_30d": delta(apy_values, 30),
            "tvl_delta_7d": delta(tvl_values, 7),
            "tvl_delta_30d": delta(tvl_values, 30),
            "apy_persistence_score": persistence,
        }

    def _apy_persistence_score(self, apy_values: Sequence[float]) -> int:
        if len(apy_values) < 5:
            return 45
        avg = max(mean(apy_values), 1.0)
        volatility = mean(abs(value - avg) for value in apy_values[-30:]) / avg
        drift = abs(apy_values[-1] - mean(apy_values[-7:])) / avg if len(apy_values) >= 7 else volatility
        score = 82 - (volatility * 55) - (drift * 35)
        return max(15, min(100, round(score)))
