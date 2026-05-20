"""Pin test for wave-11 verb-inversion guard at build_yield_execution_plan.

Wave-10 D05 t2 reproduced D-P0-10b: prompt "Exit Balancer wsteth-weth with
0.5 BPT" reached build_yield_execution_plan with action="deposit_lp"
because the live LLM-based intent extractor bled t1's deposit context.
Generated a READY 3-step joinPool DEPOSIT plan — drain-equivalent.

Wave-11 adds a verb-aware guard at the tool's entry point: when
extra.user_message starts with an exit/withdraw/remove verb but the
caller asked for a deposit-side action, refuse with VERB_INVERTED.
"""
from __future__ import annotations

import asyncio


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _Ctx:
    wallet = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    evm_wallet = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    solana_wallet = None


def test_exit_balancer_with_deposit_lp_action_refused():
    """D-P0-10b wave-10 reproduction: prompt 'Exit Balancer wsteth-weth
    with 0.5 BPT' + action='deposit_lp' → must refuse."""
    from src.agent.tools.build_yield_execution_plan import (
        build_yield_execution_plan,
    )
    res = _run(build_yield_execution_plan(
        _Ctx(),
        chain="ethereum",
        protocol="balancer",
        action="deposit_lp",
        asset_in="USDC",
        amount_in=0.5,
        extra={"user_message": "Exit Balancer wsteth-weth with 0.5 BPT"},
    ))
    # res is a ToolEnvelope with card_payload containing a VERB_INVERTED blocker
    payload = res.card_payload or {}
    blockers = payload.get("blockers", [])
    assert any(b.get("code") == "VERB_INVERTED" for b in blockers), (
        f"Expected VERB_INVERTED blocker; got {blockers!r}"
    )


def test_withdraw_with_supply_action_refused():
    from src.agent.tools.build_yield_execution_plan import (
        build_yield_execution_plan,
    )
    res = _run(build_yield_execution_plan(
        _Ctx(),
        chain="base",
        protocol="aave-v3",
        action="supply",
        asset_in="USDC",
        amount_in=100,
        extra={"user_message": "Withdraw 100 USDC from Aave V3 Base"},
    ))
    payload = res.card_payload or {}
    blockers = payload.get("blockers", [])
    assert any(b.get("code") == "VERB_INVERTED" for b in blockers)


def test_remove_with_add_liquidity_action_refused():
    from src.agent.tools.build_yield_execution_plan import (
        build_yield_execution_plan,
    )
    res = _run(build_yield_execution_plan(
        _Ctx(),
        chain="ethereum",
        protocol="uniswap-v3",
        action="add_liquidity",
        asset_in="USDC",
        amount_in=100,
        extra={"user_message": "Remove liquidity from Uniswap V3 USDC/WETH"},
    ))
    payload = res.card_payload or {}
    blockers = payload.get("blockers", [])
    assert any(b.get("code") == "VERB_INVERTED" for b in blockers)


def test_deposit_with_supply_action_passes_guard():
    """Regression: matching verb (Deposit + supply) must NOT trigger the
    guard. May still fail downstream for other reasons but the guard
    must let it through."""
    from src.agent.tools.build_yield_execution_plan import (
        build_yield_execution_plan,
    )
    res = _run(build_yield_execution_plan(
        _Ctx(),
        chain="base",
        protocol="aave-v3",
        action="supply",
        asset_in="USDC",
        amount_in=100,
        extra={"user_message": "Supply 100 USDC to Aave V3 on Base"},
    ))
    # Whatever the result, must NOT be a VERB_INVERTED refusal.
    payload = res.card_payload or {}
    blockers = payload.get("blockers", [])
    assert not any(b.get("code") == "VERB_INVERTED" for b in blockers)


def test_no_user_message_passes_guard():
    """When no user_message is passed, the guard cannot detect intent
    and must allow through (let downstream handle)."""
    from src.agent.tools.build_yield_execution_plan import (
        build_yield_execution_plan,
    )
    res = _run(build_yield_execution_plan(
        _Ctx(),
        chain="base",
        protocol="aave-v3",
        action="supply",
        asset_in="USDC",
        amount_in=100,
        extra={},
    ))
    payload = res.card_payload or {}
    blockers = payload.get("blockers", [])
    assert not any(b.get("code") == "VERB_INVERTED" for b in blockers)
