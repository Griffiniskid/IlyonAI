"""Pass 1 market scan normalization for DeFi candidates."""

from __future__ import annotations

from typing import Any, Dict, List

from src.defi.opportunity_taxonomy import PHASE_1_CHAINS, classify_defi_record, normalize_chain_name


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


class MarketScanPipeline:
    SUPPORTED_CHAINS = PHASE_1_CHAINS

    def normalize_chain_name(self, chain: Any) -> str | None:
        return normalize_chain_name(chain)

    def normalize_candidates(
        self,
        *,
        pools: List[Dict[str, Any]],
        yields: List[Dict[str, Any]],
        markets: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        candidates.extend(self._normalize_pool(pool) for pool in pools)
        candidates.extend(self._normalize_yield(item) for item in yields)
        candidates.extend(self._normalize_lending_supply(item) for item in markets)
        return candidates

    def _normalize_pool(self, pool: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self._normalize_candidate(pool, apy_key="apy")
        normalized["candidate_kind"] = "pool"
        return normalized

    def _normalize_yield(self, item: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self._normalize_candidate(item, apy_key="apy")
        normalized["candidate_kind"] = "yield"
        return normalized

    def _normalize_lending_supply(self, item: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self._normalize_candidate(item, apy_key="apy_supply")
        normalized["candidate_kind"] = "lending_supply"
        normalized.setdefault("product_type", "lending_supply_like")
        return normalized

    def _normalize_candidate(self, item: Dict[str, Any], *, apy_key: str) -> Dict[str, Any]:
        classification = classify_defi_record(item)
        apy = _safe_float(item.get(apy_key) if apy_key in item else item.get("apy"))
        tvl = _safe_float(item.get("tvlUsd", item.get("tvl_usd", 0)))
        chain = self.normalize_chain_name(item.get("chain"))
        project = item.get("project") or item.get("protocol") or "unknown"
        normalized = {
            **item,
            "project": project,
            "protocol": item.get("protocol") or project,
            "chain": chain,
            "apy": apy,
            "tvlUsd": tvl,
            "product_type": classification.get("product_type") or item.get("product_type"),
            "candidate_kind": classification.get("candidate_kind") or classification.get("default_kind") or "yield",
            "shortlist_score": self._shortlist_score(apy=apy, tvl=tvl, chain=chain),
        }
        return normalized

    def _shortlist_score(self, *, apy: float, tvl: float, chain: str | None) -> int:
        score = min(max(apy, 0.0), 40.0)
        if tvl >= 10_000_000:
            score += 30
        elif tvl >= 1_000_000:
            score += 20
        elif tvl >= 100_000:
            score += 10
        if chain in self.SUPPORTED_CHAINS:
            score += 10
        return round(score)
