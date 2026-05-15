"""ComposedPlanOrchestrator — async background watch_for_fill task pool."""
from __future__ import annotations

import asyncio
import time

import pytest

from src.defi.execution.composed_plan import Snapshot
from src.defi.execution.composed_plan_orchestrator import (
    ComposedPlanOrchestrator,
)
from src.defi.execution.models import (
    ExecutionStepV3,
    UnsignedStepTransaction,
    make_step,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _new_step() -> ExecutionStepV3:
    return make_step(
        index=1, action="supply",
        title="Cross-chain deposit",
        description="awaits bridge fill",
        chain="base", wallet="MetaMask", protocol="aave-v3",
        asset_in="USDC", amount_in="100",
        slippage_bps=50, gas_estimate_usd=2.0, duration_estimate_s=20,
        transaction=UnsignedStepTransaction(
            chain_kind="evm", chain_id=8453,
            to="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            data="0x", value="0x0",
            spender="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ),
        status="blocked",
        blocker_codes=["PENDING_DST_FILL"],
    )


def _snapshot() -> Snapshot:
    return Snapshot(
        bridge_name="debridge-dln", src_chain_id=1, dst_chain_id=8453,
        token_in="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        token_out="0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
        src_amount=100_000_000, expected_dst_amount=99_500_000,
        slippage_bps_band_min=0, slippage_bps_band_max=50,
        quote_id="quote-123", captured_at=time.time(),
    )


class _StubBridge:
    name = "stub-bridge"

    def __init__(self, sequence: list[dict]):
        self._seq = list(sequence)

    async def quote(self, **kwargs):
        return {}

    async def status(self, order_id: str) -> dict:
        if self._seq:
            return self._seq.pop(0)
        return {"state": "created"}


def test_watch_promotes_step_on_filled():
    """When status returns filled with actual_dst_amount, step flips ready."""
    bridge = _StubBridge([
        {"state": "created"},
        {"state": "filled", "actual_dst_amount": 99_700_000},
    ])
    updates: list[dict] = []

    async def on_update(plan_id, payload):
        updates.append({"plan_id": plan_id, **payload})

    step = _new_step()
    snap = _snapshot()
    orch = ComposedPlanOrchestrator(
        on_plan_update=on_update, poll_interval_s=0.01, max_poll_s=5.0,
    )

    async def _go():
        task = await orch.watch(
            plan_id="plan-abc", bridge=bridge,
            order_id="order-1", deposit_step=step, snapshot=snap,
        )
        await task

    _run(_go())
    assert step.status == "ready"
    # PENDING_DST_FILL blocker removed by promote_step_to_ready
    assert "PENDING_DST_FILL" not in step.blocker_codes
    # At least one bridge_resolution event emitted
    kinds = [u.get("kind") for u in updates]
    assert "bridge_resolution" in kinds


def test_watch_keeps_blocker_on_failed():
    bridge = _StubBridge([{"state": "failed", "actual_dst_amount": None}])
    step = _new_step()
    orch = ComposedPlanOrchestrator(poll_interval_s=0.01, max_poll_s=5.0)

    async def _go():
        await (await orch.watch(
            plan_id="plan-fail", bridge=bridge, order_id="o-fail",
            deposit_step=step, snapshot=_snapshot(),
        ))

    _run(_go())
    # Step is still blocked — failed bridge does not clear blockers.
    assert step.status == "blocked"
    assert "PENDING_DST_FILL" in step.blocker_codes


def test_watch_emits_progress_updates():
    bridge = _StubBridge([
        {"state": "created"},
        {"state": "created"},
        {"state": "filled", "actual_dst_amount": 50},
    ])
    progress: list[dict] = []

    async def on_update(plan_id, payload):
        progress.append(payload)

    orch = ComposedPlanOrchestrator(
        on_plan_update=on_update, poll_interval_s=0.01, max_poll_s=5.0,
    )

    async def _go():
        await (await orch.watch(
            plan_id="plan-p", bridge=bridge, order_id="o-p",
            deposit_step=_new_step(), snapshot=_snapshot(),
        ))

    _run(_go())
    kinds = [p["kind"] for p in progress]
    # progress events fire on each poll; resolution event fires last
    assert kinds.count("bridge_progress") >= 1
    assert kinds[-1] == "bridge_resolution"


def test_cancel_removes_watch():
    bridge = _StubBridge([{"state": "created"}] * 100)
    orch = ComposedPlanOrchestrator(poll_interval_s=0.05, max_poll_s=30.0)

    async def _go():
        await orch.watch(
            plan_id="plan-x", bridge=bridge, order_id="o-x",
            deposit_step=_new_step(), snapshot=_snapshot(),
        )
        await asyncio.sleep(0.01)
        assert orch.active_count == 1
        cancelled = await orch.cancel("plan-x")
        assert cancelled is True
        await asyncio.sleep(0.05)
        assert orch.active_count == 0

    _run(_go())


def test_cancel_unknown_returns_false():
    orch = ComposedPlanOrchestrator()

    async def _go():
        return await orch.cancel("not-a-plan")

    assert _run(_go()) is False


def test_watch_replaces_existing_watch_for_same_plan():
    """Second watch() for the same plan_id cancels the prior task."""
    bridge1 = _StubBridge([{"state": "created"}] * 100)
    bridge2 = _StubBridge([{"state": "filled", "actual_dst_amount": 10}])
    orch = ComposedPlanOrchestrator(poll_interval_s=0.01, max_poll_s=5.0)

    async def _go():
        first = await orch.watch(
            plan_id="dup", bridge=bridge1, order_id="o1",
            deposit_step=_new_step(), snapshot=_snapshot(),
        )
        await asyncio.sleep(0.01)
        # Replace with a new watch that resolves instantly.
        second = await orch.watch(
            plan_id="dup", bridge=bridge2, order_id="o2",
            deposit_step=_new_step(), snapshot=_snapshot(),
        )
        await second
        # First task was cancelled.
        assert first.cancelled() or first.done()

    _run(_go())


def test_shutdown_cancels_all_inflight():
    bridge = _StubBridge([{"state": "created"}] * 100)
    orch = ComposedPlanOrchestrator(poll_interval_s=0.05, max_poll_s=30.0)

    async def _go():
        await orch.watch(plan_id="a", bridge=bridge, order_id="oa",
                         deposit_step=_new_step(), snapshot=_snapshot())
        await orch.watch(plan_id="b", bridge=bridge, order_id="ob",
                         deposit_step=_new_step(), snapshot=_snapshot())
        await asyncio.sleep(0.01)
        assert orch.active_count == 2
        await orch.shutdown()
        assert orch.active_count == 0

    _run(_go())


def test_orchestrator_swallows_bridge_exceptions():
    """A bridge.status that raises must not crash the orchestrator."""

    class _CrashBridge:
        name = "crash"

        async def quote(self, **kw):
            return {}

        async def status(self, oid):
            raise RuntimeError("rpc down")

    orch = ComposedPlanOrchestrator(poll_interval_s=0.01, max_poll_s=0.05)
    step = _new_step()

    async def _go():
        await (await orch.watch(
            plan_id="boom", bridge=_CrashBridge(),
            order_id="o-boom", deposit_step=step, snapshot=_snapshot(),
        ))

    _run(_go())
    # Step should remain blocked — no spurious flip on a crashing bridge.
    assert step.status == "blocked"


def test_no_callback_works_silently():
    """on_plan_update=None must not raise; orchestrator stays usable."""
    bridge = _StubBridge([{"state": "filled", "actual_dst_amount": 1}])
    orch = ComposedPlanOrchestrator(
        on_plan_update=None, poll_interval_s=0.01, max_poll_s=5.0,
    )
    step = _new_step()

    async def _go():
        await (await orch.watch(
            plan_id="silent", bridge=bridge, order_id="o-s",
            deposit_step=step, snapshot=_snapshot(),
        ))

    _run(_go())
    assert step.status == "ready"
