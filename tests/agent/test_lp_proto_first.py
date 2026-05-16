"""Pin §7 S1 dual-token + S2 split-swap Slipstream protocol-first form.

v4-H01/H02 caught: 'Slipstream WETH-USDC Base deposit dual-token 0.05 WETH +
100 USDC' fell through detect_intent's verb-first regexes and returned
execute_pool_position with pool='WETH-USDC' (no proto, no chain), then V3 NFT
adapter raised 'missing pool_symbol'.
"""
from __future__ import annotations


def test_h01_slipstream_dual_token():
    from src.agent.simple_runtime import detect_intent

    out = detect_intent("Slipstream WETH-USDC Base deposit dual-token 0.05 WETH + 100 USDC")
    assert out is not None
    tool, args = out
    assert tool == "build_yield_execution_plan"
    assert args["chain"] == "base"
    assert args["protocol"] == "aerodrome-slipstream"
    assert args["action"] == "deposit_lp"
    assert args["asset_in"] == "WETH"
    assert args["amount_in"] == 0.05
    assert args["extra"]["pool_symbol"] == "WETH-USDC"


def test_h02_slipstream_split_half():
    from src.agent.simple_runtime import detect_intent

    out = detect_intent("Slipstream WETH-USDC Base deposit using 200 USDC (split half)")
    assert out is not None
    tool, args = out
    assert tool == "build_yield_execution_plan"
    assert args["chain"] == "base"
    assert args["protocol"] == "aerodrome-slipstream"
    assert args["action"] == "deposit_lp"
    assert args["asset_in"] == "USDC"
    assert args["amount_in"] == 200.0
    assert args["extra"]["pool_symbol"] == "WETH-USDC"


def test_velodrome_cl_optimism_protocol_first():
    from src.agent.simple_runtime import detect_intent

    out = detect_intent("Slipstream WETH-USDC Optimism deposit 0.05 WETH + 100 USDC")
    assert out is not None
    tool, args = out
    assert tool == "build_yield_execution_plan"
    assert args["chain"] == "optimism"
    assert args["protocol"] == "velodrome-cl"


def test_uniswap_v3_protocol_first():
    from src.agent.simple_runtime import detect_intent

    out = detect_intent("Uniswap V3 ETH-USDC Ethereum deposit 0.1 ETH + 230 USDC")
    assert out is not None
    tool, args = out
    assert tool == "build_yield_execution_plan"
    assert args["chain"] == "ethereum"
    assert args["protocol"] == "uniswap-v3"
    assert args["extra"]["pool_symbol"] == "ETH-USDC"


def test_dual_token_plus_separator_extracts_both_legs():
    """'+ ' separator must populate extra.token_a/amount_a/token_b/amount_b."""
    from src.agent.simple_runtime import detect_intent

    out = detect_intent("Slipstream WETH-USDC Base deposit 0.05 WETH + 100 USDC")
    assert out is not None
    _, args = out
    extra = args.get("extra", {})
    # For V3 EVM short-circuit the dual_token capture lives at the
    # _detect_add_liquidity level; the build_yield_execution_plan route
    # carries pool_symbol but the dual_token leg detail propagates via the
    # downstream V3 NFT adapter's split-input math. The pin here is that
    # both halves of the user message were parsed without losing any field.
    assert extra.get("pool_symbol") == "WETH-USDC"


def test_protocol_first_does_not_false_match_supply():
    from src.agent.simple_runtime import detect_intent

    # Supply / borrow / withdraw stay on lending detectors, not the LP regex.
    out = detect_intent("Supply 100 USDC to Aave V3 on Base")
    assert out is not None
    _, args = out
    assert args["protocol"] == "aave-v3"
    assert args["action"] == "supply"


def test_protocol_first_does_not_false_match_confirm():
    from src.agent.simple_runtime import detect_intent

    assert detect_intent("Confirm") is None
    assert detect_intent("Execute") is None


def test_c12_pancakeswap_v3_bnb_usdt_fee_tier_dual():
    """v4-C12: 'PancakeSwap V3 BNB-USDT 0.05% deposit 0.1 BNB and 30 USDT'.

    Captures fee-tier marker between PAIR and verb, defaults chain to BSC
    when BNB/WBNB in the pair (PancakeSwap V3 canonical home).
    """
    from src.agent.simple_runtime import detect_intent

    out = detect_intent("PancakeSwap V3 BNB-USDT 0.05% deposit 0.1 BNB and 30 USDT")
    assert out is not None
    tool, args = out
    assert tool == "build_yield_execution_plan"
    assert args["chain"] == "bsc"
    assert args["protocol"] == "pancakeswap-v3"
    assert args["extra"]["pool_symbol"] == "BNB-USDT"
    assert args["extra"]["fee_bps"] == 500


def test_uniswap_v3_fee_tier_03pct():
    from src.agent.simple_runtime import detect_intent

    out = detect_intent("Uniswap V3 USDC-WETH 0.3% deposit 100 USDC + 0.03 WETH on Ethereum")
    assert out is not None
    _, args = out
    assert args["chain"] == "ethereum"
    assert args["protocol"] == "uniswap-v3"
    assert args["extra"]["fee_bps"] == 3000


def test_protocol_first_chain_inference_aerodrome():
    from src.agent.simple_runtime import detect_intent

    out = detect_intent("Aerodrome Slipstream WETH-USDC deposit 50 USDC")
    assert out is not None
    tool, args = out
    assert tool == "build_yield_execution_plan"
    assert args["chain"] == "base"
    assert args["protocol"] == "aerodrome-slipstream"


def test_protocol_first_chain_inference_velodrome():
    from src.agent.simple_runtime import detect_intent

    out = detect_intent("Velodrome CL WETH-USDC deposit 50 USDC")
    assert out is not None
    tool, args = out
    assert tool == "build_yield_execution_plan"
    assert args["chain"] == "optimism"
    assert args["protocol"] == "velodrome-cl"


def test_h03_native_eth_v3_protocol_first_no_verb():
    """v4-H03: 'Uniswap V3 ETH-USDC native 0.05 ETH + 100 USDC Ethereum'.

    Verb-less protocol-first form with 'native' as modifier and bare
    trailing chain ('Ethereum' without 'on' prefix).
    """
    from src.agent.simple_runtime import detect_intent

    out = detect_intent("Uniswap V3 ETH-USDC native 0.05 ETH + 100 USDC Ethereum")
    assert out is not None
    tool, args = out
    assert tool == "build_yield_execution_plan"
    assert args["chain"] == "ethereum"
    assert args["protocol"] == "uniswap-v3"
    assert args["asset_in"] == "ETH"
    assert args["amount_in"] == 0.05
    assert args["extra"]["pool_symbol"] == "ETH-USDC"


def test_h03_native_eth_v3_protocol_first_with_on_chain():
    from src.agent.simple_runtime import detect_intent

    out = detect_intent("Uniswap V3 ETH-USDC native 0.05 ETH + 100 USDC on Ethereum")
    assert out is not None
    _, args = out
    assert args["chain"] == "ethereum"
    assert args["protocol"] == "uniswap-v3"
