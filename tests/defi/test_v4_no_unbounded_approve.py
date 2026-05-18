"""Pin test for §11 D.3 — Uniswap V4 must not issue unbounded approves.

Surfaced by codebase audit subagent: ``uniswap_v4.py:385`` emitted
``2**256 - 1`` approve to Permit2 with no revoke pair. Spec mandates
scoped approval equal to ``amount_max`` (or padded ceiling) OR paired
revoke step.

These tests pin the bound: every ``approve(spender, amount)`` calldata
in a V4 mint plan must have its 32-byte amount argument set to the
slippage-padded ``amount_max`` for that token leg — never ``MAX_UINT256``.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from src.defi.execution.adapters.uniswap_v4 import (
    _APPROVE_SEL,
    _PERMIT2,
    _PERMIT2_APPROVE_SEL,
    UniswapV4NativeAdapter,
)
from src.defi.execution.adapters.base import YieldBuildRequest

# Sentinel: 32 bytes of 0xff hex = MAX_UINT256.
_MAX_UINT_HEX = "f" * 64


def _build_plan(amount_in: Decimal = Decimal("1000"), usd: float = 1000.0):
    """Build a V4 USDC-USDT plan on ethereum (both legs ERC-20 → two approves)."""
    adapter = UniswapV4NativeAdapter()
    # Patch the on-chain slot0 read to avoid network in tests — supplies
    # current_tick=0 via the `extra.current_tick` short-circuit instead.
    req = YieldBuildRequest(
        chain="ethereum",
        protocol="uniswap-v4",
        asset_in="USDC",
        amount_in=amount_in,
        user_address="0x000000000000000000000000000000000000dEaD",
        extra={
            "pool_symbol": "USDC-USDT",
            "fee_bps": 500,
            "tick_spacing": 10,
            "hooks": "0x" + "00" * 20,
            "current_tick": 0,
            "usd_equivalent": usd,
            "range_lower_pct": -10.0,
            "range_upper_pct": 10.0,
        },
    )
    return asyncio.run(adapter.build(req))


def _approve_steps(steps):
    """Yield (step, calldata_hex, last_32_bytes_hex, amount_field) per approve leg."""
    out = []
    for s in steps:
        if s.action != "approve":
            continue
        data = s.transaction.data.lower().removeprefix("0x")
        selector = "0x" + data[:8]
        if selector == _APPROVE_SEL:
            # ERC20.approve(spender, amount): 4 + 32 + 32 bytes — amount is last 32.
            last32 = data[-64:]
            amount_field = int(last32, 16)
            out.append((s, data, last32, amount_field, "erc20"))
        elif selector == _PERMIT2_APPROVE_SEL:
            # Permit2.approve(token, spender, uint160 amount, uint48 expiration):
            # head is selector + 4 × 32 = 132 bytes. amount is the 3rd 32-byte
            # slot (offsets 8+64..8+128 in hex), expiration is the 4th.
            amount_slot = data[8 + 64 * 2 : 8 + 64 * 3]
            amount_field = int(amount_slot, 16)
            out.append((s, data, amount_slot, amount_field, "permit2"))
    return out


def test_approve_amount_scoped_to_amount_max():
    """Every approve emitted by the V4 plan binds its amount argument to the
    +5% padded ``amount_max`` of the leg — exactly what Permit2 needs to
    fund this single mint and nothing more.
    """
    steps = _build_plan()
    approves = _approve_steps(steps)
    assert approves, "Expected at least one approve step in the V4 plan."

    # The plan emits exactly one ERC20.approve + one Permit2.approve per
    # non-native leg. Both must lock to the same +5% padded ceiling.
    erc20 = [a for a in approves if a[4] == "erc20"]
    permit2 = [a for a in approves if a[4] == "permit2"]
    assert len(erc20) >= 1, "Expected ERC20.approve to Permit2 step."
    assert len(permit2) >= 1, "Expected Permit2.approve to PositionManager step."

    for step, _data, _last32, amt, kind in approves:
        # Bound: must be a small finite cap, NEVER max-uint256 and NEVER
        # near 2**160 (Permit2's uint160 ceiling).
        assert amt > 0, f"{kind} approve amount must be > 0, got {amt}"
        assert amt < 2**128, (
            f"{kind} approve amount {amt} is suspiciously large — "
            f"§11 D.3 forbids unbounded approvals."
        )

    # ERC20 and Permit2 approves on the same leg must agree on the cap
    # (both = amount_max × 105 / 100).
    erc20_amt = erc20[0][3]
    permit2_amt = permit2[0][3]
    assert erc20_amt == permit2_amt, (
        f"ERC20 approve cap ({erc20_amt}) must equal Permit2 approve cap "
        f"({permit2_amt}) — otherwise the two-step funnel leaks excess "
        f"allowance past the mint."
    )

    # And both must equal the +5% padded amount_max for the leg. The plan
    # uses usd_equivalent=1000 → half_usd=500, dec=6 → amount_max=500_000_000,
    # padded = 500_000_000 × 105 // 100 = 525_000_000.
    expected = 500_000_000 * 105 // 100
    assert erc20_amt == expected, (
        f"ERC20 approve amount {erc20_amt} should equal +5% padded "
        f"amount_max {expected}."
    )


def test_approve_never_emits_max_uint256():
    """No approve calldata in the V4 plan ends with 64 hex 'f's (MAX_UINT256).
    This is the exact violation §11 D.3 forbids.
    """
    steps = _build_plan()
    approves = _approve_steps(steps)
    assert approves, "Expected approve steps to assert against."

    for step, data, last32, amt, kind in approves:
        assert _MAX_UINT_HEX not in data, (
            f"{kind} approve calldata contains MAX_UINT256 sentinel "
            f"({_MAX_UINT_HEX[:8]}…) — §11 D.3 violation. "
            f"step={step.title!r} data={data}"
        )
        # Belt-and-braces: amount_in field on the step should also be a
        # bounded integer string, not 2**256-1.
        if step.amount_in is not None:
            assert step.amount_in != str(2**256 - 1), (
                f"step.amount_in still surfaces MAX_UINT256 — UI would "
                f"render an unbounded allowance prompt to the user."
            )


def test_approve_step_spender_is_permit2_then_position_manager():
    """Sanity: the two-step approval chain hits Permit2 first, then the
    V4 PositionManager — matching the §11 D.3 scoped-allowance model.
    """
    from src.defi.execution.adapters.uniswap_v4 import _V4_POSITION_MANAGER

    steps = _build_plan()
    approves = _approve_steps(steps)
    erc20 = [a for a in approves if a[4] == "erc20"]
    permit2 = [a for a in approves if a[4] == "permit2"]
    assert erc20 and permit2

    erc20_step = erc20[0][0]
    assert erc20_step.transaction.spender.lower() == _PERMIT2.lower()

    permit2_step = permit2[0][0]
    assert (
        permit2_step.transaction.spender.lower()
        == _V4_POSITION_MANAGER["ethereum"].lower()
    )
