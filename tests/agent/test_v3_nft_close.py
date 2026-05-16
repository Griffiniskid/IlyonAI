"""Pin V3 NFT close-by-tokenId detector (v4-D01)."""
from __future__ import annotations


def test_close_uniswap_v3_tokenid():
    from src.agent.simple_runtime import detect_intent

    out = detect_intent("Close my Uniswap V3 position tokenId 12345")
    assert out is not None
    tool, args = out
    assert tool == "build_yield_execution_plan"
    assert args["protocol"] == "uniswap-v3"
    assert args["action"] == "close_position"
    assert args["extra"]["action"] == "close_position"
    assert args["extra"]["token_id"] == 12345


def test_close_pancakeswap_v3_hash_form():
    from src.agent.simple_runtime import detect_intent

    out = detect_intent("Close my PancakeSwap V3 position #98765")
    assert out is not None
    _, args = out
    assert args["protocol"] == "pancakeswap-v3"
    assert args["extra"]["token_id"] == 98765


def test_close_aerodrome_with_chain():
    from src.agent.simple_runtime import detect_intent

    out = detect_intent("Close Aerodrome Slipstream position tokenId 5 on Base")
    assert out is not None
    _, args = out
    assert args["chain"] == "base"
    assert args["protocol"] == "aerodrome-slipstream"
    assert args["extra"]["token_id"] == 5


def test_close_velodrome_cl_default_chain():
    from src.agent.simple_runtime import detect_intent

    out = detect_intent("Close my Velodrome CL position tokenId 42")
    assert out is not None
    _, args = out
    assert args["protocol"] == "velodrome-cl"
    assert args["extra"]["token_id"] == 42


def test_close_does_not_match_supply_or_withdraw():
    from src.agent.simple_runtime import detect_intent

    # 'Close' is reserved for V3 NFT close — generic 'withdraw' / 'supply'
    # should not match the m_close branch.
    out = detect_intent("Withdraw 100 USDC from Aave V3 on Base")
    assert out is not None
    _, args = out
    assert args["action"] == "withdraw"
    assert "token_id" not in args.get("extra", {})
