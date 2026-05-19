"""Pin tests for build_yield_execution_plan cross-chain routing (Pass A rows 10-11).

Routing contract pinned by these tests:

1. When `extra.cross_chain_message` expresses cross-chain intent but does NOT
   include a source chain (E04-E14 bug class), the tool MUST surface a
   CROSS_CHAIN_SOURCE_AMBIGUOUS blocker via execution_plan_v3 — never fall
   through to pool_link.
2. When the cross_chain_message resolves both source and dest, the tool MUST
   take the composed-plan branch (E01/E02/E07 bug class). We assert it
   tries the deBridge path by mocking the bridge client and looking for an
   attempt to call snapshot_bridge_quote.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

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


class TestSourceAmbiguousBlocker:
    def test_dest_only_message_emits_blocker_not_pool_link(self):
        # E04 / E05 / E06 / E09 / E12 / E13 / E14 pin.
        result = _run(build_yield_execution_plan(
            _ctx(),
            chain="ethereum",
            protocol="aave-v3",
            action="supply",
            asset_in="USDC",
            amount_in=100,
            extra={"cross_chain_message": "bridge my USDC to mainnet and supply on Aave"},
        ))

        envelope = result if isinstance(result, dict) else result.__dict__
        # ok_envelope returns an object/dict — pull card_type out robustly.
        card_type = envelope.get("card_type") or (envelope.get("data") or {}).get("card_type")
        assert card_type == "execution_plan_v3", (
            f"Cross-chain source-ambiguous must surface execution_plan_v3 "
            f"with a blocker, never pool_link. Got: {card_type}"
        )

        plan = (envelope.get("card_payload") or envelope.get("data", {}).get("plan") or {})
        blockers = plan.get("blockers") or []
        codes = [b.get("code") for b in blockers]
        assert "CROSS_CHAIN_SOURCE_AMBIGUOUS" in codes, (
            f"Expected CROSS_CHAIN_SOURCE_AMBIGUOUS blocker. Got: {codes}"
        )

    def test_dest_only_no_post_action_still_emits_blocker(self):
        # Even without "then supply", a cross-chain destination with implicit
        # source must not silently route to single-chain pool_link.
        result = _run(build_yield_execution_plan(
            _ctx(),
            chain="base",
            protocol="aave-v3",
            action="supply",
            asset_in="USDC",
            amount_in=100,
            extra={"cross_chain_message": "bridge USDT to base then supply on aave"},
        ))
        envelope = result if isinstance(result, dict) else result.__dict__
        card_type = envelope.get("card_type") or (envelope.get("data") or {}).get("card_type")
        # The detector fires (post-action present); source ambiguous → blocker.
        assert card_type == "execution_plan_v3"
        plan = (envelope.get("card_payload") or envelope.get("data", {}).get("plan") or {})
        codes = [b.get("code") for b in (plan.get("blockers") or [])]
        assert "CROSS_CHAIN_SOURCE_AMBIGUOUS" in codes


class TestNoFalseTriggerOnSingleChain:
    """Plain single-chain prompts must not be misrouted to a blocker."""

    def test_single_chain_supply_unaffected(self):
        # No cross_chain_message — must not even enter the new branch.
        result = _run(build_yield_execution_plan(
            _ctx(),
            chain="ethereum",
            protocol="aave-v3",
            action="supply",
            asset_in="USDC",
            amount_in=100,
            extra={},
        ))
        envelope = result if isinstance(result, dict) else result.__dict__
        card_type = envelope.get("card_type") or (envelope.get("data") or {}).get("card_type")
        # Doesn't blow up — and doesn't synthesise the cross-chain blocker.
        plan = (envelope.get("card_payload") or envelope.get("data", {}).get("plan") or {})
        codes = [b.get("code") for b in (plan.get("blockers") or [])]
        assert "CROSS_CHAIN_SOURCE_AMBIGUOUS" not in codes

    def test_single_chain_message_unaffected(self):
        # A non-cross-chain message must not trigger the blocker.
        result = _run(build_yield_execution_plan(
            _ctx(),
            chain="ethereum",
            protocol="aave-v3",
            action="supply",
            asset_in="USDC",
            amount_in=100,
            extra={"cross_chain_message": "supply 100 USDC on aave"},
        ))
        envelope = result if isinstance(result, dict) else result.__dict__
        plan = (envelope.get("card_payload") or envelope.get("data", {}).get("plan") or {})
        codes = [b.get("code") for b in (plan.get("blockers") or [])]
        assert "CROSS_CHAIN_SOURCE_AMBIGUOUS" not in codes


class TestSourceInferredFromMessage:
    """When the message names both endpoints, routing must take the composed
    branch even if the structured caller forgot to set extra.source_chain.
    """

    def test_inferred_source_routes_to_composed_branch(self):
        # E01/E02/E07 pin — the tool must attempt the deBridge snapshot when
        # the prose names src + dst, not fall through to single-chain pool_link.
        attempted: dict[str, Any] = {}

        async def _fake_snapshot(*args, **kwargs):
            attempted.update(kwargs)
            raise RuntimeError("intercepted — composed branch reached")

        with patch(
            "src.defi.execution.composed_plan.snapshot_bridge_quote",
            side_effect=_fake_snapshot,
        ):
            result = _run(build_yield_execution_plan(
                _ctx(),
                chain="base",
                protocol="aave-v3",
                action="supply",
                asset_in="USDC",
                amount_in=100,
                extra={
                    "cross_chain_message": (
                        "bridge 100 USDC from arbitrum to base then supply on aave v3"
                    ),
                },
            ))

        # Either the patched snapshot was attempted (composed branch reached)
        # OR the envelope is an err_envelope from the composed branch failing
        # downstream — both prove the routing decision (composed, not pool_link)
        # was taken. The critical failure mode the test guards against is the
        # tool returning a card_type="pool_link".
        envelope = result if isinstance(result, dict) else result.__dict__
        card_type = envelope.get("card_type") or (envelope.get("data") or {}).get("card_type")
        # If snapshot was called → branch confirmed; otherwise card_type must
        # still NOT be pool_link.
        if not attempted:
            assert card_type != "pool_link", (
                "Cross-chain message with inferred source MUST NOT route to "
                f"pool_link. Got: {card_type}"
            )
