"""Deterministic DeFi scoring engine with hard caps and explicit dimensions."""

from __future__ import annotations

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


def _dimension(key: str, label: str, score: int, weight: float, summary: str) -> Dict[str, Any]:
    return RiskDimension(key=key, label=label, score=score, weight=weight, summary=summary).to_dict()


def _strategy_fit(safety_score: int, yield_quality: int) -> str:
    if safety_score >= 82 and yield_quality >= 48:
        return "conservative"
    if safety_score >= 65:
        return "balanced"
    return "aggressive"


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

        unresolved_critical = sum(1 for audit in audits if (audit.get("severity_findings") or {}).get("critical", 0) > 0)
        contract_safety = 70 + min(len(audits), 3) * 7 - unresolved_critical * 8
        if audits:
            ages = [parse_age_hours(audit.get("date")) for audit in audits]
            freshest = min((age for age in ages if age is not None), default=None)
            if freshest is not None and freshest > 24 * 365 * 2:
                contract_safety -= 8
        else:
            contract_safety -= 14

        incident_penalty = 0
        recent_critical = False
        for incident in incidents:
            severity = str(incident.get("severity") or "").upper()
            age_hours = parse_age_hours(incident.get("date"))
            if severity == "CRITICAL":
                incident_penalty += 16
            elif severity == "HIGH":
                incident_penalty += 10
            else:
                incident_penalty += 6
            if age_hours is not None and age_hours < 24 * 365 and severity == "CRITICAL":
                recent_critical = True
                incident_penalty += 8
        incident_history = clamp(88 - incident_penalty)

        market_maturity = 40
        if tvl > 1_000_000_000:
            market_maturity += 34
        elif tvl > 100_000_000:
            market_maturity += 24
        elif tvl > 10_000_000:
            market_maturity += 12
        market_maturity += min(surface_count, 8) * 2 + min(len(chains), 6) * 3
        market_maturity = clamp(market_maturity)

        governance_admin = clamp((docs_profile.get("governance_score") or 50))
        dependency_safety = clamp(100 - _safe_mean([dependency.get("risk_score", 40) for dependency in dependencies], default=42))

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
            notes=["Confidence falls when audit, docs, or deployment data is missing."] if not audits or not docs_profile.get("available") else [],
        )

        dimensions = [
            _dimension("contract_safety", "Contract Safety", clamp(contract_safety), 0.30, "Audit freshness, critical findings, and implementation-quality proxies."),
            _dimension("incident_history", "Incident History", incident_history, 0.20, "Historical exploit burden and time since major incidents."),
            _dimension("market_maturity", "Market Maturity", market_maturity, 0.20, "Battle-testing from TVL, deployments, and surface breadth."),
            _dimension("governance_admin", "Governance & Admin", governance_admin, 0.15, "Docs transparency, governance signals, timelocks, and admin posture."),
            _dimension("dependency_safety", "Dependency Safety", dependency_safety, 0.15, "Oracle, bridge, wrapper, and external dependency inheritance."),
        ]

        safety_score = clamp(sum(d["score"] * d["weight"] for d in dimensions))
        if recent_critical:
            safety_score = min(safety_score, 58)
        opportunity_score = clamp((safety_score * 0.60) + (market_maturity * 0.20) + (confidence["score"] * 0.20))
        risk_level = risk_level_from_score(100 - safety_score)

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
        tvl = _safe_float(item.get("tvl_usd") or item.get("tvlUsd"))
        apy = _safe_float(item.get("apy"))
        apy_base = _safe_float(item.get("apy_base") or item.get("apyBase"))
        sustainability_ratio = _safe_float(item.get("sustainability_ratio"), apy_base / apy if apy > 0 else 0)
        symbol_parts = [str(asset.get("symbol") or "").upper() for asset in assets if asset.get("role") != "reward"]
        reward_assets = [asset for asset in assets if asset.get("role") == "reward"]

        asset_safety = clamp(_safe_mean([asset.get("quality_score", 55) for asset in assets if asset.get("role") != "reward"], default=62))

        structure = 70
        il_risk = str(item.get("il_risk") or item.get("ilRisk") or "").lower() == "yes"
        exposure = str(item.get("exposure_type") or item.get("exposure") or "")
        if il_risk:
            structure -= 18 if exposure == "crypto-crypto" else 10
        if len(symbol_parts) > 2:
            structure -= 6
        if kind == "yield":
            structure -= 4
        if all(symbol in STABLE_SYMBOLS for symbol in symbol_parts if symbol):
            structure += 8
        structure_safety = clamp(structure)

        dependency_safety = clamp(100 - _safe_mean([dependency.get("risk_score", 42) for dependency in dependencies], default=42))
        governance_admin = clamp((docs_profile.get("governance_score") or 52))

        stress_history = 72
        if incidents:
            stress_history -= min(26, len(incidents) * 8)
        if history_summary.get("available"):
            if abs(_safe_float(history_summary.get("tvl_delta_30d"))) < 25:
                stress_history += 8
            if abs(_safe_float(history_summary.get("apy_delta_30d"))) > 100:
                stress_history -= 10
        else:
            stress_history -= 10
        stress_history = clamp(stress_history)

        safety_score = clamp(
            (protocol_safety * 0.25)
            + (asset_safety * 0.20)
            + (structure_safety * 0.20)
            + (dependency_safety * 0.15)
            + (governance_admin * 0.10)
            + (stress_history * 0.10)
        )

        fee_backed_share = clamp(sustainability_ratio * 100)
        apy_persistence = clamp(history_summary.get("apy_persistence_score") or 45)
        reward_quality = clamp(_safe_mean([asset.get("quality_score", 42) for asset in reward_assets], default=85 if not reward_assets else 42))
        emissions_dilution = clamp(100 - ((1 - sustainability_ratio) * 100))
        volume_efficiency = self._volume_efficiency_proxy(tvl, apy_base, apy, history_summary)

        yield_quality = clamp(
            (fee_backed_share * 0.30)
            + (apy_persistence * 0.20)
            + (reward_quality * 0.20)
            + (emissions_dilution * 0.15)
            + (volume_efficiency * 0.15)
        )

        tvl_depth = self._tvl_depth_score(tvl)
        simulated_slippage = self._simulated_slippage_score(tvl, apy)
        fragmentation = self._fragmentation_score(symbol_parts, tvl)
        withdrawal_constraints = self._withdrawal_constraints_score(kind, item, tvl)
        exit_quality = clamp((tvl_depth * 0.40) + (simulated_slippage * 0.20) + (fragmentation * 0.20) + (withdrawal_constraints * 0.20))

        confidence = build_confidence_report(
            required_fields=["chain", "project", "symbol", "tvl", "apy", "assets", "dependencies", "history"],
            present_fields=[
                "chain" if item.get("chain") else "",
                "project" if item.get("project") else "",
                "symbol" if item.get("symbol") else "",
                "tvl" if tvl > 0 else "",
                "apy" if apy > 0 else "",
                "assets" if assets else "",
                "dependencies" if dependencies else "",
                "history" if history_summary.get("available") else "",
            ],
            source_count=sum(1 for source in [item, assets, dependencies, docs_profile, history_summary] if source),
            freshness_hours=0.0 if history_summary.get("available") else None,
            notes=["Yield confidence is capped when history or asset inheritance is incomplete."] if not history_summary.get("available") else [],
        )

        safety_score, yield_quality, exit_quality, confidence, caps = self._apply_pool_caps(
            item,
            assets,
            incidents,
            docs_profile,
            safety_score,
            yield_quality,
            exit_quality,
            confidence,
        )

        if ranking == "conservative":
            opportunity_score = clamp((safety_score * 0.55) + (yield_quality * 0.20) + (exit_quality * 0.15) + (confidence["score"] * 0.10))
        else:
            opportunity_score = clamp((safety_score * 0.45) + (yield_quality * 0.30) + (exit_quality * 0.15) + (confidence["score"] * 0.10))

        dimensions = [
            _dimension("protocol_safety", "Protocol Safety", protocol_safety, 0.25, "Audit, incident, maturity, and governance profile of the protocol."),
            _dimension("asset_safety", "Asset Safety", asset_safety, 0.20, "Inherited risk from LP legs, collateral assets, and reward tokens."),
            _dimension("structure_safety", "Structure Safety", structure_safety, 0.20, "IL exposure, stable-vs-volatile composition, and setup fragility."),
            _dimension("dependency_safety", "Dependency Safety", dependency_safety, 0.15, "Bridge, oracle, wrapper, and external dependency inheritance."),
            _dimension("governance_admin", "Governance & Admin", governance_admin, 0.10, "Admin powers, docs transparency, and timelock signals."),
            _dimension("stress_history", "Stress History", stress_history, 0.10, "Incident burden plus APY/TVL stability over time."),
            _dimension("yield_quality", "Yield Quality", yield_quality, 0.30, "How real, durable, and non-inflationary the APY looks."),
            _dimension("exit_quality", "Exit Quality", exit_quality, 0.15, "How realistic it is to enter and exit without pain."),
            _dimension("confidence", "Confidence", confidence["score"], 0.10, "Coverage, freshness, and critical-field completeness."),
        ]

        return {
            "summary": {
                "opportunity_score": opportunity_score,
                "safety_score": safety_score,
                "yield_quality_score": yield_quality,
                "exit_quality_score": exit_quality,
                "confidence_score": confidence["score"],
                "risk_level": risk_level_from_score(100 - safety_score),
                "strategy_fit": _strategy_fit(safety_score, yield_quality),
                "headline": self._headline(kind, safety_score, yield_quality, exit_quality, confidence["partial_analysis"]),
                "thesis": self._pool_thesis(kind, item, safety_score, yield_quality, exit_quality, caps),
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
        tvl = _safe_float(item.get("tvlUsd") or item.get("tvl_usd"))
        supply = _safe_float(item.get("apy_supply"))
        borrow = _safe_float(item.get("apy_borrow"))
        utilization = _safe_float(item.get("utilization_pct"))
        asset_quality = clamp(_safe_mean([asset.get("quality_score", 60) for asset in assets if asset.get("role") != "reward"], default=68))

        oracle_liquidation = 76
        if utilization > 90:
            oracle_liquidation -= 12
        if incidents:
            oracle_liquidation -= min(14, len(incidents) * 5)
        if docs_profile.get("has_oracle_mentions"):
            oracle_liquidation += 6
        oracle_liquidation = clamp(oracle_liquidation)

        market_liquidity = self._tvl_depth_score(tvl)
        utilization_stress = clamp(100 - max(0.0, utilization - 45) * 1.2)
        governance_admin = clamp((docs_profile.get("governance_score") or 52))
        dependency_safety = clamp(100 - _safe_mean([dependency.get("risk_score", 40) for dependency in dependencies], default=40))

        safety_score = clamp(
            (protocol_safety * 0.30)
            + (oracle_liquidation * 0.20)
            + (market_liquidity * 0.15)
            + (utilization_stress * 0.15)
            + (asset_quality * 0.10)
            + (governance_admin * 0.10)
        )

        net_value = self._lending_net_value_score(supply, borrow)
        rate_stability = clamp(88 - max(0.0, utilization - 70) * 1.4 - max(0.0, borrow - 20) * 0.8)
        reserve_health = clamp((market_liquidity * 0.55) + (utilization_stress * 0.45))
        counterparty_quality = clamp((protocol_safety * 0.60) + (asset_quality * 0.40))
        incentive_dependence = 82 if supply <= 15 else 60 if supply <= 25 else 42
        yield_quality = clamp(
            (net_value * 0.35)
            + (rate_stability * 0.20)
            + (reserve_health * 0.20)
            + (counterparty_quality * 0.15)
            + (incentive_dependence * 0.10)
        )

        exit_quality = clamp((market_liquidity * 0.45) + (utilization_stress * 0.35) + (dependency_safety * 0.20))

        confidence = build_confidence_report(
            required_fields=["symbol", "chain", "tvl", "supply", "utilization", "assets", "dependencies"],
            present_fields=[
                "symbol" if item.get("symbol") else "",
                "chain" if item.get("chain") else "",
                "tvl" if tvl > 0 else "",
                "supply" if supply >= 0 else "",
                "utilization" if utilization > 0 else "",
                "assets" if assets else "",
                "dependencies" if dependencies else "",
            ],
            source_count=sum(1 for source in [item, assets, dependencies, docs_profile] if source),
            freshness_hours=0.0,
            notes=["Confidence falls when reserve health or asset inheritance coverage is incomplete."] if not assets else [],
        )

        safety_score, yield_quality, exit_quality, confidence, caps = self._apply_lending_caps(
            item,
            assets,
            incidents,
            docs_profile,
            safety_score,
            yield_quality,
            exit_quality,
            confidence,
        )

        if ranking == "conservative":
            opportunity_score = clamp((safety_score * 0.60) + (yield_quality * 0.15) + (exit_quality * 0.15) + (confidence["score"] * 0.10))
        else:
            opportunity_score = clamp((safety_score * 0.50) + (yield_quality * 0.25) + (exit_quality * 0.15) + (confidence["score"] * 0.10))

        dimensions = [
            _dimension("protocol_safety", "Protocol Safety", protocol_safety, 0.30, "Audit, incident, maturity, and governance profile of the lending protocol."),
            _dimension("oracle_liquidation", "Oracle & Liquidation Safety", oracle_liquidation, 0.20, "Oracle reliability, collateral repricing risk, and liquidation mechanics."),
            _dimension("market_liquidity", "Market Liquidity", market_liquidity, 0.15, "Reserve depth and withdraw capacity for meaningful size."),
            _dimension("utilization_stress", "Utilization Stress", utilization_stress, 0.15, "How close the market is to reserve stress or withdrawal failure."),
            _dimension("asset_quality", "Asset Quality", asset_quality, 0.10, "Collateral and borrow-asset quality inherited from token intelligence or heuristics."),
            _dimension("governance_admin", "Governance & Admin", governance_admin, 0.10, "Admin powers, docs transparency, and timelock signals."),
            _dimension("yield_quality", "Yield Quality", yield_quality, 0.25, "Net rate value, reserve health, rate stability, and incentive dependence."),
            _dimension("exit_quality", "Exit Quality", exit_quality, 0.15, "Depth, utilization headroom, and dependency-driven unwind quality."),
            _dimension("confidence", "Confidence", confidence["score"], 0.10, "Coverage, freshness, and critical-field completeness."),
        ]

        return {
            "summary": {
                "opportunity_score": opportunity_score,
                "safety_score": safety_score,
                "yield_quality_score": yield_quality,
                "exit_quality_score": exit_quality,
                "confidence_score": confidence["score"],
                "risk_level": risk_level_from_score(100 - safety_score),
                "strategy_fit": _strategy_fit(safety_score, yield_quality),
                "headline": self._headline("lending", safety_score, yield_quality, exit_quality, confidence["partial_analysis"]),
                "thesis": self._lending_thesis(item, safety_score, yield_quality, exit_quality, caps),
            },
            "dimensions": dimensions,
            "confidence": confidence,
            "score_caps": caps,
        }

    def _apply_pool_caps(
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
        recent_critical = any(
            str(incident.get("severity") or "").upper() == "CRITICAL"
            and (parse_age_hours(incident.get("date")) or 10 ** 9) < 24 * 365
            for incident in incidents
        )
        if recent_critical:
            safety_score = min(safety_score, 42)
            caps.append(ScoreCap("safety", 42, "Recent critical exploit history caps safety until resilience is re-established.").to_dict())

        reward_assets = [asset for asset in assets if asset.get("role") == "reward"]
        low_quality_reward = any((asset.get("quality_score") or 100) < 45 for asset in reward_assets)
        if low_quality_reward:
            yield_quality = min(yield_quality, 45)
            caps.append(ScoreCap("yield_quality", 45, "Low-quality reward token caps yield quality even if nominal APY is high.").to_dict())

        tvl = _safe_float(item.get("tvl_usd") or item.get("tvlUsd"))
        if tvl < 250_000:
            exit_quality = min(exit_quality, 40)
            caps.append(ScoreCap("exit_quality", 40, "Shallow liquidity caps exit quality.").to_dict())

        if confidence.get("partial_analysis"):
            confidence = {**confidence, "score": min(confidence.get("score", 0), 60), "label": "PARTIAL"}
            caps.append(ScoreCap("confidence", 60, "Partial analysis caps confidence until missing fields are resolved.").to_dict())

        stable_assets = [asset for asset in assets if str(asset.get("symbol") or "").upper() in STABLE_SYMBOLS]
        risky_stable = any((asset.get("quality_score") or 100) < 70 for asset in stable_assets)
        if risky_stable:
            safety_score = min(100, safety_score - 8)
            caps.append(ScoreCap("safety", safety_score, "Stable-leg quality penalty applied for depeg-prone or bridged stable exposure.").to_dict())

        if docs_profile.get("has_admin_mentions") and not docs_profile.get("has_timelock_mentions"):
            safety_score = min(100, safety_score - 6)
            caps.append(ScoreCap("safety", safety_score, "Governance/admin penalty applied because admin controls appear stronger than timelock protection.").to_dict())

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
        recent_critical = any(
            str(incident.get("severity") or "").upper() == "CRITICAL"
            and (parse_age_hours(incident.get("date")) or 10 ** 9) < 24 * 365
            for incident in incidents
        )
        if recent_critical:
            safety_score = min(safety_score, 48)
            caps.append(ScoreCap("safety", 48, "Recent critical exploit history caps lending safety.").to_dict())

        utilization = _safe_float(item.get("utilization_pct"))
        if utilization > 90:
            exit_quality = min(exit_quality, 42)
            caps.append(ScoreCap("exit_quality", 42, "Reserve utilization cap applied because withdrawals may fail under stress.").to_dict())

        risky_asset = any((asset.get("quality_score") or 100) < 45 for asset in assets if asset.get("role") != "reward")
        if risky_asset:
            safety_score = min(safety_score, 58)
            caps.append(ScoreCap("safety", 58, "Low-quality collateral or borrowed asset caps lending safety.").to_dict())

        if confidence.get("partial_analysis"):
            confidence = {**confidence, "score": min(confidence.get("score", 0), 60), "label": "PARTIAL"}
            caps.append(ScoreCap("confidence", 60, "Partial analysis caps confidence until coverage improves.").to_dict())

        if docs_profile.get("has_admin_mentions") and not docs_profile.get("has_timelock_mentions"):
            safety_score = min(100, safety_score - 6)
            caps.append(ScoreCap("safety", safety_score, "Governance/admin penalty applied because admin controls appear stronger than timelock protection.").to_dict())

        return safety_score, yield_quality, exit_quality, confidence, caps

    def _tvl_depth_score(self, tvl: float) -> int:
        if tvl > 100_000_000:
            return 94
        if tvl > 25_000_000:
            return 82
        if tvl > 10_000_000:
            return 72
        if tvl > 1_000_000:
            return 58
        if tvl > 250_000:
            return 46
        return 28

    def _simulated_slippage_score(self, tvl: float, apy: float) -> int:
        base = self._tvl_depth_score(tvl)
        if apy > 150:
            base -= 8
        elif apy > 40:
            base -= 4
        return clamp(base)

    def _fragmentation_score(self, symbol_parts: Sequence[str], tvl: float) -> int:
        score = 78
        if len(symbol_parts) > 2:
            score -= 12
        if tvl < 1_000_000:
            score -= 10
        return clamp(score)

    def _withdrawal_constraints_score(self, kind: str, item: Dict[str, Any], tvl: float) -> int:
        score = 76
        if kind == "yield" and _safe_float(item.get("sustainability_ratio"), 1.0) < 0.2:
            score -= 8
        if tvl < 500_000:
            score -= 14
        return clamp(score)

    def _volume_efficiency_proxy(self, tvl: float, apy_base: float, apy: float, history_summary: Dict[str, Any]) -> int:
        score = 48
        if apy > 0 and apy_base > 0:
            score += min(32, (apy_base / apy) * 40)
        if tvl > 10_000_000:
            score += 10
        if abs(_safe_float(history_summary.get("tvl_delta_30d"))) < 25:
            score += 6
        return clamp(score)

    def _lending_net_value_score(self, supply: float, borrow: float) -> int:
        score = 52
        if 3 <= supply <= 12:
            score += 24
        elif 0 < supply < 3:
            score += 12
        elif supply > 20:
            score -= 12
        if borrow > 0:
            if borrow < 8:
                score += 10
            elif borrow > 25:
                score -= 10
        return clamp(score)

    def _headline(self, kind: str, safety_score: int, yield_quality: int, exit_quality: int, partial: bool) -> str:
        if partial:
            return "Promising surface, but analysis coverage is partial."
        if safety_score >= 80 and yield_quality >= 62:
            return "High-quality, evidence-backed capital path"
        if kind == "lending" and safety_score >= 78:
            return "Battle-tested lending setup with manageable reserve risk"
        if yield_quality >= 70 and safety_score < 65:
            return "Attractive nominal yield with material fragility beneath the surface"
        if exit_quality < 45:
            return "Thesis may work, but unwind quality is weak"
        return "Risk-adjusted setup with mixed strengths and weaknesses"

    def _pool_thesis(self, kind: str, item: Dict[str, Any], safety_score: int, yield_quality: int, exit_quality: int, caps: Sequence[Dict[str, Any]]) -> str:
        if any(cap.get("dimension") == "yield_quality" for cap in caps):
            return "Nominal APY is elevated, but reward-token quality or emissions dependence limits how much of that yield is real."
        if str(item.get("il_risk") or item.get("ilRisk") or "").lower() == "yes":
            return "This setup depends on fees and asset correlation offsetting impermanent-loss exposure."
        if exit_quality < 45:
            return "The gross yield may look workable, but capital size should respect weak unwind depth."
        if safety_score >= 75 and yield_quality >= 55:
            return "The attraction is a cleaner mix of protocol quality, asset quality, and reasonably durable yield."
        if kind == "yield":
            return "This farm is only attractive if you accept moderate uncertainty around durability, dependency risk, and exits."
        return "The setup is usable, but only if your capital size matches the available depth and dependency profile."

    def _lending_thesis(self, item: Dict[str, Any], safety_score: int, yield_quality: int, exit_quality: int, caps: Sequence[Dict[str, Any]]) -> str:
        if any(cap.get("dimension") == "exit_quality" for cap in caps):
            return "Rates may look good, but reserve utilization already threatens withdrawal quality under stress."
        if safety_score >= 80 and yield_quality >= 60:
            return "This is a cleaner lending setup where protocol quality, reserve health, and asset quality align."
        if _safe_float(item.get("utilization_pct")) > 85:
            return "Rate attractiveness needs to be discounted because reserve stress can impair exits quickly."
        if exit_quality < 50:
            return "The market is usable for smaller size, but reserve depth is not ideal for fast exits."
        return "This lending opportunity is serviceable, but it depends on utilization staying orderly and dependencies remaining healthy."
