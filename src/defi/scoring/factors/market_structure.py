from __future__ import annotations

from typing import Any, Dict, Sequence

from src.defi.evidence import clamp


def score_market_structure(kind: str, candidate: Dict[str, Any], assets: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    product_type = str(candidate.get("product_type") or "")
    score = 58
    if "stable" in product_type:
        score += 26
    elif "crypto_stable" in product_type:
        score += 12
    elif kind == "lending":
        score += 18
    elif kind == "vault":
        score += 8
    if str(candidate.get("il_risk") or "").lower() == "yes":
        score -= 14
    reward_share = max(float(candidate.get("apy_reward") or 0.0), 0.0) / max(float(candidate.get("apy") or candidate.get("apy_supply") or 0.0), 0.01)
    score -= reward_share * 14
    underlying_assets = [asset for asset in assets if asset.get("role") != "reward"] or list(assets)
    if underlying_assets:
        average_quality = sum(float(asset.get("quality_score") or 55) for asset in underlying_assets) / len(underlying_assets)
        stable_share = sum(1 for asset in underlying_assets if asset.get("is_stable")) / len(underlying_assets)
        major_share = sum(1 for asset in underlying_assets if asset.get("is_major")) / len(underlying_assets)
        average_depeg = sum(float(asset.get("depeg_risk") or 0) for asset in underlying_assets) / len(underlying_assets)
        average_wrapper = sum(float(asset.get("wrapper_risk") or 0) for asset in underlying_assets) / len(underlying_assets)
        average_volatility = sum(float(asset.get("volatility_24h") or 0) for asset in underlying_assets) / len(underlying_assets)
        score += (average_quality - 55.0) * 0.45
        score += stable_share * 8.0
        score += major_share * 6.0
        score -= average_depeg * 0.45
        score -= average_wrapper * 0.35
        score -= average_volatility * 0.50
    return {"score": clamp(score), "burden": clamp(100 - score), "notes": ["Exposure mix, asset quality, stable-major mix, and depeg-wrapper-volatility drag."]}
