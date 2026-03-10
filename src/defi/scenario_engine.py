"""Scenario generation and simulation logic for DeFi opportunities and positions."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from src.defi.entities import ScenarioResult, SimulationResult


def _clamp(value: float, lower: float = 0, upper: float = 100) -> float:
    return max(lower, min(upper, value))


class DefiScenarioEngine:
    def build_opportunity_scenarios(self, kind: str, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        if kind == "lending":
            return [
                ScenarioResult(
                    key="utilization_spike",
                    title="Utilization spike",
                    impact="Withdraw quality can deteriorate quickly if utilization moves into the 90%+ zone.",
                    severity="high",
                    trigger="Borrow demand surges, collateral gets stressed, or reserve depth shrinks.",
                ).to_dict(),
                ScenarioResult(
                    key="oracle_or_collateral_shock",
                    title="Oracle or collateral shock",
                    impact="Liquidations can cluster if collateral reprices quickly or oracle conditions degrade.",
                    severity="high",
                    trigger="Underlying collateral moves sharply or chain conditions impair oracle freshness.",
                ).to_dict(),
                ScenarioResult(
                    key="governance_intervention",
                    title="Emergency governance intervention",
                    impact="A pause, cap reduction, or parameter hotfix can change exits and carrying costs.",
                    severity="medium",
                    trigger="Emergency governance, guardian, or multisig action lands during stress.",
                ).to_dict(),
            ]

        scenarios = [
            ScenarioResult(
                key="emissions_decay",
                title="Reward emissions fade",
                impact="Displayed APY compresses quickly if emissions slow before organic fee generation catches up.",
                severity="medium",
                trigger="Fee-backed yield ratio trends down for multiple refreshes.",
            ).to_dict(),
            ScenarioResult(
                key="liquidity_outflow",
                title="TVL outflow",
                impact="Exit quality deteriorates as liquidity leaves and slippage rises.",
                severity="medium",
                trigger="TVL drops sharply while APY rises.",
            ).to_dict(),
        ]
        if str(item.get("il_risk") or item.get("ilRisk") or "").lower() == "yes":
            scenarios.append(
                ScenarioResult(
                    key="relative_price_move",
                    title="Relative price divergence",
                    impact="A strong move between pool legs can erase headline yield through impermanent loss.",
                    severity="high",
                    trigger="Volatility spikes or correlation weakens between pool assets.",
                ).to_dict()
            )
        if item.get("stablecoin") or "USD" in str(item.get("symbol") or "").upper():
            scenarios.append(
                ScenarioResult(
                    key="stable_depeg",
                    title="Stablecoin depeg",
                    impact="Stable-leg weakness can overwhelm low-volatility assumptions and create asymmetric exits.",
                    severity="high",
                    trigger="Redemption pressure, bridge stress, or on-chain peg drift emerges.",
                ).to_dict()
            )
        return scenarios

    def simulate_lp(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        deposit_usd = float(payload.get("deposit_usd") or 0)
        apy = float(payload.get("apy") or 0)
        tvl_usd = max(float(payload.get("tvl_usd") or 0), 1.0)
        price_move_pct = float(payload.get("price_move_pct") or 0)
        emissions_decay_pct = float(payload.get("emissions_decay_pct") or 0)
        stable_depeg_pct = float(payload.get("stable_depeg_pct") or 0)

        ratio = max(0.01, 1 + (price_move_pct / 100))
        il_pct = abs((2 * math.sqrt(ratio) / (1 + ratio)) - 1) * 100
        annual_yield_usd = deposit_usd * (apy / 100)
        yield_after_decay = annual_yield_usd * max(0.0, 1 - (emissions_decay_pct / 100))
        stable_depeg_loss = deposit_usd * max(0.0, stable_depeg_pct / 100) * 0.5
        exit_impact_pct = min(35.0, (deposit_usd / max(tvl_usd, 1.0)) * 120)

        scenarios = [
            {
                "name": "Price divergence",
                "summary": "Estimated impermanent loss under the configured relative price move.",
                "metric": "impermanent_loss_pct",
                "value": round(il_pct, 2),
                "unit": "%",
                "severity": "high" if il_pct > 8 else "medium" if il_pct > 3 else "low",
            },
            {
                "name": "Emissions decay",
                "summary": "Estimated annualized yield after emissions compression.",
                "metric": "yield_after_decay_usd",
                "value": round(yield_after_decay, 2),
                "unit": "usd",
                "severity": "high" if emissions_decay_pct > 60 else "medium" if emissions_decay_pct > 25 else "low",
            },
            {
                "name": "Stable depeg",
                "summary": "Loss estimate if the stable leg depegs by the configured percentage.",
                "metric": "stable_depeg_loss_usd",
                "value": round(stable_depeg_loss, 2),
                "unit": "usd",
                "severity": "high" if stable_depeg_pct >= 5 else "medium" if stable_depeg_pct > 0 else "low",
            },
            {
                "name": "Exit impact",
                "summary": "Approximate exit penalty proxy for this size relative to TVL.",
                "metric": "exit_impact_pct",
                "value": round(exit_impact_pct, 2),
                "unit": "%",
                "severity": "high" if exit_impact_pct > 12 else "medium" if exit_impact_pct > 4 else "low",
            },
        ]

        recommendations = [
            "Reduce position size if exit impact is above 10% of the standard slippage proxy.",
            "Treat emissions-heavy APY as temporary and underwrite the position off fee-backed yield instead.",
        ]
        if il_pct > 8:
            recommendations.append("Do not size this like a stable yield product; relative price risk dominates the thesis.")
        if stable_depeg_pct > 0:
            recommendations.append("Apply a separate stablecoin risk budget if any leg can depeg or is bridge-dependent.")

        result = SimulationResult(
            kind="lp",
            summary="LP stress simulation over price divergence, emissions decay, stable weakness, and exit depth.",
            base_case={
                "deposit_usd": deposit_usd,
                "apy": apy,
                "annual_yield_usd": round(annual_yield_usd, 2),
                "tvl_usd": tvl_usd,
            },
            scenarios=scenarios,
            recommendations=recommendations,
        )
        return result.to_dict()

    def simulate_lending(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        collateral_usd = float(payload.get("collateral_usd") or 0)
        debt_usd = float(payload.get("debt_usd") or 0)
        liquidation_threshold = float(payload.get("liquidation_threshold") or 0.8)
        collateral_drop_pct = float(payload.get("collateral_drop_pct") or 0)
        stable_depeg_pct = float(payload.get("stable_depeg_pct") or 0)
        borrow_rate_spike_pct = float(payload.get("borrow_rate_spike_pct") or 0)
        utilization_pct = float(payload.get("utilization_pct") or 0)
        utilization_shock_pct = float(payload.get("utilization_shock_pct") or 0)

        effective_collateral = collateral_usd * (1 - (collateral_drop_pct / 100))
        depeg_adjusted_collateral = effective_collateral * (1 - (stable_depeg_pct / 100))
        base_hf = float("inf") if debt_usd <= 0 else (collateral_usd * liquidation_threshold) / max(debt_usd, 1e-9)
        stressed_hf = float("inf") if debt_usd <= 0 else (depeg_adjusted_collateral * liquidation_threshold) / max(debt_usd, 1e-9)
        utilization_after = min(100.0, utilization_pct + utilization_shock_pct)
        withdraw_headroom = max(0.0, 100 - utilization_after)
        carry_cost_delta = debt_usd * (borrow_rate_spike_pct / 100)

        scenarios = [
            {
                "name": "Collateral shock",
                "summary": "Health factor after collateral drawdown and stable depeg assumptions.",
                "metric": "stressed_health_factor",
                "value": round(stressed_hf, 3) if math.isfinite(stressed_hf) else float("inf"),
                "unit": "hf",
                "severity": "high" if stressed_hf < 1.1 else "medium" if stressed_hf < 1.5 else "low",
            },
            {
                "name": "Borrow-rate spike",
                "summary": "Estimated annualized extra carry cost from a borrow-rate jump.",
                "metric": "carry_cost_delta_usd",
                "value": round(carry_cost_delta, 2),
                "unit": "usd",
                "severity": "high" if borrow_rate_spike_pct > 15 else "medium" if borrow_rate_spike_pct > 5 else "low",
            },
            {
                "name": "Utilization spike",
                "summary": "Reserve headroom after utilization shock.",
                "metric": "withdraw_headroom_pct",
                "value": round(withdraw_headroom, 2),
                "unit": "%",
                "severity": "high" if withdraw_headroom < 10 else "medium" if withdraw_headroom < 25 else "low",
            },
        ]

        recommendations = [
            "Target a health factor buffer that still survives correlated collateral and stable stress.",
            "Do not assume borrow rates stay benign when utilization approaches the 90% zone.",
        ]
        if math.isfinite(stressed_hf) and stressed_hf < 1.2:
            recommendations.append("Add collateral or reduce leverage; stressed health factor is too close to liquidation.")
        if withdraw_headroom < 15:
            recommendations.append("Reserve utilization is too tight for large exits; treat withdraw reliability as impaired.")

        result = SimulationResult(
            kind="lending",
            summary="Lending stress simulation over collateral drawdown, stable weakness, borrow-rate spikes, and reserve stress.",
            base_case={
                "collateral_usd": collateral_usd,
                "debt_usd": debt_usd,
                "liquidation_threshold": liquidation_threshold,
                "base_health_factor": round(base_hf, 3) if math.isfinite(base_hf) else float("inf"),
                "utilization_pct": utilization_pct,
            },
            scenarios=scenarios,
            recommendations=recommendations,
        )
        return result.to_dict()

    def analyze_position(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        kind = str(payload.get("kind") or "lending").lower()
        if kind == "lp":
            result = self.simulate_lp(payload)
        else:
            result = self.simulate_lending(payload)

        result["position_size_usd"] = float(payload.get("deposit_usd") or payload.get("collateral_usd") or 0)
        result["monitor_triggers"] = [
            "Protocol incident or emergency governance action",
            "Reward-token quality deterioration or sudden APY spike",
            "Reserve utilization or slippage proxies moving into stress territory",
        ]
        return result
