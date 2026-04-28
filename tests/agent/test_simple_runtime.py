from src.agent.simple_runtime import detect_intent


def test_detect_intent_parses_allocate_chain_and_asset_hint():
    intent = detect_intent(
        "I have $1,000 USDT. Allocate it across the best staking and yield opportunities on solana, risk-weighted using Sentinel scores."
    )

    assert intent == (
        "allocate_plan",
        {
            "usd_amount": 1000.0,
            "risk_budget": "balanced",
            "chains": ["solana"],
            "asset_hint": "USDT",
        },
    )


def test_detect_intent_routes_sentinel_explanation_away_from_allocate_plan():
    intent = detect_intent(
        "How does the Ilyon Sentinel scoring actually work? Explain every criterion."
    )

    assert intent == ("explain_sentinel_methodology", {})
