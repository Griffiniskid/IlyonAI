from __future__ import annotations

from dataclasses import dataclass

from src.api.schemas.agent import SentinelBlock
from src.allocator.composer import (
    PoolCandidate,
    bucket_fit,
    bucket_risk,
    derive_flags,
    score_confidence,
    score_durability,
    score_exit,
    score_safety,
    weighted_sentinel,
)


@dataclass(frozen=True)
class PoolSentinelScore:
    safety: int
    durability: int
    exit: int
    confidence: int
    weighted: int
    risk_level: str
    strategy_fit: str
    flags: list[str]
    breakdown_explainer: str


def score_pool_candidate(pool: PoolCandidate) -> PoolSentinelScore:
    safety = score_safety(pool)
    durability = score_durability(pool)
    exit_score = score_exit(pool)
    confidence = score_confidence(pool)
    weighted = weighted_sentinel(safety, durability, exit_score, confidence)
    risk_level = bucket_risk(weighted)
    strategy_fit = bucket_fit(weighted, pool.apy)
    flags = derive_flags(pool, weighted)
    explainer = (
        f"Safety {safety}, durability {durability}, exit {exit_score}, "
        f"confidence {confidence}; weighted Sentinel {weighted}/100."
    )
    return PoolSentinelScore(
        safety=safety,
        durability=durability,
        exit=exit_score,
        confidence=confidence,
        weighted=weighted,
        risk_level=risk_level,
        strategy_fit=strategy_fit,
        flags=flags,
        breakdown_explainer=explainer,
    )


def sentinel_block_from_candidate(pool: PoolCandidate) -> SentinelBlock:
    score = score_pool_candidate(pool)
    return SentinelBlock(
        sentinel=score.weighted,
        safety=score.safety,
        durability=score.durability,
        exit=score.exit,
        confidence=score.confidence,
        risk_level=score.risk_level.upper(),
        strategy_fit=score.strategy_fit,
        flags=score.flags,
    )
