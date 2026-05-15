"""Tests for spec §6c composed-plan primitives."""
from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from src.defi.execution.composed_plan import (
    Bridge,
    FillResolution,
    Snapshot,
    block_step_for_async_fill,
    promote_step_to_ready,
    rebuild_step_with_actual_delta,
    snapshot_bridge_quote,
    watch_for_fill,
)
from src.defi.execution.models import ExecutionStepV3, UnsignedStepTransaction


class _FakeBridge:
    """Minimal Bridge implementation for tests — no network."""

    name = "fake-dln"

    def __init__(self, expected_dst: int = 1_000_000, fill_state: str = "filled", actual_dst: int | None = None):
        self.expected_dst = expected_dst
        self.fill_state = fill_state
        self.actual_dst = actual_dst if actual_dst is not None else expected_dst
        self.poll_count = 0

    async def quote(self, **kwargs):
        return {
            "expected_dst_amount": self.expected_dst,
            "slippage_bps_band": {"min": 5, "max": 20},
            "quote_id": "q-123",
        }

    async def status(self, order_id: str):
        self.poll_count += 1
        if self.poll_count < 3:
            return {"state": "created"}
        return {
            "state": self.fill_state,
            "actual_dst_amount": self.actual_dst,
            "realized_slippage_bps": 12,
        }


def _new_step(**kwargs) -> ExecutionStepV3:
    return ExecutionStepV3(
        step_id="step_test",
        index=2,
        action=kwargs.get("action", "supply"),
        title="Deposit on dst",
        description="",
        chain="solana",
        wallet="Phantom",
        protocol="raydium-clmm",
        asset_in="USDC",
        amount_in="100",
        status=kwargs.get("status", "pending"),
        transaction=UnsignedStepTransaction(chain_kind="solana"),
    )


@pytest.mark.asyncio
async def test_snapshot_captures_expected_amount():
    bridge = _FakeBridge(expected_dst=1_996_450_000)
    snap = await snapshot_bridge_quote(
        bridge,
        src_chain_id=1,
        dst_chain_id=101,
        token_in="USDT",
        token_out="USDC",
        amount=2_000_000_000,
        recipient="5MgZ...",
    )
    assert snap.expected_dst_amount == 1_996_450_000
    assert snap.bridge_name == "fake-dln"
    assert snap.quote_id == "q-123"
    assert snap.captured_at > 0


@pytest.mark.asyncio
async def test_snapshot_rejects_zero_quote():
    bridge = _FakeBridge(expected_dst=0)
    with pytest.raises(ValueError, match="zero/missing"):
        await snapshot_bridge_quote(
            bridge,
            src_chain_id=1,
            dst_chain_id=101,
            token_in="USDT",
            token_out="USDC",
            amount=1_000,
            recipient="5MgZ...",
        )


def test_block_step_sets_pending_dst_fill():
    step = _new_step()
    block_step_for_async_fill(step)
    assert "PENDING_DST_FILL" in step.blocker_codes
    assert step.status == "blocked"


def test_block_step_is_idempotent():
    step = _new_step()
    block_step_for_async_fill(step)
    block_step_for_async_fill(step)
    assert step.blocker_codes.count("PENDING_DST_FILL") == 1


def test_block_step_accepts_custom_blocker_code():
    step = _new_step()
    block_step_for_async_fill(step, blocker_code="PENDING_EPOCH_ENTRY")
    assert "PENDING_EPOCH_ENTRY" in step.blocker_codes


@pytest.mark.asyncio
async def test_watch_for_fill_resolves_filled():
    bridge = _FakeBridge(expected_dst=1_000_000, fill_state="filled", actual_dst=999_000)
    fill = await watch_for_fill(bridge, "order-1", poll_interval_s=0.01, max_poll_s=5)
    assert fill.state == "filled"
    assert fill.actual_dst_amount == 999_000
    assert fill.realized_slippage_bps == 12


@pytest.mark.asyncio
async def test_watch_for_fill_timeouts():
    bridge = _FakeBridge()
    # Override status to always return "created" → poll loop should hit max_poll_s.
    async def _stuck(_):
        return {"state": "created"}
    bridge.status = _stuck  # type: ignore[method-assign]
    fill = await watch_for_fill(bridge, "order-stuck", poll_interval_s=0.01, max_poll_s=0.1)
    assert fill.state == "timeout"


@pytest.mark.asyncio
async def test_watch_for_fill_resolves_failed():
    bridge = _FakeBridge(fill_state="failed", actual_dst=0)
    fill = await watch_for_fill(bridge, "order-fail", poll_interval_s=0.01, max_poll_s=5)
    assert fill.state == "failed"


def test_rebuild_with_filled_clears_blocker_and_runs_rebuilder():
    step = _new_step(action="deposit_lp", status="blocked")
    block_step_for_async_fill(step)
    snap = Snapshot(
        bridge_name="dln",
        src_chain_id=1,
        dst_chain_id=101,
        token_in="USDT",
        token_out="USDC",
        src_amount=1_000_000,
        expected_dst_amount=996_000,
        slippage_bps_band_min=5,
        slippage_bps_band_max=20,
        captured_at=time.time(),
    )
    fill = FillResolution(
        order_id="o1", state="filled", actual_dst_amount=994_500,
        realized_slippage_bps=15, resolved_at=time.time(),
    )
    captured_amount: list[int] = []

    def _rebuilder(actual: int) -> ExecutionStepV3:
        captured_amount.append(actual)
        s = _new_step(action="deposit_lp", status="ready")
        s.amount_in = str(actual)
        return s

    out = rebuild_step_with_actual_delta(step, snapshot=snap, fill=fill, rebuilder=_rebuilder)
    assert captured_amount == [994_500]
    assert out.amount_in == "994500"
    assert "PENDING_DST_FILL" not in out.blocker_codes
    assert out.step_id == "step_test"  # identity preserved


def test_rebuild_with_failed_attaches_recovery_hook():
    step = _new_step(status="blocked")
    block_step_for_async_fill(step)
    snap = Snapshot(
        bridge_name="dln", src_chain_id=1, dst_chain_id=101,
        token_in="USDT", token_out="USDC",
        src_amount=1_000_000, expected_dst_amount=996_000,
        slippage_bps_band_min=5, slippage_bps_band_max=20,
        captured_at=time.time(),
    )
    fill = FillResolution(
        order_id="o2", state="failed", actual_dst_amount=None,
        realized_slippage_bps=None, resolved_at=time.time(),
    )
    out = rebuild_step_with_actual_delta(step, snapshot=snap, fill=fill)
    assert out.recovery_hook is not None
    assert out.recovery_hook["action"] == "ASK_USER"
    assert any("LI.FI" in b for b in out.recovery_hook["buttons"])


def test_promote_rejects_step_with_blockers():
    step = _new_step()
    block_step_for_async_fill(step)
    import pytest as _pytest
    with _pytest.raises(ValueError, match="active blocker_codes"):
        promote_step_to_ready(step)


def test_promote_rejects_step_without_fill_resolution():
    step = _new_step()
    import pytest as _pytest
    with _pytest.raises(ValueError, match="fill not resolved"):
        promote_step_to_ready(step)


def test_promote_flips_blocked_to_ready():
    step = _new_step(status="blocked")
    step.fill_resolved = {"state": "filled", "actual_dst_amount": "994500"}
    step.blocker_codes = []
    promote_step_to_ready(step)
    assert step.status == "ready"


def test_snapshot_to_dict_serialisable():
    snap = Snapshot(
        bridge_name="dln", src_chain_id=1, dst_chain_id=101,
        token_in="USDT", token_out="USDC",
        src_amount=2_000_000, expected_dst_amount=1_996_000,
        slippage_bps_band_min=5, slippage_bps_band_max=20,
        captured_at=1234567890.0,
    )
    d = snap.to_dict()
    assert d["bridge_name"] == "dln"
    assert d["src_amount"] == "2000000"
    assert d["slippage_bps_band"] == {"min": 5, "max": 20}


def test_fill_resolution_to_dict_serialisable():
    fill = FillResolution(order_id="o3", state="filled", actual_dst_amount=1000, realized_slippage_bps=8, resolved_at=12345.6)
    d = fill.to_dict()
    assert d["order_id"] == "o3"
    assert d["actual_dst_amount"] == "1000"
    assert d["realized_slippage_bps"] == 8
