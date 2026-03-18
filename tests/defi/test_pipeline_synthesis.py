import json
from pathlib import Path

from src.defi.pipeline.synthesize import SynthesisPipeline
import pytest

SOLANA_FIXTURE = {"chain": "solana", "protocol_slug": "orca", "product_type": "stable_lp"}
CHAIN_MATRIX = ["solana", "ethereum", "base", "arbitrum", "bsc", "polygon", "optimism", "avalanche"]
EVM_FIXTURE = {"chain": "base", "protocol_slug": "aave-v3", "product_type": "lending_supply_like"}

def test_synthesis_combines_deterministic_and_ai_scores_without_bypassing_caps():
    pipeline = SynthesisPipeline()

    analysis = pipeline.combine(
        identity={
            "id": "opp_aave_base_supply",
            "chain": "base",
            "kind": "lending",
            "protocol_slug": "aave-v3",
            "protocol_name": "Aave V3",
            "category": "lending",
            "assets": ["USDC"],
            "strategy_family": "carry",
        },
        market={"apy": 5.2, "tvl_usd": 12000000, "liquidity_usd": 4400000, "market_regime": "balanced"},
        deterministic={
            "final_score": 62,
            "safety_score": 42,
            "apr_quality_score": 64,
            "exit_quality_score": 71,
            "resilience_score": 58,
            "confidence_score": 74,
            "gross_apr": 5.2,
            "haircut_apr": 4.8,
            "net_expected_apr": 3.9,
            "weighted_risk_burden": 16,
            "risk_to_apr_ratio": 3.1,
            "strategy_fit": "balanced",
            "headline": "Recent incident caps capital confidence.",
            "hard_caps": [
                {
                    "code": "recent_critical_incident",
                    "dimension": "safety",
                    "cap": 42,
                    "reason": "Recent critical incident caps deterministic safety until resilience is re-established.",
                }
            ],
            "fragility_flags": ["recent_critical_incident"],
            "kill_switches": ["recent_critical_incident"],
            "confidence_reasoning": ["Recent incident keeps evidence quality from supporting deployment."],
        },
        ai={"judgment_score": 90},
    )

    assert analysis.scores.ai_judgment_score == 90
    assert analysis.scores.final_deployability_score <= 62
    assert analysis.recommendation.action == "avoid"
    assert analysis.identity.protocol_slug == "aave-v3"


def test_synthesis_honors_explicit_hard_cap_value_in_final_score():
    pipeline = SynthesisPipeline()

    analysis = pipeline.combine(
        deterministic={
            "final_score": 62,
            "safety_score": 62,
            "apr_quality_score": 62,
            "exit_quality_score": 62,
            "resilience_score": 62,
            "confidence_score": 80,
            "hard_caps": [
                {
                    "code": "exit_liquidity_cap",
                    "dimension": "exit_quality",
                    "cap": 41,
                    "reason": "Exit depth is too thin for deployment sizing.",
                }
            ],
        },
        ai={"judgment_score": 95},
    )

    assert analysis.scores.final_deployability_score == 41
    assert analysis.scores.capped_score == 41


def test_synthesis_preserves_explicit_zero_deterministic_component_scores():
    pipeline = SynthesisPipeline()

    analysis = pipeline.combine(
        deterministic={
            "final_score": 0,
            "overall_score": 91,
            "safety_score": 0,
            "apr_quality_score": 0,
            "exit_quality_score": 0,
            "resilience_score": 0,
            "confidence_score": 0,
            "hard_caps": [],
        },
        ai={"judgment_score": 0},
    )

    assert analysis.scores.deterministic_score == 0
    assert analysis.scores.ai_judgment_score == 0
    assert analysis.scores.final_deployability_score == 0
    assert analysis.scores.safety_score == 0
    assert analysis.scores.apr_quality_score == 0
    assert analysis.scores.exit_quality_score == 0
    assert analysis.scores.resilience_score == 0
    assert analysis.scores.confidence_score == 0


def test_synthesis_emits_full_opportunity_analysis_contract():
    pipeline = SynthesisPipeline()

    analysis = pipeline.combine(
        identity={
            "id": "opp_curve_eth_stables",
            "chain": "ethereum",
            "kind": "pool",
            "protocol_slug": "curve",
            "protocol_name": "Curve",
            "category": "dex",
            "assets": ["USDC", "USDT", "DAI"],
            "strategy_family": "liquidity",
            "title": "Curve stable pool",
        },
        market={
            "apy": 8.6,
            "tvl_usd": 48000000,
            "liquidity_usd": 7300000,
            "volume_24h_usd": 2500000,
            "utilization_ratio": 0.54,
            "market_regime": "range-bound",
        },
        deterministic={
            "final_score": 78,
            "safety_score": 81,
            "apr_quality_score": 74,
            "exit_quality_score": 79,
            "resilience_score": 77,
            "confidence_score": 84,
            "gross_apr": 8.6,
            "haircut_apr": 7.9,
            "net_expected_apr": 6.8,
            "weighted_risk_burden": 12,
            "risk_to_apr_ratio": 1.5,
            "strategy_fit": "balanced",
            "headline": "Durable carry with manageable exit conditions.",
            "hard_caps": [],
            "fragility_flags": ["reward_decay_watch"],
            "kill_switches": [],
            "confidence_reasoning": ["Coverage is broad across liquidity, docs, and protocol history."],
        },
        ai={
            "judgment_score": 70,
            "headline": "Solid carry if stable liquidity stays sticky.",
            "summary": "The allocator case holds because fee-backed carry and exits are both credible.",
            "best_for": "balanced capital",
            "why_it_exists": "Trading demand is carrying most of the yield rather than short-lived emissions.",
            "main_risks": ["Stablecoin composition can weaken if one leg de-risks suddenly."],
            "monitor_triggers": ["Watch for TVL slipping faster than volume."],
            "safer_alternative": "Favor the deepest stable pool if sizing increases.",
        },
        factors=[
            {
                "key": "exit-liquidity",
                "label": "Exit liquidity",
                "normalized_score": 79,
                "score_impact": 9,
                "scenario_sensitivity": "medium",
                "summary": "Depth supports moderate exits without severe slippage.",
            }
        ],
        scenarios=[
            {
                "name": "base",
                "outlook": "Carry remains attractive while stable volumes hold.",
                "trigger": "Range-bound conditions persist",
                "probability": "medium",
            }
        ],
        evidence=[
            {
                "key": "curve-volume",
                "title": "Curve volume",
                "summary": "Volume remains healthy across the last week.",
                "source": "defillama",
                "freshness_hours": 4.0,
            }
        ],
    )

    payload = json.loads(analysis.model_dump_json())

    assert sorted(payload) == [
        "behavior",
        "evidence",
        "factors",
        "identity",
        "market",
        "observability",
        "recommendation",
        "scenarios",
        "scores",
    ]
    assert payload["scores"]["final_deployability_score"] == 74
    assert payload["recommendation"]["action"] == "deploy_small"
    assert payload["evidence"][0]["source"] == "defillama"

@pytest.mark.parametrize("chain", CHAIN_MATRIX)
def test_synthesis_supports_chain_matrix(chain):
    pipeline = SynthesisPipeline()
    analysis = pipeline.combine(
        identity={"id": f"opp_{chain}", "chain": chain, "kind": "pool", "protocol_slug": "test", "protocol_name": "Test", "category": "dex", "assets": ["USDC"], "strategy_family": "carry"},
        market={"apy": 5.0, "tvl_usd": 1000000, "liquidity_usd": 100000, "market_regime": "balanced"},
        deterministic={"final_score": 75, "safety_score": 75, "apr_quality_score": 75, "exit_quality_score": 75, "resilience_score": 75, "confidence_score": 75, "gross_apr": 5.0, "haircut_apr": 4.5, "net_expected_apr": 4.0, "weighted_risk_burden": 10, "risk_to_apr_ratio": 2.0, "strategy_fit": "balanced", "headline": "Test", "hard_caps": [], "fragility_flags": [], "kill_switches": [], "confidence_reasoning": []},
        ai={"judgment_score": 75}
    )
    assert analysis.identity.chain == chain
    assert analysis.scores.final_deployability_score == 75

def test_synthesis_supports_solana_fixture():
    pipeline = SynthesisPipeline()
    analysis = pipeline.combine(
        identity={"id": "opp_sol", "chain": SOLANA_FIXTURE["chain"], "kind": "pool", "protocol_slug": SOLANA_FIXTURE["protocol_slug"], "protocol_name": "Orca", "category": "dex", "assets": ["SOL", "USDC"], "strategy_family": "carry"},
        market={"apy": 5.0, "tvl_usd": 1000000, "liquidity_usd": 100000, "market_regime": "balanced"},
        deterministic={"final_score": 75, "safety_score": 75, "apr_quality_score": 75, "exit_quality_score": 75, "resilience_score": 75, "confidence_score": 75, "gross_apr": 5.0, "haircut_apr": 4.5, "net_expected_apr": 4.0, "weighted_risk_burden": 10, "risk_to_apr_ratio": 2.0, "strategy_fit": "balanced", "headline": "Test", "hard_caps": [], "fragility_flags": [], "kill_switches": [], "confidence_reasoning": []},
        ai={"judgment_score": 75}
    )
    assert analysis.identity.chain == "solana"
    assert analysis.identity.protocol_slug == "orca"

def test_synthesis_supports_evm_fixture():
    pipeline = SynthesisPipeline()
    analysis = pipeline.combine(
        identity={"id": "opp_evm", "chain": EVM_FIXTURE["chain"], "kind": "lending", "protocol_slug": EVM_FIXTURE["protocol_slug"], "protocol_name": "Aave", "category": "lending", "assets": ["USDC"], "strategy_family": "carry"},
        market={"apy": 5.0, "tvl_usd": 1000000, "liquidity_usd": 100000, "market_regime": "balanced"},
        deterministic={"final_score": 75, "safety_score": 75, "apr_quality_score": 75, "exit_quality_score": 75, "resilience_score": 75, "confidence_score": 75, "gross_apr": 5.0, "haircut_apr": 4.5, "net_expected_apr": 4.0, "weighted_risk_burden": 10, "risk_to_apr_ratio": 2.0, "strategy_fit": "balanced", "headline": "Test", "hard_caps": [], "fragility_flags": [], "kill_switches": [], "confidence_reasoning": []},
        ai={"judgment_score": 75}
    )
    assert analysis.identity.chain == "base"
    assert analysis.identity.protocol_slug == "aave-v3"

