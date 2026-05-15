"""In-memory pending-plan registry for composed plans.

When a composed plan is built with a PENDING_DST_FILL blocker, the
build path registers (order_id → PendingPlan) here so the deBridge
webhook handler can look up the plan + deposit_step + snapshot on
fill and call composed_plan.rebuild_step_with_actual_delta + promote.

Production deployments swap this for a Redis/Postgres-backed registry
so the data survives a process restart. The dev/staging in-memory
shape is sufficient to drive the runtime wire-in today.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from src.defi.execution.composed_plan import Snapshot
from src.defi.execution.models import ExecutionPlanV3, ExecutionStepV3


@dataclass
class PendingPlan:
    plan_id: str
    order_id: str
    plan: ExecutionPlanV3
    deposit_step: ExecutionStepV3
    snapshot: Snapshot
    user_wallet: str
    src_chain: str
    dst_chain: str


_registry: dict[str, PendingPlan] = {}
_lock = asyncio.Lock()


async def register(p: PendingPlan) -> None:
    async with _lock:
        _registry[p.order_id] = p


async def get(order_id: str) -> PendingPlan | None:
    async with _lock:
        return _registry.get(order_id)


async def drop(order_id: str) -> PendingPlan | None:
    async with _lock:
        return _registry.pop(order_id, None)


async def list_by_wallet(user_wallet: str) -> list[PendingPlan]:
    async with _lock:
        return [
            p for p in _registry.values()
            if p.user_wallet.lower() == user_wallet.lower()
        ]


def clear_for_tests() -> None:
    """Tests-only escape hatch."""
    _registry.clear()


def size() -> int:
    return len(_registry)


async def rekey(old_order_id: str, new_order_id: str) -> PendingPlan | None:
    """Update an entry's order_id — used when the bridge tx confirms with
    the real DLN order_id (the quote-time id may be a placeholder).
    """
    async with _lock:
        entry = _registry.pop(old_order_id, None)
        if entry is None:
            return None
        # Build a new PendingPlan with the updated order_id since the
        # dataclass is frozen-style; reconstruct it directly.
        new_entry = PendingPlan(
            plan_id=entry.plan_id,
            order_id=new_order_id,
            plan=entry.plan,
            deposit_step=entry.deposit_step,
            snapshot=entry.snapshot,
            user_wallet=entry.user_wallet,
            src_chain=entry.src_chain,
            dst_chain=entry.dst_chain,
        )
        _registry[new_order_id] = new_entry
        return new_entry


async def resolve_fill(
    order_id: str,
    *,
    actual_dst_amount: int | None,
    state: str,
) -> dict[str, Any] | None:
    """Webhook handler entry point.

    Looks up the pending plan, calls rebuild_step_with_actual_delta +
    promote_step_to_ready on filled, drops the entry. Returns a
    payload describing the resolution (consumed by SSE push).
    """
    from src.defi.execution.composed_plan import (
        FillResolution,
        promote_step_to_ready,
        rebuild_step_with_actual_delta,
    )
    import time

    p = await get(order_id)
    if p is None:
        return None
    resolution = FillResolution(
        order_id=order_id,
        state=state,
        actual_dst_amount=actual_dst_amount,
        resolved_at=time.time(),
    )
    if state == "filled" and actual_dst_amount is not None:
        rebuild_step_with_actual_delta(
            p.deposit_step, snapshot=p.snapshot, fill=resolution,
        )
        promote_step_to_ready(p.deposit_step)
        await drop(order_id)
        return {
            "kind": "bridge_resolution",
            "state": "filled",
            "plan_id": p.plan_id,
            "step_id": p.deposit_step.step_id,
            "step_status": p.deposit_step.status,
            "actual_dst_amount": actual_dst_amount,
            "user_wallet": p.user_wallet,
        }
    # cancelled / failed — keep blocker, drop registry entry so retries don't
    # hit a stale row, surface the failure to the user.
    await drop(order_id)
    return {
        "kind": "bridge_resolution",
        "state": state,
        "plan_id": p.plan_id,
        "step_id": p.deposit_step.step_id,
        "step_status": p.deposit_step.status,
        "user_wallet": p.user_wallet,
    }
