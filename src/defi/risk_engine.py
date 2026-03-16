"""Deterministic DeFi scoring engine with richer differentiation and hard caps."""

from __future__ import annotations

import math
import re
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.defi.entities import RiskDimension, ScoreCap
from src.defi.evidence import build_confidence_report, clamp, parse_age_hours, risk_level_from_score

STABLE_SYMBOLS = {
    "USDC", "USDT", "DAI", "FRAX", "BUSD", "USDE", "USDS", "LUSD", "TUSD", "USDP", "FDUSD", "GHO", "USDBC"
}
MAJOR_SYMBOLS = {
    "ETH", "WETH", "WBTC", "BTC", "SOL", "STETH", "WSTETH", "CBETH", "CBBTC", "WEETH", "RETH", "SUSDE", "EZETH"
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_mean(values: Iterable[float], default: float = 0.0) -> float:
    cleaned = [float(value) for value in values if value is not None]
    return mean(cleaned) if cleaned else default


def _weighted_average(entries: Iterable[Tuple[float, float]], default: float = 0.0) -> float:
    total_weight = 0.0
    total_value = 0.0
    for value, weight in entries:
        total_value += value * weight
        total_weight += weight
    return (total_value / total_weight) if total_weight > 0 else default


def _log_scale(value: float, low: float, high: float) -> float:
    numeric = max(_safe_float(value), 1.0)
    lower = max(low, 1.0)
    upper = max(high, lower + 1.0)
    ratio = (math.log10(numeric) - math.log10(lower)) / max(math.log10(upper) - math.log10(lower), 1e-9)
    return max(0.0, min(100.0, ratio * 100.0))


def _dimension(key: str, label: str, score: int, weight: float, summary: str) -> Dict[str, Any]:
    return RiskDimension(key=key, label=label, score=score, weight=weight, summary=summary).to_dict()


def _strategy_fit(safety_score: int, yield_quality: int) -> str:
    if safety_score >= 80 and yield_quality >= 55:
        return "conservative"
    if safety_score >= 68:
        return "balanced"
    return "aggressive"


def _quality_score(product_type: str, safety_score: int, yield_durability: int, exit_liquidity: int, confidence_score: int) -> int:
    if product_type in {"stable_lp", "incentivized_stable_lp"}:
        score = (safety_score * 0.48) + (yield_durability * 0.18) + (exit_liquidity * 0.24) + (confidence_score * 0.10)
    elif product_type in {"crypto_stable_lp", "incentivized_crypto_stable_lp"}:
        score = (safety_score * 0.45) + (yield_durability * 0.21) + (exit_liquidity * 0.24) + (confidence_score * 0.10)
    elif product_type in {"crypto_crypto_lp", "incentivized_crypto_crypto_lp"}:
        score = (safety_score * 0.40) + (yield_durability * 0.24) + (exit_liquidity * 0.26) + (confidence_score * 0.10)
    else:
        score = (safety_score * 0.46) + (yield_durability * 0.22) + (exit_liquidity * 0.22) + (confidence_score * 0.10)
    return clamp(score)


def _is_incentivized(product_type: str) -> bool:
    return product_type.startswith("incentivized_")


def _incident_penalty(incidents: Sequence[Dict[str, Any]]) -> Tuple[float, bool]:
    penalty = 0.0
    recent_critical = False
    for incident in incidents:
        severity = str(incident.get("severity") or "").upper()
        age_hours = parse_age_hours(incident.get("date"))
        base = 22.0 if severity == "CRITICAL" else 14.0 if severity == "HIGH" else 8.0
        decay = 1.0
        if age_hours is not None:
            if age_hours > 24 * 365 * 2:
                decay = 0.35
            elif age_hours > 24 * 365:
                decay = 0.55
            elif age_hours > 24 * 180:
                decay = 0.8
            if severity == "CRITICAL" and age_hours < 24 * 365:
                recent_critical = True
        penalty += base * decay
    return penalty, recent_critical


class DefiRiskEngine:
    def __init__(self, public_ranking_default: str = "balanced"):
        self.public_ranking_default = public_ranking_default

    def score_protocol(
        self,
        protocol: Dict[str, Any],
        detail: Optional[Dict[str, Any]],
        audits: Sequence[Dict[str, Any]],
        incidents: Sequence[Dict[str, Any]],
        docs_profile: Optional[Dict[str, Any]],
        dependencies: Sequence[Dict[str, Any]],
        surface_count: int,
    ) -> Dict[str, Any]:
        docs_profile = docs_profile or {}
        tvl = _safe_float(protocol.get("tvl"))
        chains = protocol.get("chains") or detail.get("chains") if isinstance(detail, dict) else []
        chains = chains or []

        critical_findings = sum(int((audit.get("severity_findings") or {}).get("critical", 0) or 0) for audit in audits)
        freshest_audit = min((age for age in (parse_age_hours(audit.get("date")) for audit in audits) if age is not None), default=None)
        audit_freshness = 88 if freshest_audit is not None and freshest_audit < 24 * 365 else 76 if freshest_audit is not None and freshest_audit < 24 * 365 * 2 else 62
        contract_safety = clamp(36 + min(len(audits), 4) * 10 + ((audit_freshness - 60) * 0.35) - (critical_findings * 9) - (16 if not audits else 0))

        incident_penalty, recent_critical = _incident_penalty(incidents)
        incident_history = clamp(96 - incident_penalty)
        market_maturity = clamp(24 + (_log_scale(tvl, 1_000_000, 100_000_000_000) * 0.58) + min(len(chains), 10) * 4 + min(surface_count, 16) * 1.8)

        governance_admin = _safe_float(docs_profile.get("governance_score"), 50)
        governance_admin += 5 if docs_profile.get("has_timelock_mentions") else 0
        governance_admin += 4 if docs_profile.get("has_multisig_mentions") else 0
        governance_admin -= 7 if docs_profile.get("has_admin_mentions") and not docs_profile.get("has_timelock_mentions") else 0
        governance_admin = clamp(governance_admin)

        dependency_safety = self._weighted_dependency_safety(dependencies)

        confidence = build_confidence_report(
            required_fields=["protocol", "tvl", "chains", "audits", "docs"],
            present_fields=[
                "protocol",
                "tvl" if tvl > 0 else "",
                "chains" if chains else "",
                "audits" if audits else "",
                "docs" if docs_profile.get("available") else "",
            ],
            source_count=sum(1 for source in [protocol, detail, audits, incidents, docs_profile] if source),
            freshness_hours=docs_profile.get("freshness_hours"),
            notes=["Confidence drops when audit or governance coverage is sparse."] if not audits or not docs_profile.get("available") else [],
        )

        safety_score = clamp(
            (contract_safety * 0.28)
            + (incident_history * 0.22)
            + (market_maturity * 0.20)
            + (governance_admin * 0.17)
            + (dependency_safety * 0.13)
        )
        if recent_critical:
            safety_score = min(safety_score, 60)
        opportunity_score = clamp((safety_score * 0.64) + (market_maturity * 0.21) + (confidence["score"] * 0.15))
        risk_level = risk_level_from_score(100 - safety_score)

        dimensions = [
            _dimension("contract_safety", "Contract Safety", contract_safety, 0.28, "Audit coverage, audit freshness, and unresolved critical findings."),
            _dimension("incident_history", "Incident History", incident_history, 0.22, "Exploit burden with time decay so older incidents matter less than fresh ones."),
            _dimension("market_maturity", "Market Maturity", market_maturity, 0.20, "TVL depth, deployment breadth, and how battle-tested the surface looks."),
            _dimension("governance_admin", "Governance & Admin", governance_admin, 0.17, "Timelocks, multisig mentions, and admin power visibility in docs."),
            _dimension("dependency_safety", "Dependency Safety", dependency_safety, 0.13, "Oracle, bridge, wrapper, and external dependency inheritance."),
        ]

        return {
            "dimensions": dimensions,
            "confidence": confidence,
            "summary": {
                "tvl_usd": round(tvl, 2),
                "safety_score": safety_score,
                "opportunity_score": opportunity_score,
                "confidence_score": confidence["score"],
                "risk_level": risk_level,
                "incident_count": len(incidents),
                "audit_count": len(audits),
                "deployment_count": len(chains),
            },
        }

    def score_opportunity(
        self,
        kind: str,
        item: Dict[str, Any],
        assets: Sequence[Dict[str, Any]],
        dependencies: Sequence[Dict[str, Any]],
        protocol_safety: int,
        docs_profile: Optional[Dict[str, Any]],
        history_summary: Optional[Dict[str, Any]],
        incidents: Sequence[Dict[str, Any]],
        ranking_profile: Optional[str] = None,
    ) -> Dict[str, Any]:
        docs_profile = docs_profile or {}
        history_summary = history_summary or {}
        ranking = ranking_profile or self.public_ranking_default
        if kind == "lending":
            return self._score_lending(item, assets, dependencies, protocol_safety, docs_profile, incidents, ranking)
        return self._score_pool_or_yield(kind, item, assets, dependencies, protocol_safety, docs_profile, history_summary, incidents, ranking)

    def _score_pool_or_yield(
        self,
        kind: str,
        item: Dict[str, Any],
        assets: Sequence[Dict[str, Any]],
        dependencies: Sequence[Dict[str, Any]],
        protocol_safety: int,
        docs_profile: Dict[str, Any],
        history_summary: Dict[str, Any],
        incidents: Sequence[Dict[str, Any]],
        ranking: str,
    ) -> Dict[str, Any]:
        product_type = str(item.get("product_type") or ("incentivized_crypto_crypto_lp" if kind == "yield" else "crypto_crypto_lp"))
        score_family = str(item.get("score_family") or "lp")
        tvl = _safe_float(item.get("tvl_usd") or item.get("tvlUsd"))
        apy = _safe_float(item.get("apy"))
        apy_base = _safe_float(item.get("apy_base") or item.get("apyBase"))
        apy_reward = _safe_float(item.get("apy_reward") or item.get("apyReward"))
        volume_1d = _safe_float(item.get("volume_usd_1d") or item.get("volumeUsd1d") or item.get("volume_usd") or item.get("volumeUsd"))
        total_yield = max(apy_base + apy_reward, apy, 0.01)
        fee_ratio = apy_base / total_yield if apy_base > 0 else _safe_float(item.get("sustainability_ratio"), 0.0)
        fee_ratio = max(0.0, min(1.0, fee_ratio))
        reward_ratio = max(0.0, min(1.0, apy_reward / total_yield if apy_reward > 0 else max(0.0, 1.0 - fee_ratio)))
        symbol_parts = [str(asset.get("symbol") or "").upper() for asset in assets if asset.get("role") != "reward"]
        underlying_assets = [asset for asset in assets if asset.get("role") != "reward"] or list(assets)
        reward_assets = [asset for asset in assets if asset.get("role") == "reward"]
        stable_share = sum(1 for asset in underlying_assets if asset.get("is_stable") or str(asset.get("symbol") or "").upper() in STABLE_SYMBOLS) / max(len(underlying_assets), 1)
        major_share = sum(1 for asset in underlying_assets if asset.get("is_major") or str(asset.get("symbol") or "").upper() in MAJOR_SYMBOLS) / max(len(underlying_assets), 1)
        exposure = str(item.get("normalized_exposure") or item.get("exposure_type") or item.get("exposure") or "")
        il_risk = str(item.get("il_risk") or item.get("ilRisk") or "").lower() == "yes"

        underlying_quality = _safe_mean([asset.get("quality_score", 55) for asset in underlying_assets], default=58)
        asset_market_depth = _safe_mean([
            max(
                _log_scale(asset.get("liquidity_usd") or 0, 100_000, 5_000_000_000),
                _log_scale(asset.get("market_cap_usd") or 0, 1_000_000, 500_000_000_000) * 0.85,
            )
            for asset in underlying_assets
        ], default=_log_scale(tvl, 100_000, 10_000_000_000))
        volatility_penalty = _safe_mean([min(_safe_float(asset.get("volatility_24h")), 80) * 0.38 for asset in underlying_assets], default=8)
        depeg_penalty = _safe_mean([_safe_float(asset.get("depeg_risk")) * 0.22 for asset in underlying_assets], default=0)
        wrapper_penalty = _safe_mean([_safe_float(asset.get("wrapper_risk")) * 0.28 for asset in underlying_assets], default=0)

        asset_safety = clamp(
            (underlying_quality * 0.62)
            + (asset_market_depth * 0.20)
            + (stable_share * 10)
            + (major_share * 6)
            - volatility_penalty
            - depeg_penalty
            - wrapper_penalty
        )

        if score_family != "lp" or exposure == "single":
            correlation_base = 90
        elif stable_share >= 0.99 or product_type in {"stable_lp", "incentivized_stable_lp"}:
            correlation_base = 92
        elif exposure == "crypto-stable" or product_type in {"crypto_stable_lp", "incentivized_crypto_stable_lp"}:
            correlation_base = 78
        elif major_share >= 0.99:
            correlation_base = 66
        else:
            correlation_base = 50
        complexity_penalty = max(0, len(symbol_parts) - 2) * 10
        if score_family != "lp":
            il_penalty = 0
        else:
            il_penalty = 20 if il_risk and exposure == "crypto-crypto" else 12 if il_risk else 4 if kind == "yield" and reward_ratio > 0.35 else 0
        structure_safety = clamp(correlation_base - complexity_penalty - il_penalty - (reward_ratio * 16))

        dependency_safety = self._weighted_dependency_safety(dependencies)
        governance_admin = _safe_float(docs_profile.get("governance_score"), 50)
        governance_admin += 5 if docs_profile.get("has_timelock_mentions") else 0
        governance_admin += 4 if docs_profile.get("has_multisig_mentions") else 0
        governance_admin -= 7 if docs_profile.get("has_admin_mentions") and not docs_profile.get("has_timelock_mentions") else 0
        governance_admin = clamp(governance_admin)

        stress_history = self._lp_stress_history_score(product_type, history_summary, fee_ratio, reward_ratio)

        safety_score = clamp(
            (protocol_safety * 0.22)
            + (asset_safety * 0.18)
            + (structure_safety * 0.20)
            + (dependency_safety * 0.15)
            + (governance_admin * 0.10)
            + (stress_history * 0.15)
        )

        fee_backed_share = clamp(15 + (fee_ratio * 85))
        apy_persistence = clamp(
            (history_summary.get("apy_persistence_score", 42) * 0.75)
            + (history_summary.get("apy_trend_score", 42) * 0.25)
        ) if history_summary.get("available") else 42
        reward_base_quality = _safe_mean([asset.get("quality_score", 35) for asset in reward_assets], default=88 if not reward_assets else 38)
        reward_quality = clamp((reward_base_quality * 0.72) + ((100 - reward_ratio * 100) * 0.28))
        emissions_dilution = clamp(96 - (reward_ratio * 75) - max(0.0, apy - max(apy_base * 1.4, 0.0)) * 0.05)
        volume_efficiency = self._volume_efficiency(volume_1d, tvl, fee_ratio, history_summary)

        yield_durability = self._yield_durability_score(
            product_type,
            fee_backed_share,
            apy_persistence,
            reward_quality,
            emissions_dilution,
            volume_efficiency,
            fee_ratio,
            reward_ratio,
            history_summary,
        )

        tvl_depth = self._tvl_depth_score(tvl)
        simulated_slippage = self._slippage_score(tvl, volume_1d, len(symbol_parts), reward_ratio, apy)
        fragmentation = self._fragmentation_score(symbol_parts, tvl, stable_share, reward_ratio)
        withdrawal_constraints = self._withdrawal_constraints_score(kind, tvl, fee_ratio, reward_ratio, history_summary)
        exit_liquidity = clamp((tvl_depth * 0.40) + (simulated_slippage * 0.25) + (fragmentation * 0.15) + (withdrawal_constraints * 0.20))

        confidence_notes: List[str] = []
        if not history_summary.get("available"):
            confidence_notes.append("Pool history is missing, so persistence and drawdown analysis is less certain.")
        if volume_1d <= 0:
            confidence_notes.append("Volume data is missing, so exit-quality estimates fall back to TVL proxies.")

        confidence = build_confidence_report(
            required_fields=["chain", "project", "symbol", "tvl", "apy", "assets", "dependencies", "history"],
            present_fields=[
                "chain" if item.get("chain") else "",
                "project" if item.get("project") else "",
                "symbol" if item.get("symbol") else "",
                "tvl" if tvl > 0 else "",
                "apy" if apy >= 0 else "",
                "assets" if assets else "",
                "dependencies" if dependencies else "",
                "history" if history_summary.get("available") else "",
            ],
            source_count=sum(
                1
                for source in [item, assets, dependencies, history_summary]
                if source
            ) + (1 if docs_profile and docs_profile.get("available") and not docs_profile.get("placeholder") else 0),
            freshness_hours=0.0 if history_summary.get("available") else docs_profile.get("freshness_hours"),
            notes=confidence_notes,
        )
        if docs_profile.get("available") and not docs_profile.get("placeholder"):
            confidence["score"] = clamp(confidence["score"] + 6)
        elif product_type in {"stable_lp", "crypto_stable_lp", "crypto_crypto_lp"} and history_summary.get("available"):
            confidence["score"] = clamp(confidence["score"] + 10)
            if not confidence.get("missing_critical_fields"):
                confidence["partial_analysis"] = False
                confidence["label"] = "STANDARD" if confidence["score"] < 76 else "HIGH"

        safety_score, yield_durability, exit_liquidity, confidence, caps = self._apply_pool_caps(
            item,
            underlying_assets,
            reward_assets,
            history_summary,
            incidents,
            docs_profile,
            fee_ratio,
            reward_ratio,
            product_type,
            safety_score,
            yield_durability,
            exit_liquidity,
            confidence,
        )

        raw_risk_burden = self._risk_burden_score(
            product_type,
            item,
            protocol_safety,
            asset_safety,
            structure_safety,
            dependency_safety,
            governance_admin,
            stress_history,
            exit_liquidity,
            il_risk,
            reward_ratio,
            len(symbol_parts),
        )
        risk_burden = clamp(max(raw_risk_burden, 100 - safety_score))

        quality_score = clamp(
            _quality_score(product_type, safety_score, yield_durability, exit_liquidity, confidence["score"])
            + self._quality_adjustment(
                product_type,
                safety_score,
                yield_durability,
                exit_liquidity,
                confidence["score"],
                tvl,
                fee_ratio,
                reward_ratio,
                stable_share,
                major_share,
                underlying_assets,
            )
        )
        effective_apr = self._effective_apr(
            product_type,
            apy_base,
            apy_reward,
            fee_ratio,
            reward_ratio,
            safety_score,
            yield_durability,
            exit_liquidity,
            volume_efficiency,
            reward_quality,
            emissions_dilution,
            confidence["score"],
            history_summary,
        )
        required_apr = self._required_apr(
            product_type,
            apy,
            risk_burden,
            exit_liquidity,
            yield_durability,
            confidence["score"],
            reward_ratio,
        )
        apr_efficiency = self._apr_efficiency_score(effective_apr, required_apr)
        return_potential = apr_efficiency

        overall_score = self._overall_score(
            ranking,
            quality_score,
            safety_score,
            yield_durability,
            exit_liquidity,
            apr_efficiency,
            confidence["score"],
        )
        opportunity_score = overall_score

        dimensions = [
            _dimension("overall_score", "Overall Score", overall_score, 1.0, "Primary deployment score blending APR efficiency, pool quality, safety, exit liquidity, durability, and confidence."),
            _dimension("protocol_safety", "Protocol Safety", protocol_safety, 0.22, "Protocol battle-testing, audits, incidents, and governance posture."),
            _dimension("asset_safety", "Asset Safety", asset_safety, 0.18, "Underlying asset quality blended with depth, volatility, and wrapper or depeg risk."),
            _dimension("structure_safety", "Structure Safety", structure_safety, 0.20, "IL exposure, correlation, and pool complexity rather than just a stable-pair bonus."),
            _dimension("dependency_safety", "Dependency Safety", dependency_safety, 0.15, "Weighted dependency inheritance with oracles and bridges penalized more heavily."),
            _dimension("governance_admin", "Governance & Admin", governance_admin, 0.10, "Timelocks, multisig coverage, and visible admin controls in docs."),
            _dimension("stress_history", "Stress History", stress_history, 0.15, "Historical APY variance, TVL drawdown, and recovery quality over recent snapshots."),
            _dimension("quality_score", "Quality Score", quality_score, 1.0, "Core pool quality combining safety, durability, exit liquidity, and evidence confidence."),
            _dimension("yield_durability", "Yield Durability", yield_durability, 0.24, "Fee-backed yield, persistence, reward quality, emissions dilution, and real trading activity."),
            _dimension("exit_liquidity", "Exit Liquidity", exit_liquidity, 0.15, "Depth, slippage realism, fragmentation, and practical withdrawal constraints."),
            _dimension("confidence", "Confidence", confidence["score"], 0.10, "Coverage, freshness, and whether critical fields are still missing."),
            _dimension("apr_efficiency", "APR Efficiency", apr_efficiency, 0.40, "How much effective APR remains after risk, durability, liquidity, and incentive haircuts relative to the required hurdle APR."),
        ]

        return {
            "summary": {
                "overall_score": overall_score,
                "quality_score": quality_score,
                "opportunity_score": opportunity_score,
                "safety_score": safety_score,
                "risk_burden_score": risk_burden,
                "yield_durability_score": yield_durability,
                "yield_quality_score": yield_durability,
                "exit_liquidity_score": exit_liquidity,
                "exit_quality_score": exit_liquidity,
                "apr_efficiency_score": apr_efficiency,
                "effective_apr": effective_apr,
                "required_apr": required_apr,
                "return_potential_score": return_potential,
                "confidence_score": confidence["score"],
                "risk_level": risk_level_from_score(100 - safety_score),
                "strategy_fit": _strategy_fit(safety_score, yield_durability),
                "headline": self._headline(kind, overall_score, quality_score, apr_efficiency, exit_liquidity, confidence["partial_analysis"]),
                "thesis": self._pool_thesis(kind, item, fee_ratio, safety_score, yield_durability, exit_liquidity, caps),
            },
            "dimensions": dimensions,
            "confidence": confidence,
            "score_caps": caps,
        }

    def _score_lending(
        self,
        item: Dict[str, Any],
        assets: Sequence[Dict[str, Any]],
        dependencies: Sequence[Dict[str, Any]],
        protocol_safety: int,
        docs_profile: Dict[str, Any],
        incidents: Sequence[Dict[str, Any]],
        ranking: str,
    ) -> Dict[str, Any]:
        product_type = str(item.get("product_type") or "lending_supply_like")
        tvl = _safe_float(item.get("tvlUsd") or item.get("tvl_usd"))
        supply = _safe_float(item.get("apy_supply"))
        borrow = _safe_float(item.get("apy_borrow"))
        utilization = _safe_float(item.get("utilization_pct"))
        asset_quality = clamp(_safe_mean([asset.get("quality_score", 60) for asset in assets if asset.get("role") != "reward"], default=68))
        dependency_safety = self._weighted_dependency_safety(dependencies)

        incident_penalty, recent_critical = _incident_penalty(incidents)
        oracle_liquidation = 84
        oracle_liquidation -= min(24.0, max(utilization - 70.0, 0.0) * 0.8)
        oracle_liquidation -= incident_penalty * 0.35
        oracle_liquidation += 6 if docs_profile.get("has_oracle_mentions") else 0
        oracle_liquidation += (asset_quality - 60) * 0.08
        oracle_liquidation = clamp(oracle_liquidation)

        market_liquidity = self._tvl_depth_score(tvl)
        utilization_headroom = clamp(100 - max(0.0, utilization - 55.0) * 1.6)
        governance_admin = _safe_float(docs_profile.get("governance_score"), 50)
        governance_admin += 5 if docs_profile.get("has_timelock_mentions") else 0
        governance_admin += 4 if docs_profile.get("has_multisig_mentions") else 0
        governance_admin -= 7 if docs_profile.get("has_admin_mentions") and not docs_profile.get("has_timelock_mentions") else 0
        governance_admin = clamp(governance_admin)

        safety_score = clamp(
            (protocol_safety * 0.28)
            + (oracle_liquidation * 0.20)
            + (market_liquidity * 0.17)
            + (utilization_headroom * 0.15)
            + (asset_quality * 0.10)
            + (governance_admin * 0.10)
        )

        net_value = self._lending_net_value_score(supply, borrow, utilization)
        rate_stability = clamp(92 - max(0.0, utilization - 70.0) * 1.25 - max(0.0, borrow - 12.0) * 1.1)
        reserve_health = clamp((market_liquidity * 0.55) + (utilization_headroom * 0.45))
        counterparty_quality = clamp((protocol_safety * 0.60) + (asset_quality * 0.25) + (dependency_safety * 0.15))
        incentive_dependence = clamp(92 - max(0.0, supply - 12.0) * 2.2)
        yield_durability = clamp(
            (net_value * 0.35)
            + (rate_stability * 0.20)
            + (reserve_health * 0.20)
            + (counterparty_quality * 0.15)
            + (incentive_dependence * 0.10)
        )

        exit_liquidity = clamp(
            (market_liquidity * 0.40)
            + (utilization_headroom * 0.35)
            + (dependency_safety * 0.15)
            + (governance_admin * 0.10)
        )

        confidence_notes: List[str] = []
        if not assets:
            confidence_notes.append("Asset inheritance is incomplete, so collateral quality is partially heuristic.")

        confidence = build_confidence_report(
            required_fields=["symbol", "chain", "tvl", "supply", "utilization", "assets", "dependencies", "docs"],
            present_fields=[
                "symbol" if item.get("symbol") else "",
                "chain" if item.get("chain") else "",
                "tvl" if tvl > 0 else "",
                "supply" if supply >= 0 else "",
                "utilization" if utilization > 0 else "",
                "assets" if assets else "",
                "dependencies" if dependencies else "",
                "docs" if docs_profile.get("available") and not docs_profile.get("placeholder") else "",
            ],
            source_count=sum(1 for source in [item, assets, dependencies] if source) + (1 if docs_profile and docs_profile.get("available") and not docs_profile.get("placeholder") else 0),
            freshness_hours=docs_profile.get("freshness_hours"),
            notes=confidence_notes,
        )

        safety_score, yield_durability, exit_liquidity, confidence, caps = self._apply_lending_caps(
            item,
            assets,
            incidents,
            docs_profile,
            safety_score,
            yield_durability,
            exit_liquidity,
            confidence,
        )

        risk_burden = clamp(
            ((100 - protocol_safety) * 0.25)
            + ((100 - oracle_liquidation) * 0.20)
            + ((100 - market_liquidity) * 0.15)
            + ((100 - utilization_headroom) * 0.15)
            + ((100 - asset_quality) * 0.10)
            + ((100 - governance_admin) * 0.10)
            + ((100 - exit_liquidity) * 0.05)
        )
        quality_score = _quality_score(product_type, safety_score, yield_durability, exit_liquidity, confidence["score"])
        effective_apr = round(max(0.0, supply) * max(0.35, min(0.95, 0.55 + 0.45 * (yield_durability / 100.0) * (confidence["score"] / 100.0))), 2)
        required_apr = self._required_apr(product_type, supply, risk_burden, exit_liquidity, yield_durability, confidence["score"], 0.0)
        apr_efficiency = self._apr_efficiency_score(effective_apr, required_apr)
        return_potential = apr_efficiency

        overall_score = self._overall_score(
            ranking,
            quality_score,
            safety_score,
            yield_durability,
            exit_liquidity,
            apr_efficiency,
            confidence["score"],
        )
        opportunity_score = overall_score

        if recent_critical:
            opportunity_score = min(opportunity_score, 72)

        dimensions = [
            _dimension("overall_score", "Overall Score", opportunity_score, 1.0, "Primary deployment score blending APR efficiency, quality, safety, exits, durability, and confidence."),
            _dimension("protocol_safety", "Protocol Safety", protocol_safety, 0.28, "Protocol quality from audits, incidents, TVL depth, and governance posture."),
            _dimension("oracle_liquidation", "Oracle & Liquidation Safety", oracle_liquidation, 0.20, "Oracle reliability and how violently the market can reprice during stress."),
            _dimension("market_liquidity", "Market Liquidity", market_liquidity, 0.17, "Reserve depth and practical withdraw capacity for meaningful size."),
            _dimension("utilization_headroom", "Utilization Headroom", utilization_headroom, 0.15, "How much reserve slack remains before exits and rates become stressed."),
            _dimension("asset_quality", "Asset Quality", asset_quality, 0.10, "Collateral and borrow asset quality inherited from token intelligence or heuristics."),
            _dimension("governance_admin", "Governance & Admin", governance_admin, 0.10, "Timelocks, multisig mentions, and admin control transparency."),
            _dimension("quality_score", "Quality Score", quality_score, 1.0, "Core opportunity quality combining safety, durability, exits, and evidence confidence."),
            _dimension("yield_durability", "Yield Durability", yield_durability, 0.20, "Net carry, reserve health, rate stability, and incentive dependence."),
            _dimension("exit_liquidity", "Exit Liquidity", exit_liquidity, 0.20, "Depth, utilization headroom, dependency risk, and operational constraints."),
            _dimension("confidence", "Confidence", confidence["score"], 0.10, "Coverage, freshness, and whether reserve and asset data are complete."),
            _dimension("apr_efficiency", "APR Efficiency", apr_efficiency, 0.40, "Effective lending APR relative to the hurdle required for this risk burden."),
        ]

        return {
            "summary": {
                "overall_score": opportunity_score,
                "quality_score": quality_score,
                "opportunity_score": opportunity_score,
                "safety_score": safety_score,
                "risk_burden_score": risk_burden,
                "yield_durability_score": yield_durability,
                "yield_quality_score": yield_durability,
                "exit_liquidity_score": exit_liquidity,
                "exit_quality_score": exit_liquidity,
                "apr_efficiency_score": apr_efficiency,
                "effective_apr": effective_apr,
                "required_apr": required_apr,
                "return_potential_score": return_potential,
                "confidence_score": confidence["score"],
                "risk_level": risk_level_from_score(100 - safety_score),
                "strategy_fit": _strategy_fit(safety_score, yield_durability),
                "headline": self._headline("lending", opportunity_score, quality_score, apr_efficiency, exit_liquidity, confidence["partial_analysis"]),
                "thesis": self._lending_thesis(item, safety_score, yield_durability, exit_liquidity, caps),
            },
            "dimensions": dimensions,
            "confidence": confidence,
            "score_caps": caps,
        }

    def _apply_pool_caps(
        self,
        item: Dict[str, Any],
        underlying_assets: Sequence[Dict[str, Any]],
        reward_assets: Sequence[Dict[str, Any]],
        history_summary: Dict[str, Any],
        incidents: Sequence[Dict[str, Any]],
        docs_profile: Dict[str, Any],
        fee_ratio: float,
        reward_ratio: float,
        product_type: str,
        safety_score: int,
        yield_quality: int,
        exit_quality: int,
        confidence: Dict[str, Any],
    ) -> Tuple[int, int, int, Dict[str, Any], List[Dict[str, Any]]]:
        caps: List[Dict[str, Any]] = []

        incident_penalty, recent_critical = _incident_penalty(incidents)
        if recent_critical:
            safety_score = min(safety_score, 42)
            caps.append(ScoreCap("safety", 42, "Recent critical exploit history caps safety until resilience is re-established.").to_dict())
        elif incident_penalty > 12:
            safety_score = min(safety_score, 56)
            caps.append(ScoreCap("safety", 56, "Meaningful incident history still caps safety even if the latest event is not recent.").to_dict())

        reward_quality = _safe_mean([asset.get("quality_score", 35) for asset in reward_assets], default=100)
        if reward_assets and reward_quality < 42:
            yield_quality = min(yield_quality, 44)
            caps.append(ScoreCap("yield_quality", 44, "Low-quality reward token caps yield quality even when nominal APY is high.").to_dict())

        tvl = _safe_float(item.get("tvl_usd") or item.get("tvlUsd"))
        if tvl < 150_000:
            exit_quality = min(exit_quality, 32)
            caps.append(ScoreCap("exit_quality", 32, "Very shallow liquidity sharply caps exit quality.").to_dict())
        elif tvl < 500_000:
            exit_quality = min(exit_quality, 46)
            caps.append(ScoreCap("exit_quality", 46, "Thin liquidity caps exit quality for non-trivial size.").to_dict())

        if confidence.get("partial_analysis"):
            confidence = {**confidence, "score": min(confidence.get("score", 0), 55), "label": "PARTIAL"}
            caps.append(ScoreCap("confidence", 55, "Partial analysis caps confidence until missing fields are resolved.").to_dict())

        risky_stable = any(_safe_float(asset.get("depeg_risk")) > 24 for asset in underlying_assets if str(asset.get("symbol") or "").upper() in STABLE_SYMBOLS)
        if risky_stable:
            safety_score = max(0, safety_score - 10)
            caps.append(ScoreCap("safety", safety_score, "Stable-leg quality penalty applied for depeg-prone or wrapper-heavy stable exposure.").to_dict())

        if docs_profile.get("has_admin_mentions") and not docs_profile.get("has_timelock_mentions"):
            safety_score = max(0, safety_score - 8)
            caps.append(ScoreCap("safety", safety_score, "Governance/admin penalty applied because admin controls appear stronger than timelock protection.").to_dict())

        recent_apy_drop = _safe_float(history_summary.get("recent_apy_drop_pct"))
        recent_tvl_drop = _safe_float(history_summary.get("recent_tvl_drop_pct"))
        reward_heavy = reward_ratio > 0.30 or _is_incentivized(product_type)
        fee_backed_lp = fee_ratio >= 0.70 and reward_ratio <= 0.20 and not _is_incentivized(product_type)
        if history_summary.get("available") and recent_tvl_drop > 45:
            yield_quality = min(yield_quality, 48)
            caps.append(ScoreCap("yield_quality", 48, "Recent TVL collapse caps yield durability until liquidity stabilizes.").to_dict())
        elif history_summary.get("available") and reward_heavy and recent_apy_drop > 65:
            yield_quality = min(yield_quality, 48)
            caps.append(ScoreCap("yield_quality", 48, "Reward-heavy yield with a sharp recent APY collapse caps durability until incentives stabilize.").to_dict())
        elif history_summary.get("available") and not fee_backed_lp and recent_apy_drop > 85 and recent_tvl_drop > 20:
            yield_quality = min(yield_quality, 52)
            caps.append(ScoreCap("yield_quality", 52, "Combined APY and TVL deterioration caps durability for non-organic yield surfaces.").to_dict())

        return safety_score, yield_quality, exit_quality, confidence, caps

    def _apply_lending_caps(
        self,
        item: Dict[str, Any],
        assets: Sequence[Dict[str, Any]],
        incidents: Sequence[Dict[str, Any]],
        docs_profile: Dict[str, Any],
        safety_score: int,
        yield_quality: int,
        exit_quality: int,
        confidence: Dict[str, Any],
    ) -> Tuple[int, int, int, Dict[str, Any], List[Dict[str, Any]]]:
        caps: List[Dict[str, Any]] = []
        incident_penalty, recent_critical = _incident_penalty(incidents)
        if recent_critical:
            safety_score = min(safety_score, 48)
            caps.append(ScoreCap("safety", 48, "Recent critical exploit history caps lending safety.").to_dict())
        elif incident_penalty > 12:
            safety_score = min(safety_score, 60)
            caps.append(ScoreCap("safety", 60, "Incident history still caps lending safety even if the latest event is older.").to_dict())

        utilization = _safe_float(item.get("utilization_pct"))
        if utilization > 92:
            exit_quality = min(exit_quality, 35)
            caps.append(ScoreCap("exit_quality", 35, "Reserve utilization cap applied because withdrawals may fail under stress.").to_dict())
        elif utilization > 85:
            exit_quality = min(exit_quality, 48)
            caps.append(ScoreCap("exit_quality", 48, "High utilization caps exit quality because reserve headroom is thin.").to_dict())

        risky_asset = any((asset.get("quality_score") or 100) < 45 for asset in assets if asset.get("role") != "reward")
        if risky_asset:
            safety_score = min(safety_score, 58)
            caps.append(ScoreCap("safety", 58, "Low-quality collateral or borrowed asset caps lending safety.").to_dict())

        if confidence.get("partial_analysis"):
            confidence = {**confidence, "score": min(confidence.get("score", 0), 55), "label": "PARTIAL"}
            caps.append(ScoreCap("confidence", 55, "Partial analysis caps confidence until coverage improves.").to_dict())

        if docs_profile.get("has_admin_mentions") and not docs_profile.get("has_timelock_mentions"):
            safety_score = max(0, safety_score - 8)
            caps.append(ScoreCap("safety", safety_score, "Governance/admin penalty applied because admin controls appear stronger than timelock protection.").to_dict())

        if _safe_float(item.get("apy_borrow")) > 35:
            yield_quality = min(yield_quality, 52)
            caps.append(ScoreCap("yield_quality", 52, "Very high borrow rates cap yield quality because the market is already stressed.").to_dict())

        return safety_score, yield_quality, exit_quality, confidence, caps

    def _weighted_dependency_safety(self, dependencies: Sequence[Dict[str, Any]]) -> int:
        if not dependencies:
            return 58
        weights = {
            "oracle": 1.45,
            "bridge": 1.30,
            "protocol": 1.20,
            "reward": 0.95,
            "underlying": 1.0,
            "collateral": 1.0,
            "asset": 1.0,
        }
        weighted_risk = _weighted_average(
            (
                _safe_float(dependency.get("risk_score"), 45),
                weights.get(str(dependency.get("dependency_type") or "dependency"), 1.0),
            )
            for dependency in dependencies
        )
        return clamp(100 - weighted_risk)

    def _tvl_depth_score(self, tvl: float) -> int:
        return clamp(18 + (_log_scale(tvl, 50_000, 5_000_000_000) * 0.82))

    def _slippage_score(self, tvl: float, daily_volume: float, asset_count: int, reward_ratio: float, apy: float) -> int:
        liquidity_component = self._tvl_depth_score(tvl) * 0.55
        volume_ratio = min(2.0, daily_volume / max(tvl, 1.0)) if daily_volume > 0 else 0.0
        flow_component = 18 + (volume_ratio * 24) + (_log_scale(daily_volume, 100_000, 5_000_000_000) * 0.20 if daily_volume > 0 else 0)
        penalty = max(0, asset_count - 2) * 8 + (reward_ratio * 10)
        penalty += 8 if apy > 150 else 4 if apy > 60 else 0
        return clamp(liquidity_component + flow_component - penalty)

    def _fragmentation_score(self, symbol_parts: Sequence[str], tvl: float, stable_share: float, reward_ratio: float) -> int:
        score = 86 - max(0, len(symbol_parts) - 2) * 10
        score += stable_share * 6
        score -= reward_ratio * 8
        score -= 8 if tvl < 500_000 else 0
        return clamp(score)

    def _withdrawal_constraints_score(self, kind: str, tvl: float, fee_ratio: float, reward_ratio: float, history_summary: Dict[str, Any]) -> int:
        score = 80 - max(0.0, 0.22 - fee_ratio) * 50 - (reward_ratio * 10)
        if kind == "yield":
            score -= max(0.0, 0.25 - fee_ratio) * 30
        if tvl < 500_000:
            score -= 16
        if history_summary.get("available"):
            score -= min(18.0, _safe_float(history_summary.get("recent_tvl_drop_pct")) * 0.22)
        return clamp(score)

    def _volume_efficiency(self, daily_volume: float, tvl: float, fee_ratio: float, history_summary: Dict[str, Any]) -> int:
        if daily_volume > 0:
            ratio = min(2.0, daily_volume / max(tvl, 1.0))
            score = 24 + (ratio * 28) + (_log_scale(daily_volume, 100_000, 5_000_000_000) * 0.38) + (fee_ratio * 16)
        else:
            score = 32 + (fee_ratio * 30)
        if history_summary.get("available"):
            score += (history_summary.get("tvl_trend_score", 40) - 50) * 0.12
            score -= min(12.0, _safe_float(history_summary.get("recent_tvl_drop_pct")) * 0.18)
        return clamp(score)

    def _lending_net_value_score(self, supply: float, borrow: float, utilization: float) -> int:
        score = 42 + (_log_scale(max(supply, 0.0) + 1.0, 1.0, 20.0) * 0.38)
        score += 12 if 2 <= supply <= 9 else 5 if 0.5 <= supply < 2 else -8 if supply > 18 else 0
        score -= max(0.0, borrow - 8.0) * 0.9
        score -= max(0.0, utilization - 80.0) * 0.4
        return clamp(score)

    def _lp_stress_history_score(
        self,
        product_type: str,
        history_summary: Dict[str, Any],
        fee_ratio: float,
        reward_ratio: float,
    ) -> int:
        if not history_summary.get("available"):
            return 58 if not _is_incentivized(product_type) else 50

        apy_persistence = _safe_float(history_summary.get("apy_persistence_score"), 42)
        apy_trend = _safe_float(history_summary.get("apy_trend_score"), 42)
        tvl_trend = _safe_float(history_summary.get("tvl_trend_score"), 42)
        tvl_drawdown = _safe_float(history_summary.get("tvl_drawdown_pct"), 0)
        recent_tvl_drop = _safe_float(history_summary.get("recent_tvl_drop_pct"), 0)
        recent_apy_drop = _safe_float(history_summary.get("recent_apy_drop_pct"), 0)

        if fee_ratio >= 0.65 and reward_ratio <= 0.20:
            score = (
                (apy_persistence * 0.18)
                + (tvl_trend * 0.32)
                + ((100 - min(tvl_drawdown, 100)) * 0.25)
                + ((100 - min(recent_tvl_drop, 100)) * 0.25)
            )
            score -= max(0.0, recent_tvl_drop - 12.0) * 0.30
            score -= max(0.0, recent_apy_drop - 85.0) * 0.05
            return clamp(score)

        score = (
            (apy_persistence * 0.38)
            + (apy_trend * 0.16)
            + (tvl_trend * 0.18)
            + ((100 - min(tvl_drawdown, 100)) * 0.14)
            + ((100 - min(recent_tvl_drop, 100)) * 0.14)
        )
        score -= max(0.0, recent_apy_drop - 45.0) * 0.20
        return clamp(score)

    def _yield_durability_score(
        self,
        product_type: str,
        fee_backed_share: int,
        apy_persistence: int,
        reward_quality: int,
        emissions_dilution: int,
        volume_efficiency: int,
        fee_ratio: float,
        reward_ratio: float,
        history_summary: Dict[str, Any],
    ) -> int:
        if fee_ratio >= 0.70 and reward_ratio <= 0.20:
            score = (
                (fee_backed_share * 0.30)
                + (max(apy_persistence, int(_safe_float(history_summary.get("tvl_trend_score"), apy_persistence))) * 0.18)
                + (volume_efficiency * 0.26)
                + (emissions_dilution * 0.14)
                + (reward_quality * 0.12)
            )
            score -= max(0.0, _safe_float(history_summary.get("recent_tvl_drop_pct"), 0) - 15.0) * 0.22
            return clamp(score)

        if product_type in {"stable_lp", "incentivized_stable_lp"}:
            score = (
                (fee_backed_share * 0.28)
                + (apy_persistence * 0.22)
                + (reward_quality * 0.16)
                + (emissions_dilution * 0.18)
                + (volume_efficiency * 0.16)
            )
            return clamp(score)

        score = (
            (fee_backed_share * 0.26)
            + (apy_persistence * 0.24)
            + (reward_quality * 0.18)
            + (emissions_dilution * 0.16)
            + (volume_efficiency * 0.16)
        )
        return clamp(score)

    def _quality_adjustment(
        self,
        product_type: str,
        safety_score: int,
        yield_durability: int,
        exit_liquidity: int,
        confidence_score: int,
        tvl: float,
        fee_ratio: float,
        reward_ratio: float,
        stable_share: float,
        major_share: float,
        underlying_assets: Sequence[Dict[str, Any]],
    ) -> int:
        bonus = 0.0
        avg_quality = _safe_mean([asset.get("quality_score", 55) for asset in underlying_assets], default=55)

        if tvl >= 10_000_000:
            bonus += min(8.0, (_log_scale(tvl, 10_000_000, 1_000_000_000) * 0.08))
        if fee_ratio >= 0.80 and reward_ratio <= 0.15:
            bonus += 6.0
        elif fee_ratio >= 0.60:
            bonus += 3.0
        if stable_share >= 0.99:
            bonus += 5.0
        elif stable_share > 0 or major_share >= 0.99:
            bonus += 4.0
        if avg_quality >= 88:
            bonus += 4.0
        if exit_liquidity >= 75:
            bonus += 5.0
        elif exit_liquidity >= 68:
            bonus += 2.0
        if safety_score < 50:
            bonus -= (50 - safety_score) * 0.30
        if yield_durability < 45:
            bonus -= (45 - yield_durability) * 0.25
        if tvl < 1_000_000:
            bonus -= 6.0
        elif tvl < 5_000_000:
            bonus -= 2.0
        if _is_incentivized(product_type) and reward_ratio > 0.40:
            bonus -= 4.0
        if confidence_score >= 70:
            bonus += 2.0
        return round(bonus)

    def _fee_tier_pct(self, item: Dict[str, Any]) -> Optional[float]:
        raw = str(item.get("pool_meta") or item.get("poolMeta") or "").strip()
        if not raw:
            return None
        match = re.search(r"(\d+(?:\.\d+)?)%", raw)
        if not match:
            return None
        try:
            return float(match.group(1))
        except ValueError:
            return None

    def _fee_tier_suitability(self, product_type: str, fee_tier_pct: Optional[float]) -> int:
        if fee_tier_pct is None:
            return 62
        tier = max(fee_tier_pct, 0.0)
        if product_type in {"stable_lp", "incentivized_stable_lp"}:
            if tier <= 0.05:
                return 92
            if tier <= 0.10:
                return 80
            if tier <= 0.30:
                return 60
            return 35
        if product_type in {"crypto_stable_lp", "incentivized_crypto_stable_lp"}:
            if 0.03 <= tier <= 0.30:
                return 86
            if tier <= 0.60:
                return 70
            return 48
        if product_type in {"crypto_crypto_lp", "incentivized_crypto_crypto_lp"}:
            if 0.05 <= tier <= 1.00:
                return 82
            if tier <= 1.50:
                return 66
            return 50
        return 60

    def _operational_risk(
        self,
        product_type: str,
        item: Dict[str, Any],
        asset_count: int,
        il_risk: bool,
        reward_ratio: float,
    ) -> int:
        fee_tier = self._fee_tier_pct(item)
        suitability = self._fee_tier_suitability(product_type, fee_tier)
        risk = 18 if product_type in {"stable_lp", "incentivized_stable_lp"} else 26 if product_type in {"crypto_stable_lp", "incentivized_crypto_stable_lp"} else 34
        if il_risk:
            risk += 12
        risk += max(0, asset_count - 2) * 6
        if _is_incentivized(product_type):
            risk += 6
        if fee_tier is not None:
            risk += max(0.0, 70 - suitability) * 0.35
        risk += reward_ratio * 12
        return clamp(risk)

    def _risk_burden_score(
        self,
        product_type: str,
        item: Dict[str, Any],
        protocol_safety: int,
        asset_safety: int,
        structure_safety: int,
        dependency_safety: int,
        governance_admin: int,
        stress_history: int,
        exit_liquidity: int,
        il_risk: bool,
        reward_ratio: float,
        asset_count: int,
    ) -> int:
        operational_risk = self._operational_risk(product_type, item, asset_count, il_risk, reward_ratio)
        return clamp(
            ((100 - protocol_safety) * 0.20)
            + ((100 - asset_safety) * 0.15)
            + ((100 - structure_safety) * 0.15)
            + ((100 - exit_liquidity) * 0.15)
            + ((100 - dependency_safety) * 0.10)
            + ((100 - governance_admin) * 0.10)
            + ((100 - stress_history) * 0.10)
            + (operational_risk * 0.05)
        )

    def _effective_apr(
        self,
        product_type: str,
        apy_base: float,
        apy_reward: float,
        fee_ratio: float,
        reward_ratio: float,
        safety_score: int,
        yield_durability: int,
        exit_liquidity: int,
        volume_efficiency: int,
        reward_quality: int,
        emissions_dilution: int,
        confidence_score: int,
        history_summary: Dict[str, Any],
    ) -> float:
        base_capture = 0.50 + 0.50 * (
            (safety_score / 100.0)
            * (yield_durability / 100.0)
            * (max(volume_efficiency, 45) / 100.0)
            * (exit_liquidity / 100.0)
        )
        base_capture += fee_ratio * 0.08
        base_capture -= max(0.0, _safe_float(history_summary.get("recent_tvl_drop_pct")) - 15.0) * 0.003
        base_capture = max(0.30, min(0.96, base_capture))

        reward_capture = 0.03 + 0.47 * (
            (reward_quality / 100.0)
            * (emissions_dilution / 100.0)
            * (yield_durability / 100.0)
            * (confidence_score / 100.0)
        )
        reward_capture -= reward_ratio * 0.10
        reward_capture = max(0.02, min(0.55, reward_capture))

        effective_base = max(0.0, apy_base) * base_capture
        effective_reward = max(0.0, apy_reward) * reward_capture
        if fee_ratio < 0.25 and reward_ratio > 0.50:
            effective_reward *= 0.75
        if _is_incentivized(product_type) and apy_reward > 0:
            reward_cap = 18.0 + max(0.0, yield_durability - 50) * 0.50 + max(0.0, reward_quality - 50) * 0.20 + max(0.0, confidence_score - 60) * 0.10
            effective_reward = min(effective_reward, reward_cap)
        return round(max(0.0, effective_base + effective_reward), 2)

    def _required_apr(
        self,
        product_type: str,
        nominal_apr: float,
        risk_burden: int,
        exit_liquidity: int,
        yield_durability: int,
        confidence_score: int,
        reward_ratio: float,
    ) -> float:
        base_hurdles = {
            "stable_lp": 1.0,
            "incentivized_stable_lp": 3.0,
            "crypto_stable_lp": 3.5,
            "incentivized_crypto_stable_lp": 6.0,
            "crypto_crypto_lp": 5.5,
            "incentivized_crypto_crypto_lp": 10.0,
            "lending_supply_like": 2.5,
        }
        slopes = {
            "stable_lp": 0.035,
            "incentivized_stable_lp": 0.065,
            "crypto_stable_lp": 0.060,
            "incentivized_crypto_stable_lp": 0.10,
            "crypto_crypto_lp": 0.090,
            "incentivized_crypto_crypto_lp": 0.16,
            "lending_supply_like": 0.045,
        }
        base = base_hurdles.get(product_type, 4.0)
        slope = slopes.get(product_type, 0.08)
        required = base + (risk_burden * slope)
        required += max(0.0, 65 - exit_liquidity) * 0.05
        required += max(0.0, 65 - yield_durability) * 0.06
        required += reward_ratio * 8.0
        required += max(0.0, 70 - confidence_score) * 0.03
        required += max(0.0, nominal_apr - 25.0) * (0.03 if _is_incentivized(product_type) else 0.015)
        return round(max(0.5, required), 2)

    def _apr_efficiency_score(self, effective_apr: float, required_apr: float) -> int:
        if required_apr <= 0:
            return 100
        ratio = effective_apr / required_apr
        if ratio <= 0:
            return 0
        if ratio < 0.25:
            return clamp(5 + (ratio / 0.25) * 10)
        if ratio < 0.50:
            return clamp(15 + ((ratio - 0.25) / 0.25) * 20)
        if ratio < 0.80:
            return clamp(35 + ((ratio - 0.50) / 0.30) * 20)
        if ratio < 1.00:
            return clamp(55 + ((ratio - 0.80) / 0.20) * 10)
        if ratio < 1.25:
            return clamp(65 + ((ratio - 1.00) / 0.25) * 13)
        if ratio < 1.60:
            return clamp(78 + ((ratio - 1.25) / 0.35) * 12)
        return clamp(90 + min(10, (ratio - 1.60) * 8))

    def _overall_score(
        self,
        ranking: str,
        quality_score: int,
        safety_score: int,
        yield_durability: int,
        exit_liquidity: int,
        apr_efficiency: int,
        confidence_score: int,
    ) -> int:
        if ranking == "conservative":
            score = (
                (apr_efficiency * 0.30)
                + (quality_score * 0.22)
                + (safety_score * 0.20)
                + (exit_liquidity * 0.15)
                + (yield_durability * 0.08)
                + (confidence_score * 0.05)
            )
        else:
            score = (
                (apr_efficiency * 0.40)
                + (quality_score * 0.20)
                + (safety_score * 0.15)
                + (exit_liquidity * 0.10)
                + (yield_durability * 0.10)
                + (confidence_score * 0.05)
            )
        return clamp(score)

    def _risk_adjusted_return_score(self, apy: float, safety_score: int, yield_quality: int, fee_quality: float, kind: str) -> int:
        apy_score = 0 if apy <= 0 else clamp(12 + (_log_scale(apy + 1.0, 1.0, 1_500.0) * 0.88))
        effective_multiplier = 0.32 + (safety_score / 100.0) * 0.40 + (yield_quality / 100.0) * 0.28
        quality_multiplier = 0.65 + max(0.0, min(1.0, fee_quality)) * 0.35
        score = apy_score * effective_multiplier * quality_multiplier
        if kind != "lending" and apy > 300:
            score -= min(18.0, (apy - 300.0) * 0.03)
        return clamp(score)

    def _headline(self, kind: str, overall_score: int, quality_score: int, apr_efficiency: int, exit_liquidity: int, partial: bool) -> str:
        if partial:
            return "Promising surface, but the report still has partial coverage."
        if overall_score >= 85 and apr_efficiency >= 75:
            return "Exceptional risk-adjusted deployment"
        if quality_score >= 80 and apr_efficiency < 40:
            return "High-quality pool, but the effective APR is modest for the risk"
        if kind == "lending" and overall_score >= 78 and exit_liquidity >= 65:
            return "Battle-tested lending setup with workable reserve slack"
        if apr_efficiency >= 70 and overall_score < 65:
            return "Headline APR looks attractive, but the risk burden still eats into the edge"
        if exit_liquidity < 45:
            return "The thesis may work, but exits look weaker than the headline yield"
        return "Mixed risk-reward profile with clear trade-offs"

    def _pool_thesis(self, kind: str, item: Dict[str, Any], fee_ratio: float, safety_score: int, yield_quality: int, exit_quality: int, caps: Sequence[Dict[str, Any]]) -> str:
        if any(cap.get("dimension") == "yield_quality" for cap in caps):
            return "Nominal APY is elevated, but weak reward quality or collapsing history keeps the yield from scoring as durable income."
        if str(item.get("il_risk") or item.get("ilRisk") or "").lower() == "yes":
            return "This setup only works if trading fees and asset correlation offset impermanent-loss drag over time."
        if fee_ratio >= 0.7 and safety_score >= 72:
            return "The core attraction is that a large share of the yield appears fee-backed rather than purely emissions-driven."
        if exit_quality < 45:
            return "The gross yield may be workable, but capital size should respect weak unwind depth and thin liquidity."
        if kind == "yield":
            return "This farm is only compelling if you are comfortable underwriting dependency risk and moderate durability uncertainty."
        return "The setup is usable, but the opportunity depends on size discipline and the protocol maintaining orderly market conditions."

    def _lending_thesis(self, item: Dict[str, Any], safety_score: int, yield_quality: int, exit_quality: int, caps: Sequence[Dict[str, Any]]) -> str:
        if any(cap.get("dimension") == "exit_quality" for cap in caps):
            return "Rates may look workable, but reserve utilization already threatens withdrawal quality under stress."
        if safety_score >= 80 and yield_quality >= 60:
            return "This is a cleaner lending setup where protocol quality, reserve headroom, and asset quality line up."
        if _safe_float(item.get("utilization_pct")) > 85:
            return "Any attractive carry needs to be discounted because reserve stress can impair exits and rate stability quickly."
        if exit_quality < 50:
            return "The market can work for smaller size, but reserve depth is not ideal for rapid exits."
        return "This lending opportunity is serviceable, but it depends on utilization staying orderly and dependencies remaining healthy."
