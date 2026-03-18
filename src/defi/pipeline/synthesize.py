from __future__ import annotations

from typing import Any

from src.defi.assemblers.opportunity_analysis import assemble_opportunity_analysis
from src.defi.scoring.ai_judgment import build_ai_judgment_score
from src.defi.scoring.final_ranker import blend_final_score, recommend_action


class SynthesisPipeline:
    def combine(
        self,
        *,
        identity: dict[str, Any] | None = None,
        market: dict[str, Any] | None = None,
        deterministic: dict[str, Any],
        ai: dict[str, Any] | None = None,
        factors: list[dict[str, Any]] | None = None,
        behavior: dict[str, Any] | None = None,
        scenarios: list[dict[str, Any]] | None = None,
        evidence: list[dict[str, Any]] | None = None,
    ):
        identity = identity or {
            "id": "unknown-opportunity",
            "chain": "unknown",
            "kind": "unknown",
            "protocol_slug": "unknown",
        }
        market = market or {"market_regime": "unknown"}

        ai_bundle = dict(ai or {})
        if "judgment_score" not in ai_bundle:
            ai_bundle = build_ai_judgment_score(
                {
                    "protocol": identity.get("protocol_slug"),
                    "chain": identity.get("chain"),
                    "gross_apr": deterministic.get("gross_apr"),
                    "risk_to_apr_ratio": deterministic.get("risk_to_apr_ratio"),
                    "evidence_confidence": deterministic.get("confidence_score"),
                }
            )

        hard_caps = deterministic.get("hard_caps") or []
        evidence_confidence = _int_value(deterministic, "confidence_score", default=0)
        deterministic_score = _int_value(deterministic, "final_score", fallback_key="overall_score", default=0)
        ai_judgment_score = _int_value(ai_bundle, "judgment_score", default=0)
        final_score = blend_final_score(deterministic_score, ai_judgment_score, evidence_confidence, hard_caps)
        action, size = recommend_action(final_score, hard_caps)

        rationale = list(ai_bundle.get("main_risks") or [])
        if not rationale:
            rationale = [deterministic.get("headline") or "Combined deterministic and AI synthesis completed."]
        if hard_caps:
            rationale.insert(0, _cap_reason(hard_caps[0]))

        return assemble_opportunity_analysis(
            identity=identity,
            market=market,
            scores={
                "deterministic_score": deterministic_score,
                "ai_judgment_score": ai_judgment_score,
                "final_deployability_score": final_score,
                "safety_score": _int_value(deterministic, "safety_score", default=deterministic_score),
                "apr_quality_score": _int_value(deterministic, "apr_quality_score", default=deterministic_score),
                "exit_quality_score": _int_value(deterministic, "exit_quality_score", default=deterministic_score),
                "resilience_score": _int_value(deterministic, "resilience_score", default=deterministic_score),
                "confidence_score": evidence_confidence,
                "capped_score": final_score if hard_caps else None,
            },
            factors=factors,
            behavior=behavior,
            scenarios=scenarios,
            recommendation={
                "action": action,
                "rationale": rationale,
                "deployment_size_pct": size,
                "monitor_triggers": list(ai_bundle.get("monitor_triggers") or []),
            },
            evidence=evidence,
        )


def _cap_reason(cap: dict[str, Any] | str) -> str:
    if isinstance(cap, str):
        return cap.replace("_", " ")
    return str(cap.get("reason") or cap.get("code") or "hard cap applied")


def _int_value(source: dict[str, Any], key: str, *, fallback_key: str | None = None, default: int) -> int:
    value = source.get(key)
    if value is None and fallback_key is not None:
        value = source.get(fallback_key)
    if value is None:
        value = default
    return int(value)
