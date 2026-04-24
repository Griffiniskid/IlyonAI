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
    assert env.data["analysis_trace"][0].startswith("Filtered live opportunities to solana")
    assert {card.card_type for card in env.extra_cards} == {"sentinel_matrix", "execution_plan"}
