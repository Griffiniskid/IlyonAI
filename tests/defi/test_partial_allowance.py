"""Spec §7 S8 — partial allowance top-up ladder in Aave V3 supply path.

Verifies that the supply adapter:
  - Skips approve entirely when existing allowance >= requested amount.
  - Emits a delta approve (Y - X) when 0 < existing < requested.
  - Falls back to a full approve when allowance read errors or returns 0.

The reader is injected via `extra.allowance_reader` (callable) — this lets
tests drive deterministic allowance values without standing up an EVM mock,
and mirrors the prod path where the runtime pre-fetches via `EVMChainClient`.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from src.defi.execution.adapters.aave_v3 import (
    AaveV3SupplyAdapter,
    _AAVE_POOL_ADDRESSES,
)
from src.defi.execution.adapters.base import YieldBuildRequest


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _supply_req(*, asset_in="USDC", amount=Decimal("100"), extra=None):
    return YieldBuildRequest(
        chain="ethereum",
        protocol="aave-v3",
        asset_in=asset_in,
        amount_in=amount,
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra=extra or {},
    )


class TestPartialAllowance:
    def test_full_approve_when_allowance_zero(self):
        """Baseline: no existing allowance → emit full approve (current behaviour)."""
        a = AaveV3SupplyAdapter()
        reader_calls: list[tuple] = []

        def reader(chain, token, owner, spender):
            reader_calls.append((chain, token, owner, spender))
            return 0

        req = _supply_req(extra={"allowance_reader": reader})
        steps = _run(a.build(req))
        assert len(steps) == 2
        assert steps[0].action == "approve"
        assert steps[1].action == "supply"
        # USDC has 6 decimals → 100 USDC = 100_000_000 units.
        # Approve calldata: 0x095ea7b3 + spender(64hex) + amount(64hex).
        expected_units = 100 * 10**6
        assert steps[0].transaction.data.endswith(format(expected_units, "064x"))
        assert len(reader_calls) == 1

    def test_skip_approve_when_existing_allowance_sufficient(self):
        """Existing allowance >= requested → no approve step at all."""
        a = AaveV3SupplyAdapter()

        def reader(chain, token, owner, spender):
            return 200 * 10**6  # 200 USDC allowance, need 100.

        req = _supply_req(extra={"allowance_reader": reader})
        steps = _run(a.build(req))
        assert len(steps) == 1, f"approve must be skipped; got {[s.action for s in steps]}"
        assert steps[0].action == "supply"
        # Warning about existing allowance must appear on the supply step.
        joined = " ".join(steps[0].risk_warnings)
        assert "Existing allowance sufficient" in joined

    def test_delta_approve_when_partial(self):
        """0 < allowance < requested → approve emits ONLY the delta, not full."""
        a = AaveV3SupplyAdapter()
        half_amount = 50 * 10**6  # 50 USDC already approved.

        def reader(chain, token, owner, spender):
            return half_amount

        req = _supply_req(extra={"allowance_reader": reader})
        steps = _run(a.build(req))
        assert len(steps) == 2
        assert steps[0].action == "approve"
        assert steps[1].action == "supply"
        # Delta = 100 - 50 = 50 USDC = 50_000_000 units.
        expected_delta = 50 * 10**6
        approve_data = steps[0].transaction.data
        assert approve_data.endswith(format(expected_delta, "064x")), (
            f"approve must use delta {expected_delta}, got tail "
            f"{approve_data[-64:]}"
        )
        # Topping-up warning must appear on the approve step.
        joined = " ".join(steps[0].risk_warnings)
        assert "Topping up" in joined or "delta" in joined.lower()

    def test_fail_soft_when_reader_raises(self):
        """Reader exception → fall back to full approve (preserves current behaviour)."""
        a = AaveV3SupplyAdapter()

        def reader(chain, token, owner, spender):
            raise RuntimeError("RPC down")

        req = _supply_req(extra={"allowance_reader": reader})
        steps = _run(a.build(req))
        # Must still emit both steps; full approve preserves prior behaviour.
        assert len(steps) == 2
        assert steps[0].action == "approve"
        expected_units = 100 * 10**6
        assert steps[0].transaction.data.endswith(format(expected_units, "064x"))

    def test_fail_soft_when_no_reader(self):
        """No reader supplied → full approve (current default behaviour)."""
        a = AaveV3SupplyAdapter()
        req = _supply_req()
        steps = _run(a.build(req))
        assert len(steps) == 2
        assert steps[0].action == "approve"
        expected_units = 100 * 10**6
        assert steps[0].transaction.data.endswith(format(expected_units, "064x"))

    def test_pre_fetched_current_allowance_extra(self):
        """`extra.current_allowance` short-circuits the reader (pre-fetched path)."""
        a = AaveV3SupplyAdapter()
        # Pre-fetch indicates 100 USDC already approved == exact requested amount.
        req = _supply_req(extra={"current_allowance": 100 * 10**6})
        steps = _run(a.build(req))
        assert len(steps) == 1
        assert steps[0].action == "supply"
