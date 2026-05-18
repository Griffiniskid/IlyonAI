"""Spec §6c runtime orchestrator — async background task pool for
pending composed plans.

The composed_plan module ships pure functions: snapshot, block, watch,
rebuild, promote. The orchestrator wires them into a long-running
asyncio task pool so a plan with a PENDING_DST_FILL blocker resolves
itself without a user re-prompt:

  user signs bridge leg → orchestrator polls bridge.status →
  on filled → rebuild_step_with_actual_delta → promote_step_to_ready →
  push plan update through the user's SSE channel.

Usage:
  orch = ComposedPlanOrchestrator(on_plan_update=push_sse)
  await orch.watch(plan_id, bridge, order_id, deposit_step, snapshot)
  ...
  await orch.shutdown()  # cancels every in-flight task
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from src.defi.execution.composed_plan import (
    Bridge,
    FillResolution,
    Snapshot,
    promote_step_to_ready,
    rebuild_step_with_actual_delta,
    watch_for_fill,
)
from src.defi.execution.models import ExecutionStepV3

logger = logging.getLogger(__name__)


PlanUpdateCallback = Callable[[str, dict], Awaitable[None]]
ProgressCallback = Callable[[dict], Awaitable[None]]


@dataclass
class _Watch:
    plan_id: str
    order_id: str
    step: ExecutionStepV3
    snapshot: Snapshot
    task: asyncio.Task


class ComposedPlanOrchestrator:
    """Singleton-style task pool for pending composed plans.

    Wire one instance at runtime startup; call `watch()` whenever a plan
    is built with a bridge leg in PENDING_DST_FILL state.
    """

    def __init__(
        self,
        *,
        on_plan_update: PlanUpdateCallback | None = None,
        poll_interval_s: float = 2.0,
        max_poll_s: float = 900.0,
    ) -> None:
        self._on_plan_update = on_plan_update
        self._poll_interval_s = poll_interval_s
        self._max_poll_s = max_poll_s
        self._watches: dict[str, _Watch] = {}
        self._lock = asyncio.Lock()

    @property
    def active_count(self) -> int:
        return sum(1 for w in self._watches.values() if not w.task.done())

    @property
    def active_plan_ids(self) -> list[str]:
        return [w.plan_id for w in self._watches.values() if not w.task.done()]

    async def watch(
        self,
        *,
        plan_id: str,
        bridge: Bridge,
        order_id: str,
        deposit_step: ExecutionStepV3,
        snapshot: Snapshot,
    ) -> asyncio.Task:
        """Start watching `order_id`. Returns the underlying asyncio.Task.

        If a watch already exists for `plan_id`, it is replaced (the old
        task is cancelled cleanly). One plan = one in-flight watch.
        """
        async with self._lock:
            if plan_id in self._watches:
                old = self._watches.pop(plan_id)
                old.task.cancel()
            task = asyncio.create_task(
                self._run_watch(plan_id, bridge, order_id, deposit_step, snapshot)
            )
            self._watches[plan_id] = _Watch(
                plan_id=plan_id,
                order_id=order_id,
                step=deposit_step,
                snapshot=snapshot,
                task=task,
            )
            return task

    async def cancel(self, plan_id: str) -> bool:
        async with self._lock:
            w = self._watches.pop(plan_id, None)
        if w is None:
            return False
        w.task.cancel()
        return True

    async def shutdown(self) -> None:
        async with self._lock:
            tasks = [w.task for w in self._watches.values() if not w.task.done()]
            for t in tasks:
                t.cancel()
            self._watches.clear()
        for t in tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass

    async def _run_watch(
        self,
        plan_id: str,
        bridge: Bridge,
        order_id: str,
        deposit_step: ExecutionStepV3,
        snapshot: Snapshot,
    ) -> FillResolution:
        async def _progress(payload: dict) -> None:
            await self._emit(
                plan_id, {"kind": "bridge_progress", **payload, "order_id": order_id}
            )

        try:
            resolution = await watch_for_fill(
                bridge,
                order_id,
                poll_interval_s=self._poll_interval_s,
                max_poll_s=self._max_poll_s,
                on_progress=_progress,
            )
        except Exception as exc:  # noqa: BLE001 — orchestrator must not crash
            logger.warning(
                "composed_plan watch crashed for plan_id=%s order_id=%s: %s",
                plan_id, order_id, exc,
            )
            return FillResolution(
                order_id=order_id, state="failed", resolved_at=0.0,
            )

        # On filled, mutate the step + emit one final update.
        if resolution.state == "filled" and resolution.actual_dst_amount is not None:
            try:
                rebuild_step_with_actual_delta(
                    deposit_step,
                    snapshot=snapshot,
                    fill=resolution,
                )
                promote_step_to_ready(deposit_step)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "composed_plan rebuild failed for plan_id=%s: %s",
                    plan_id, exc,
                )
                resolution_state = "failed"
            else:
                resolution_state = "filled"
            await self._emit(plan_id, {
                "kind": "bridge_resolution",
                "state": resolution_state,
                "actual_dst_amount": resolution.actual_dst_amount,
                "realized_slippage_bps": resolution.realized_slippage_bps,
                "step_id": deposit_step.step_id,
                "step_status": deposit_step.status,
            })
        else:
            # cancelled / failed / timeout — keep the blocker, emit one final.
            # V7-066 — route through decide_recovery so the SSE payload carries
            # the structured recovery posture (auto-rebuild wider / ASK_USER /
            # NOTIFY) for the frontend to render the recovery card.
            from src.defi.recovery import FailureKind, decide_recovery
            _recovery = decide_recovery(
                FailureKind.BRIDGE_SUBMISSION_FAILED,
                step_kind="bridge",
            )
            await self._emit(plan_id, {
                "kind": "bridge_resolution",
                "state": resolution.state,
                "actual_dst_amount": resolution.actual_dst_amount,
                "step_id": deposit_step.step_id,
                "step_status": deposit_step.status,
                "recovery": _recovery.to_dict(),
            })
        # Drop the watch entry once the task finishes.
        async with self._lock:
            self._watches.pop(plan_id, None)
        return resolution

    async def _emit(self, plan_id: str, payload: dict) -> None:
        if self._on_plan_update is None:
            return
        try:
            await self._on_plan_update(plan_id, payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("plan-update callback failed for %s: %s", plan_id, exc)


# ── Module-level singleton for runtime wire-in ──
#
# The runtime should construct one orchestrator at startup, install its
# SSE push callback via set_runtime_callback(), and call
# get_composed_plan_orchestrator().watch(...) from the receipt-watcher
# after the bridge leg tx confirms (with the order_id observed in the
# tx receipt).

_singleton: ComposedPlanOrchestrator | None = None


def get_composed_plan_orchestrator() -> ComposedPlanOrchestrator:
    global _singleton
    if _singleton is None:
        _singleton = ComposedPlanOrchestrator()
    return _singleton


def set_runtime_callback(cb: PlanUpdateCallback) -> None:
    """Install the runtime's SSE push callback into the singleton.
    Call once at runtime startup."""
    orch = get_composed_plan_orchestrator()
    orch._on_plan_update = cb


def reset_singleton_for_tests() -> None:
    """Clear the singleton — tests-only escape hatch."""
    global _singleton
    _singleton = None
