from __future__ import annotations

from typing import Any

from src.api.schemas.agent import SentinelBlock


def score_token_mapping(token: dict[str, Any]) -> SentinelBlock:
    symbol = str(token.get("symbol") or token.get("token") or "").upper()
    major = symbol in {"BTC", "ETH", "SOL", "USDC", "USDT", "DAI", "BNB", "MATIC", "AVAX"}
    score = 85 if major else 58
    return SentinelBlock(
        sentinel=score,
        safety=score,
        durability=score if major else 55,
        exit=90 if major else 50,
        confidence=85 if major else 45,
        risk_level="LOW" if score >= 82 else ("MEDIUM" if score >= 65 else "HIGH"),
        strategy_fit="balanced" if major else "aggressive",
        flags=[] if major else ["Long-tail token"],
    )
