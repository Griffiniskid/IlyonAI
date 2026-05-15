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
