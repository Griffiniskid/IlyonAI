from __future__ import annotations

from typing import Any

from src.defi.contracts import BehaviorSummary, OpportunityAnalysis


def assemble_opportunity_analysis(
    *,
    identity: dict[str, Any],
    market: dict[str, Any],
    scores: dict[str, Any],
    factors: list[dict[str, Any]] | None = None,
    behavior: dict[str, Any] | None = None,
    scenarios: list[dict[str, Any]] | None = None,
    recommendation: dict[str, Any],
    evidence: list[dict[str, Any]] | None = None,
) -> OpportunityAnalysis:
    return OpportunityAnalysis.model_validate(
        {
            "identity": identity,
            "market": market,
            "scores": scores,
            "factors": factors or [],
            "behavior": behavior or BehaviorSummary().model_dump(),
            "scenarios": scenarios or [],
            "recommendation": recommendation,
            "evidence": evidence or [],
        }
    )
