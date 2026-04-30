from __future__ import annotations

from typing import Any

from src.api.schemas.agent import SentinelBlock, ShieldBlock
from src.scoring.shield_gate import shield_for_transaction


SCAM_TOKEN_HINTS = ("SCAM", "HONEYPOT", "MALICIOUS", "RUG")


def _risk_level(score: int) -> str:
    if score >= 82:
        return "LOW"
    if score >= 65:
        return "MEDIUM"
    return "HIGH"


def _route_sentinel_score(route: dict[str, Any], shield: ShieldBlock) -> SentinelBlock:
    router = str(route.get("router") or route.get("spender") or "").lower()
    token_out = str(route.get("token_out") or route.get("to_token") or route.get("receive_token") or "").upper()
    slippage = int(route.get("slippage_bps") or route.get("slippageBps") or 0)
    price_impact = float(route.get("price_impact_pct") or route.get("priceImpactPct") or 0)

    score = 80
    flags: list[str] = []
    if router and not any(name in router for name in ("enso", "jupiter", "uniswap", "curve", "debridge")):
        score -= 18
        flags.append("Unrecognized router")
    if any(hint in token_out for hint in SCAM_TOKEN_HINTS):
        score -= 35
        flags.append("Unaudited route token")
    if slippage > 500:
        score -= 15
        flags.append("High slippage")
    if price_impact > 1.0:
        score -= 10
        flags.append("High price impact")
    if shield.verdict in {"SCAM", "DANGEROUS"}:
        score = min(score, 40)
    score = max(0, min(100, score))
    return SentinelBlock(
        sentinel=score,
        safety=max(0, min(100, score - 5 if flags else score)),
        durability=max(0, min(100, score)),
        exit=max(0, min(100, score + 5)),
        confidence=max(0, min(100, score - 10 if flags else score)),
        risk_level=_risk_level(score),
        strategy_fit="balanced" if score >= 65 else "aggressive",
        flags=flags,
    )


def score_route_mapping(route: dict[str, Any]) -> tuple[SentinelBlock, ShieldBlock]:
    shield = shield_for_transaction(route)
    return _route_sentinel_score(route, shield), shield
