"""Tests for the Phase 4 lifecycle intent detector."""
from __future__ import annotations

import pytest


@pytest.fixture
def detector():
    """The public entry point that runs the full dispatch chain.

    `_detect_lifecycle_withdraw` is a nested function so we exercise it
    through detect_intent.
    """
    from src.agent.simple_runtime import detect_intent
    return detect_intent


def _expect_withdraw(detector, message, *, protocol, asset, amount, chain):
    r = detector(message)
    assert r is not None, f"detector returned None for {message!r}"
    tool, args = r
    assert tool == "build_yield_execution_plan"
    assert args.get("action") == "withdraw"
    assert args.get("protocol") == protocol
    assert args.get("asset_in") == asset
    assert args.get("amount_in") == amount
    assert args.get("chain") == chain
    assert (args.get("extra") or {}).get("action") == "withdraw"


def test_aave_withdraw_usd_amount(detector):
    _expect_withdraw(
        detector, "Withdraw 50 USDC from Aave V3 on Base",
        protocol="aave-v3", asset="USDC", amount=50.0, chain="base",
    )


def test_redeem_yearn_vault(detector):
    _expect_withdraw(
        detector, "Redeem 0.5 yvUSDC from Yearn on Ethereum",
        protocol="yearn", asset="YVUSDC", amount=0.5, chain="ethereum",
    )


def test_withdraw_compound_v3_with_tail_asset(detector):
    # 'Withdraw 100 USDC from Compound V3 on Ethereum' → asset USDC, chain ethereum.
    _expect_withdraw(
        detector, "Withdraw 100 USDC from Compound V3 on Ethereum",
        protocol="compound-v3", asset="USDC", amount=100.0, chain="ethereum",
    )


def test_claim_rewards_branch(detector):
    r = detector("Claim COMP rewards from Compound V3 USDC on Ethereum")
    assert r is not None
    tool, args = r
    assert tool == "build_yield_execution_plan"
    assert args.get("action") == "claim"
    assert args.get("protocol") == "compound-v3"
    assert args.get("asset_in") == "USDC"
    assert (args.get("extra") or {}).get("reward_token") == "COMP"


def test_default_chain_when_omitted(detector):
    r = detector("Withdraw 25 USDC from Aave V3")
    assert r is not None
    _, args = r
    assert args.get("chain") == "ethereum"


def test_repay_verb_maps_to_repay_action(detector):
    r = detector("Repay 25 USDC to Aave V3 on Base")
    assert r is not None
    _, args = r
    assert args.get("action") == "repay"
    assert args.get("protocol") == "aave-v3"
    assert args.get("asset_in") == "USDC"
    assert args.get("amount_in") == 25.0
    assert args.get("chain") == "base"


def test_borrow_verb_maps_to_borrow_action(detector):
    r = detector("Borrow 100 USDC from Aave V3 on Ethereum")
    assert r is not None
    _, args = r
    assert args.get("action") == "borrow"
    assert args.get("protocol") == "aave-v3"
    assert args.get("amount_in") == 100.0
    assert args.get("chain") == "ethereum"


def test_v4_d04_bare_remove_no_amount():
    """v4-D04: 'Remove from PancakeSwap V2 BNB-USDT' — bare remove with
    no amount, paired tail. Treat as withdraw-all (amount=0 sentinel)."""
    from src.agent.simple_runtime import detect_intent

    out = detect_intent("Remove from PancakeSwap V2 BNB-USDT")
    assert out is not None
    tool, args = out
    assert tool == "build_yield_execution_plan"
    assert args["protocol"] == "pancakeswap-v2"
    assert args["action"] == "withdraw"
    assert args["amount_in"] == 0
    assert args["extra"]["pool_symbol"] == "BNB-USDT"
    assert args["extra"]["token_a"] == "BNB"
    assert args["extra"]["token_b"] == "USDT"


def test_v4_d05_bare_exit_balancer():
    """v4-D05: 'Exit Balancer wsteth-weth' — bare exit, no 'with N BPT'."""
    from src.agent.simple_runtime import detect_intent

    out = detect_intent("Exit Balancer wsteth-weth")
    assert out is not None
    tool, args = out
    assert tool == "build_yield_execution_plan"
    assert args["protocol"] == "balancer"
    assert args["action"] == "exit_pool"
    assert args["amount_in"] == 0
    assert args["extra"]["pool_key"] == "wsteth-weth"


def test_v4_d06_curve_3pool_withdraw():
    """v4-D06: 'Withdraw 1000 DAI from Curve 3pool' — pool tail starts
    with digit (Curve naming convention)."""
    from src.agent.simple_runtime import detect_intent

    out = detect_intent("Withdraw 1000 DAI from Curve 3pool")
    assert out is not None
    tool, args = out
    assert tool == "build_yield_execution_plan"
    assert args["protocol"] == "curve"
    assert args["action"] == "withdraw"
    assert args["asset_in"] == "DAI"
    assert args["amount_in"] == 1000.0
