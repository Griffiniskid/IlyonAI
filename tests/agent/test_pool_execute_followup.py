"""Lock the pool-execution memory-driven detector behavior."""
from __future__ import annotations

from src.agent.simple_runtime import (
    _detect_pool_execute_followup,
    _detect_sentinel_features,
)
from src.defi.strategy.opportunity_memory import (
    clear_all_for_test,
    remember_allocation,
    remember_opportunities,
)


def setup_function(_):
    clear_all_for_test()


def test_pool_execute_followup_resolves_protocol_symbol_pair():
    sid = "session-A"
    remember_opportunities(sid, [
        {
            "protocol": "raydium-amm",
            "symbol": "SPACEX-WSOL",
            "chain": "solana",
            "product_type": "pool",
            "pool_id": "p1",
        },
        {
            "protocol": "raydium-amm",
            "symbol": "WSOL-CHILLGUY",
            "chain": "solana",
            "product_type": "pool",
            "pool_id": "p2",
        },
    ])

    detected = _detect_pool_execute_followup(
        "execute this pool raydium-amm SPACEX-WSOL", sid
    )
    assert detected is not None
    tool, params = detected
    assert tool == "build_yield_execution_plan"
    assert params["chain"] == "solana"
    assert params["protocol"] == "raydium-amm"
    assert params["action"] == "deposit_lp"
    # Pair-extraction picks the SPACEX-WSOL row, not the second row.
    assert "SPACEX-WSOL" in params["research_thesis"]


def test_pool_execute_followup_resolves_index_hint():
    sid = "session-B"
    remember_opportunities(sid, [
        {"protocol": "lido", "symbol": "ETH", "chain": "ethereum", "product_type": "staking", "pool_id": "x1"},
        {"protocol": "spark", "symbol": "DAI", "chain": "ethereum", "product_type": "lending", "pool_id": "x2"},
    ])
    detected = _detect_pool_execute_followup("execute pool #2", sid)
    assert detected is not None
    _, params = detected
    assert params["protocol"] == "spark"
    assert params["chain"] == "ethereum"


def test_allocation_execute_through_wallet_resolves_to_multi_pool():
    sid = "session-C"
    rows = [
        {"protocol": "Aave V3", "asset": "USDC", "chain": "ethereum", "weight": 60, "usd": "$600"},
        {"protocol": "Lido", "asset": "ETH", "chain": "ethereum", "weight": 40, "usd": "$400"},
    ]
    remember_allocation(sid, rows, total_usd=1000.0, asset_hint="USDC")
    detected = _detect_pool_execute_followup(
        "execute the transactions through my wallet", sid
    )
    assert detected is not None
    tool, params = detected
    assert tool == "build_allocation_execution_plan"
    assert len(params["allocations"]) == 2
    assert params["default_asset"] == "USDC"
    assert params["default_amount_total"] == "1000"


def test_sentinel_analyze_token_address_routing():
    detected = _detect_sentinel_features(
        "analyze this token 9LQ3ruKXhXoMJk5334bunknq1kUErXJjdFkAJXrapump"
    )
    assert detected is not None
    tool, params = detected
    assert tool == "analyze_token_full_sentinel"
    assert params["address"].startswith("9LQ3ru")


def test_sentinel_whale_chain_window_routing():
    detected = _detect_sentinel_features(
        "show me whales on solana last 6 hours"
    )
    assert detected is not None
    tool, params = detected
    assert tool == "track_whales"
    assert params["chain"] == "solana"
    assert params["hours"] == 6


def test_sentinel_smart_money_hub_routing():
    detected = _detect_sentinel_features("smart money hub")
    assert detected is not None
    tool, _ = detected
    assert tool == "get_smart_money_hub"


def test_direct_yield_execute_raydium_solana():
    from src.agent.simple_runtime import detect_intent
    intent = detect_intent("sign deposit_lp on raydium-amm SPACEX-WSOL on solana with 0.5 SOL")
    assert intent is not None
    tool, params = intent
    assert tool == "build_yield_execution_plan"
    assert params["chain"] == "solana"
    assert params["protocol"] == "raydium-amm"
    assert params["asset_in"] == "SOL"
    assert params["amount_in"] == "0.5"


def test_direct_yield_execute_compound_v3_base():
    from src.agent.simple_runtime import detect_intent
    intent = detect_intent("deposit 50 USDC into compound v3 on base")
    assert intent is not None
    tool, params = intent
    assert tool == "build_yield_execution_plan"
    assert params["chain"] == "base"
    assert params["protocol"] == "compound-v3"
    assert params["amount_in"] == "50"


def test_direct_yield_execute_marinade_no_chain_hint():
    from src.agent.simple_runtime import detect_intent
    intent = detect_intent("execute marinade with 2 SOL")
    assert intent is not None
    _, params = intent
    assert params["chain"] == "solana"
    assert params["protocol"] == "marinade"
    assert params["action"] == "stake"


def test_sentinel_shield_with_address_routing():
    detected = _detect_sentinel_features(
        "shield check 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
    )
    assert detected is not None
    tool, params = detected
    assert tool == "get_shield_check"
    assert params["address"].startswith("0xd8dA")
