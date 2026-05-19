"""Pin tests for FIX 2 — cross-chain composed_plan FORCE.

Pass C 58517bf hand-read found E01-E14 + H04/H06/H09 all leaked pool_link
link_only cards for cross-chain SUPPLY / STAKE / LP_MINT intents because
the dispatcher only entered the explicit composed-plan branch when the
caller passed `extra.source_chain`. The fix-wave-3 patch adds a refuse-
to-fall-through gate immediately BEFORE the pool_link emission: if the
extras carry any cross-chain indicator AND the post-action is a yield
verb, the build path emits a structured CROSS_CHAIN_SOURCE_AMBIGUOUS
or COMPOSED_PLAN_INCOMPLETE_TX blocker (depending on whether the source
is recoverable).
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from src.agent.tools.build_yield_execution_plan import build_yield_execution_plan


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _ctx() -> SimpleNamespace:
    return SimpleNamespace(
        wallet="0x1111111111111111111111111111111111111111",
        evm_wallet="0x1111111111111111111111111111111111111111",
    )


def _envelope_card_type(env: Any) -> str | None:
    if isinstance(env, dict):
        return env.get("card_type") or (env.get("data") or {}).get("card_type")
    d = env.__dict__
    return d.get("card_type") or (d.get("data") or {}).get("card_type")


def _envelope_blocker_codes(env: Any) -> list[str]:
    if isinstance(env, dict):
        d = env
    else:
        d = env.__dict__
    plan = d.get("card_payload") or (d.get("data") or {}).get("plan") or {}
    return [b.get("code") for b in (plan.get("blockers") or [])]


class TestCrossChainForceComposedPlan:
    """Hold: cross-chain post-action intent MUST NOT fall to pool_link."""

    def test_bridge_via_indicator_refuses_pool_link(self):
        # H04/H06/H09 pin: `extra.bridge_via="debridge"` is the explicit
        # cross-chain indicator the runtime threads when intent-parse fires.
        # Even without source_chain set, the dispatcher must refuse
        # pool_link and emit a structured blocker.
        result = _run(build_yield_execution_plan(
            _ctx(),
            chain="ethereum",
            # Pick a protocol/verb combo whose default capability is link_only.
            protocol="uniswap-v3",
            action="lp_mint",
            asset_in="USDC",
            amount_in=100,
            extra={
                "amount_confirmed": True,
                "bridge_via": "debridge",
            },
        ))
        card_type = _envelope_card_type(result)
        assert card_type != "pool_link", (
            f"Cross-chain bridge_via indicator MUST NOT fall to pool_link "
            f"link_only. Got: {card_type}"
        )
        # The structured blocker IS one of CROSS_CHAIN_SOURCE_AMBIGUOUS or
        # COMPOSED_PLAN_INCOMPLETE_TX depending on whether source resolved.
        codes = _envelope_blocker_codes(result)
        assert any(
            c in {"CROSS_CHAIN_SOURCE_AMBIGUOUS", "COMPOSED_PLAN_INCOMPLETE_TX"}
            for c in codes
        ), f"Expected cross-chain refusal blocker. Got: {codes}"

    def test_explicit_source_chain_in_extra_refuses_pool_link(self):
        # When source_chain IS explicit, the upper composed-plan branch should
        # fire (entering the deBridge snapshot path). If for any reason it
        # doesn't (degenerate src==chain, or the snapshot is mocked away),
        # the fall-through guard must refuse pool_link.
        result = _run(build_yield_execution_plan(
            _ctx(),
            chain="ethereum",
            protocol="uniswap-v3",
            action="supply",
            asset_in="USDC",
            amount_in=100,
            extra={
                "amount_confirmed": True,
                "source_chain": "ethereum",  # degenerate same-chain; not entering composed
                "cross_chain": True,
            },
        ))
        card_type = _envelope_card_type(result)
        assert card_type != "pool_link"

    def test_cross_chain_message_only_emits_source_blocker(self):
        # E04-E14: a free-form `cross_chain_message` with destination only
        # must surface CROSS_CHAIN_SOURCE_AMBIGUOUS, never pool_link.
        result = _run(build_yield_execution_plan(
            _ctx(),
            chain="ethereum",
            protocol="uniswap-v3",
            action="lp_mint",
            asset_in="USDC",
            amount_in=100,
            extra={
                "amount_confirmed": True,
                "cross_chain_message": (
                    "bridge my USDC to mainnet and provide liquidity"
                ),
            },
        ))
        codes = _envelope_blocker_codes(result)
        assert "CROSS_CHAIN_SOURCE_AMBIGUOUS" in codes

    def test_no_cross_chain_indicator_unaffected(self):
        # Plain single-chain LP intent must NOT trigger the cross-chain refusal.
        result = _run(build_yield_execution_plan(
            _ctx(),
            chain="ethereum",
            protocol="uniswap-v3",
            action="lp_mint",
            asset_in="USDC",
            amount_in=100,
            extra={"amount_confirmed": True},
        ))
        codes = _envelope_blocker_codes(result)
        # Single-chain LP intent should fall through to pool_deposit_v3 or
        # pool_link, NOT emit a cross-chain refusal blocker.
        assert "CROSS_CHAIN_SOURCE_AMBIGUOUS" not in codes
        assert "COMPOSED_PLAN_INCOMPLETE_TX" not in codes


class TestCrossChainForceCoversYieldVerbs:
    """Hold: every (supply, stake, deposit_lp, lp_mint, add_liquidity, provide_
    liquidity, lend) verb on a cross-chain intent must refuse pool_link."""

    @pytest.mark.parametrize("verb", [
        "supply", "stake", "deposit_lp", "lp_mint",
        "add_liquidity", "provide_liquidity", "lend",
    ])
    def test_verb_refuses_pool_link(self, verb: str):
        result = _run(build_yield_execution_plan(
            _ctx(),
            chain="ethereum",
            protocol="uniswap-v3",
            action=verb,
            asset_in="USDC",
            amount_in=100,
            extra={
                "amount_confirmed": True,
                "cross_chain": True,
            },
        ))
        card_type = _envelope_card_type(result)
        assert card_type != "pool_link", (
            f"Cross-chain {verb} MUST NOT fall to pool_link. Got: {card_type}"
        )
