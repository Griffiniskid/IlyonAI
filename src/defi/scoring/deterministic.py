from __future__ import annotations

from typing import Any, Dict

from src.defi.evidence import clamp, parse_age_hours, risk_level_from_score
from src.defi.scoring.archetypes.farm import config as farm_config
from src.defi.scoring.archetypes.lending_supply import config as lending_supply_config
from src.defi.scoring.archetypes.lp import config as lp_config
from src.defi.scoring.archetypes.vault import config as vault_config
from src.defi.scoring.factors.apr_quality import score_apr_quality
from src.defi.scoring.factors.behavior import score_behavior
from src.defi.scoring.factors.chain_risk import score_chain_risk
from src.defi.scoring.factors.confidence import score_confidence
from src.defi.scoring.factors.exit_quality import score_exit_quality
from src.defi.scoring.factors.market_structure import score_market_structure
from src.defi.scoring.factors.position_risk import score_position_risk
from src.defi.scoring.factors.protocol_integrity import score_protocol_integrity


class DeterministicScorer:
    def __init__(self, public_ranking_default: str = "balanced"):
        self.public_ranking_default = public_ranking_default

    def score(self, kind: str, candidate: Dict[str, Any], context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        context = context or {}
        archetype = self._archetype_for(kind, candidate)
        cfg = self._config_for(archetype)
        assets = context.get("assets") or []
        protocol = score_protocol_integrity(context)
        market = score_market_structure(kind, candidate, assets)
        apr = score_apr_quality(candidate, context.get("history") or {})
        position = score_position_risk(kind, candidate)
        exit_quality = score_exit_quality(kind, candidate)
        behavior_context = context.get("behavior") or candidate.get("behavior") or {}
        behavior = score_behavior(behavior_context)
        chain = score_chain_risk(candidate, context)
        confidence = score_confidence(kind, candidate, context)
        incident_effect = self._incident_effect(context.get("incidents") or [])

        factors = {
            "protocol": protocol,
            "market": market,
            "apr": apr,
            "position": position,
            "exit": exit_quality,
            "behavior": behavior,
            "chain": chain,
            "confidence": confidence,
        }
        weighted_quality = self._weighted_score(factors, cfg["weights"], "score")
        weighted_risk_burden = self._weighted_score(factors, cfg["weights"], "burden")
        safety_score = clamp((protocol["score"] * 0.45) + (market["score"] * 0.20) + (position["score"] * 0.15) + (chain["score"] * 0.10) + (behavior["score"] * 0.10))
        yield_durability = clamp((apr["score"] * 0.65) + (confidence["score"] * 0.20) + (behavior["score"] * 0.15))
        exit_score = exit_quality["score"]
        weighted_risk_burden = clamp(weighted_risk_burden + incident_effect["risk_burden_penalty"])
        safety_score = clamp(safety_score - incident_effect["safety_penalty"])
        if incident_effect["recent_critical"]:
            safety_score = min(safety_score, 42)
        elif incident_effect["has_incident"]:
            safety_score = min(safety_score, 60)

        gross_apr = apr["gross_apr"]
        extreme_apr_penalty = 0.0
        if archetype == "farm":
            extreme_apr_penalty = min(0.55, max(0.0, gross_apr - 80.0) / 180.0)
        haircut_penalty = min(0.92, apr["haircut_penalty"] + behavior["haircut_penalty"] + extreme_apr_penalty + incident_effect["haircut_penalty"])
        haircut_apr = round(max(0.0, gross_apr * (1.0 - haircut_penalty)), 2)
        net_expected_apr = round(max(0.0, haircut_apr - (weighted_risk_burden * cfg["net_apr_burden_rate"])), 2)
        required_apr = round(
            max(
                0.5,
                (weighted_risk_burden * cfg["net_apr_burden_rate"])
                + 1.0
                + (apr["reward_share"] * (10.0 if archetype == "farm" else 4.0))
                + (max(0.0, gross_apr - 25.0) * (0.14 if archetype == "farm" else 0.03)),
            ),
            2,
        )
        apr_efficiency = self._apr_efficiency_score(haircut_apr, required_apr)
        overall_score = self._overall_score(
            context.get("ranking_profile") or self.public_ranking_default,
            weighted_quality,
            safety_score,
            yield_durability,
            exit_score,
            apr_efficiency,
            confidence["score"],
        )
        if archetype == "farm" and apr_efficiency < 35:
            overall_score = min(overall_score, 34)
        if incident_effect["recent_critical"]:
            overall_score = min(overall_score, 32)

        fragility_flags = list(behavior["fragility_flags"])
        kill_switches = list(behavior["kill_switches"])
        if incident_effect["recent_critical"]:
            fragility_flags.append("recent_critical_incident")
            kill_switches.append("recent_critical_incident")
        elif incident_effect["has_incident"]:
            fragility_flags.append("incident_history")

        summary = {
            "overall_score": overall_score,
            "quality_score": weighted_quality,
            "opportunity_score": overall_score,
            "safety_score": safety_score,
            "risk_burden_score": weighted_risk_burden,
            "yield_durability_score": yield_durability,
            "yield_quality_score": yield_durability,
            "exit_liquidity_score": exit_score,
            "exit_quality_score": exit_score,
            "apr_efficiency_score": apr_efficiency,
            "effective_apr": haircut_apr,
            "required_apr": required_apr,
            "return_potential_score": apr_efficiency,
            "confidence_score": confidence["score"],
            "risk_level": risk_level_from_score(100 - safety_score),
            "strategy_fit": self._best_fit_profile(safety_score, weighted_risk_burden),
            "headline": cfg["headline"],
            "thesis": cfg["thesis"],
            "gross_apr": gross_apr,
            "haircut_apr": haircut_apr,
            "net_expected_apr": net_expected_apr,
            "weighted_risk_burden": weighted_risk_burden,
            "risk_to_apr_ratio": round(weighted_risk_burden / max(haircut_apr, 0.1), 4),
            "fragility_flags": fragility_flags,
            "kill_switches": kill_switches,
            "best_fit_risk_profile": self._best_fit_profile(safety_score, weighted_risk_burden),
            "confidence_reasoning": confidence["report"]["notes"],
        }
        dimensions = [
            self._dimension("overall_score", "Overall Score", overall_score, 1.0, "Blended deterministic deployment score."),
            self._dimension("protocol_safety", "Protocol Safety", protocol["score"], cfg["weights"]["protocol"], protocol["notes"][0]),
            self._dimension("structure_safety", "Structure Safety", market["score"], cfg["weights"]["market"], market["notes"][0]),
            self._dimension("yield_durability", "Yield Durability", yield_durability, cfg["weights"]["apr"], apr["notes"][0]),
            self._dimension("exit_liquidity", "Exit Liquidity", exit_score, cfg["weights"]["exit"], exit_quality["notes"][0]),
            self._dimension("behavior", "Behavior Signals", behavior["score"], cfg["weights"]["behavior"], behavior["notes"][0]),
            self._dimension("confidence", "Confidence", confidence["score"], cfg["weights"]["confidence"], confidence["notes"][0]),
            self._dimension("apr_efficiency", "APR Efficiency", apr_efficiency, 0.40, "Risk-adjusted APR after deterministic haircuts and burden hurdles."),
        ]
        score_caps = []
        if incident_effect["recent_critical"]:
            score_caps.append({"dimension": "safety", "cap": 42, "reason": "Recent critical incident caps deterministic safety until resilience is re-established."})
        elif incident_effect["has_incident"]:
            score_caps.append({"dimension": "safety", "cap": 60, "reason": "Incident history still caps deterministic safety."})
        return {"summary": summary, "dimensions": dimensions, "confidence": confidence["report"], "score_caps": score_caps}

    def _archetype_for(self, kind: str, candidate: Dict[str, Any]) -> str:
        if kind == "lending":
            return "lending_supply"
        if kind == "vault" or str(candidate.get("product_type") or "") == "vault":
            return "vault"
        if kind == "yield" or "incentivized" in str(candidate.get("product_type") or ""):
            return "farm"
        return "lp"

    def _config_for(self, archetype: str) -> Dict[str, Any]:
        if archetype == "farm":
            return farm_config()
        if archetype == "lending_supply":
            return lending_supply_config()
        if archetype == "vault":
            return vault_config()
        return lp_config()

    def _weighted_score(self, factors: Dict[str, Dict[str, Any]], weights: Dict[str, float], key: str) -> int:
        total = 0.0
        total_weight = 0.0
        for name, weight in weights.items():
            total += float(factors[name][key]) * weight
            total_weight += weight
        return clamp(total / max(total_weight, 1e-9))

    def _apr_efficiency_score(self, effective_apr: float, required_apr: float) -> int:
        ratio = effective_apr / max(required_apr, 0.01)
        if ratio >= 1.5:
            return 90
        if ratio >= 1.0:
            return clamp(65 + ((ratio - 1.0) * 50))
        if ratio >= 0.5:
            return clamp(35 + ((ratio - 0.5) * 60))
        return clamp(ratio * 70)

    def _overall_score(self, ranking_profile: str, quality_score: int, safety_score: int, yield_durability: int, exit_score: int, apr_efficiency: int, confidence_score: int) -> int:
        if ranking_profile == "conservative":
            return clamp(
                (apr_efficiency * 0.25)
                + (quality_score * 0.22)
                + (safety_score * 0.22)
                + (yield_durability * 0.10)
                + (exit_score * 0.14)
                + (confidence_score * 0.07)
            )
        return clamp(
            (apr_efficiency * 0.40)
            + (quality_score * 0.22)
            + (safety_score * 0.15)
            + (yield_durability * 0.10)
            + (exit_score * 0.08)
            + (confidence_score * 0.05)
        )

    def _best_fit_profile(self, safety_score: int, weighted_risk_burden: int) -> str:
        if safety_score >= 78 and weighted_risk_burden <= 28:
            return "conservative"
        if safety_score >= 62 and weighted_risk_burden <= 45:
            return "balanced"
        return "aggressive"

    def _dimension(self, key: str, label: str, score: int, weight: float, summary: str) -> Dict[str, Any]:
        return {"key": key, "label": label, "score": score, "weight": weight, "summary": summary}

    def _incident_effect(self, incidents: list[Dict[str, Any]]) -> Dict[str, Any]:
        safety_penalty = 0.0
        risk_burden_penalty = 0.0
        haircut_penalty = 0.0
        has_incident = False
        recent_critical = False
        for incident in incidents:
            severity = str(incident.get("severity") or "").lower()
            if severity not in {"critical", "high", "medium", "low"}:
                continue
            has_incident = True
            age_hours = parse_age_hours(incident.get("date"))
            freshness = 1.0
            if age_hours is not None:
                if age_hours > 24 * 365 * 2:
                    freshness = 0.35
                elif age_hours > 24 * 365:
                    freshness = 0.55
                elif age_hours > 24 * 180:
                    freshness = 0.8
            if severity == "critical" and (age_hours is None or age_hours <= 24 * 365):
                recent_critical = True
            severity_base = {"low": 4.0, "medium": 8.0, "high": 14.0, "critical": 22.0}[severity]
            safety_penalty += severity_base * freshness
            risk_burden_penalty += (severity_base * 0.85) * freshness
            haircut_penalty += min(0.24, (severity_base / 100.0) * freshness)
        return {
            "has_incident": has_incident,
            "recent_critical": recent_critical,
            "safety_penalty": safety_penalty,
            "risk_burden_penalty": risk_burden_penalty,
            "haircut_penalty": haircut_penalty,
        }
