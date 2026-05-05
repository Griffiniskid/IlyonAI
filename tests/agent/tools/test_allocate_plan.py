from types import SimpleNamespace

import pytest

from src.agent.tools._base import ToolCtx
from src.agent.tools.allocate_plan import allocate_plan


class StubIntelligenceEngine:
    def __init__(self):
        self.calls = []

    async def analyze_market(
        self,
        *,
        chain=None,
        query=None,
        min_tvl=0,
        min_apy=0,
        limit=12,
        include_ai=True,
        ranking_profile=None,
    ):
        self.calls.append(("analyze_market", chain, ranking_profile, include_ai))
        return {
            "top_opportunities": [
                {
                    "id": "lending--sol-usdc",
                    "kind": "lending",
                    "chain": "solana",
                    "protocol_name": "Kamino Finance",
                    "symbol": "USDC",
                    "summary": {"opportunity_score": 82},
                },
                {
                    "id": "lending--sol-sol",
                    "kind": "lending",
                    "chain": "solana",
                    "protocol_name": "Kamino Finance",
                    "symbol": "SOL",
                    "summary": {"opportunity_score": 78},
                },
            ],
            "ai_market_brief": {
                "headline": "Solana lending remains the cleanest route right now.",
                "summary": "Kamino dominates the liquid lending set in this fixture.",
            },
        }

    async def get_opportunity_profile(self, opportunity_id, include_ai=True, ranking_profile=None):
        self.calls.append(("get_opportunity_profile", opportunity_id, ranking_profile, include_ai))
        if opportunity_id == "lending--sol-usdc":
            return {
                "id": opportunity_id,
                "kind": "lending",
                "protocol_name": "Kamino Finance",
                "symbol": "USDC",
                "chain": "solana",
                "apy": 6.8,
                "tvl_usd": 7_400_000,
                "summary": {
                    "overall_score": 82,
                    "opportunity_score": 82,
                    "safety_score": 68,
                    "yield_durability_score": 79,
                    "exit_liquidity_score": 58,
                    "confidence_score": 74,
                    "risk_level": "MEDIUM",
                    "strategy_fit": "balanced",
                    "headline": "USDC supply on Kamino is competitive for balanced capital.",
                    "thesis": "Carry is strongest where reserve health and exits remain orderly.",
                },
                "ai_analysis": {
                    "summary": "The setup is attractive because utilization is healthy and the exit path stays liquid.",
                    "main_risks": ["Borrow demand shock", "Oracle degradation"],
                    "monitor_triggers": ["Utilization > 90%"],
                },
                "score_caps": [],
            }
        return {
            "id": opportunity_id,
            "kind": "lending",
            "protocol_name": "Kamino Finance",
            "symbol": "SOL",
            "chain": "solana",
            "apy": 4.1,
            "tvl_usd": 33_500_000,
            "summary": {
                "overall_score": 78,
                "opportunity_score": 78,
                "safety_score": 59,
                "yield_durability_score": 78,
                "exit_liquidity_score": 68,
                "confidence_score": 72,
                "risk_level": "MEDIUM",
                "strategy_fit": "aggressive",
                "headline": "SOL supply is liquid, but still more cyclical than stablecoin carry.",
                "thesis": "Use smaller size because the carry depends on market conditions staying calm.",
            },
            "ai_analysis": {
                "summary": "This is attractive when you want beta plus liquid lending exposure.",
                "main_risks": ["Collateral volatility"],
                "monitor_triggers": ["SOL drawdown > 10%"],
            },
            "score_caps": [],
        }


class _ConstraintEngine:
    def __init__(self):
        self.market_calls: list[dict] = []
        self.profile_calls: list[str] = []

    async def analyze_market(self, **kwargs):
        self.market_calls.append(kwargs)
        return {
            "top_opportunities": [
                {
                    "id": "pool--low-safe",
                    "kind": "pool",
                    "chain": "ethereum",
                    "protocol_name": "Aave V3",
                    "symbol": "USDC",
                    "apy": 4.2,
                    "summary": {"opportunity_score": 88, "risk_level": "LOW"},
                },
                {
                    "id": "pool--high-aggressive",
                    "kind": "pool",
                    "chain": "ethereum",
                    "protocol_name": "Pendle",
                    "symbol": "WETH",
                    "apy": 92.0,
                    "summary": {"opportunity_score": 71, "risk_level": "HIGH"},
                },
                {
                    "id": "pool--medium-balanced",
                    "kind": "pool",
                    "chain": "ethereum",
                    "protocol_name": "Convex",
                    "symbol": "STETH",
                    "apy": 24.5,
                    "summary": {"opportunity_score": 75, "risk_level": "MEDIUM"},
                },
            ],
            "ai_market_brief": {"summary": "test"},
        }

    async def get_opportunity_profile(self, opportunity_id, include_ai=True, ranking_profile=None):
        self.profile_calls.append(opportunity_id)
        seed = {
            "pool--low-safe": ("Aave V3", "USDC", 4.2, "LOW", 88),
            "pool--high-aggressive": ("Pendle", "WETH", 92.0, "HIGH", 71),
            "pool--medium-balanced": ("Convex", "STETH", 24.5, "MEDIUM", 75),
        }[opportunity_id]
        return {
            "id": opportunity_id,
            "kind": "pool",
            "protocol_name": seed[0],
            "symbol": seed[1],
            "chain": "ethereum",
            "apy": seed[2],
            "tvl_usd": 50_000_000,
            "summary": {
                "overall_score": seed[4],
                "opportunity_score": seed[4],
                "safety_score": 70,
                "yield_durability_score": 70,
                "exit_liquidity_score": 70,
                "confidence_score": 70,
                "risk_level": seed[3],
                "strategy_fit": "balanced",
                "headline": "test",
                "thesis": "test",
            },
            "ai_analysis": {"summary": "test", "main_risks": [], "monitor_triggers": []},
            "score_caps": [],
        }


@pytest.mark.asyncio
async def test_allocate_plan_filters_by_target_apy_and_risk_levels():
    engine = _ConstraintEngine()
    services = SimpleNamespace(defi_intelligence=engine)
    ctx = ToolCtx(services=services, user_id=0, wallet="guest")

    env = await allocate_plan(
        ctx,
        usd_amount=10_000,
        risk_budget="aggressive",
        target_apy=80.0,
        min_apy=60.0,
        max_apy=160.0,
        risk_levels=["MEDIUM", "HIGH"],
    )

    assert env.ok
    assert env.card_type == "allocation"
    assert engine.market_calls, "engine.analyze_market was not invoked"
    market_call = engine.market_calls[0]
    assert market_call["min_apy"] >= 50.0
    selected_ids = engine.profile_calls
    assert "pool--low-safe" not in selected_ids
    assert "pool--high-aggressive" in selected_ids
    positions = env.card_payload["positions"]
    assert all(pos["risk"].upper() in {"MEDIUM", "HIGH"} for pos in positions)
    assert any(float(pos["apy"].rstrip("%")) >= 50.0 for pos in positions)


@pytest.mark.asyncio
async def test_allocate_plan_uses_chain_filtered_deep_profiles():
    engine = StubIntelligenceEngine()
    services = SimpleNamespace(defi_intelligence=engine)
    ctx = ToolCtx(services=services, user_id=0, wallet="guest")

    env = await allocate_plan(
        ctx,
        usd_amount=1000,
        risk_budget="balanced",
        chains=["solana"],
        asset_hint="USDT",
    )

    assert env.ok
    assert env.card_type == "allocation"
    assert env.card_payload is not None
    assert {row[1] for row in engine.calls if row[0] == "analyze_market"} == {"solana"}
    assert len([row for row in engine.calls if row[0] == "get_opportunity_profile"]) == 2
    assert all(position["chain"] == "sol" for position in env.card_payload["positions"])
    trace = env.data["analysis_trace"]
    assert len(trace) >= 6
    assert any("Filtered" in line and "solana" in line for line in trace)
    assert any("Sentinel" in line for line in trace)
    assert any("Ilyon Shield" in line for line in trace)
    assert any("execution plan" in line.lower() for line in trace)
    assert {card.card_type for card in env.extra_cards} == {"sentinel_matrix", "execution_plan"}
