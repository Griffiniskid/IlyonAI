"""POST /api/v1/plans/{plan_id}/bridge-confirmed — bridge-leg signed handoff.

After the user signs the bridge tx, the frontend reports the resulting
DLN order_id back here so the pending-plan registry can re-key the
entry. The deBridge webhook fires later with that order_id, looks up
the plan, and resolves the deposit step.

Body shape: { order_id: str, tx_hash?: str, old_order_id?: str }
"""
from __future__ import annotations

import logging

from aiohttp import web

logger = logging.getLogger(__name__)


async def bridge_confirmed(request: web.Request) -> web.Response:
    plan_id = request.match_info["plan_id"]
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "bad_json"}, status=400)
    new_order_id = body.get("order_id")
    if not isinstance(new_order_id, str) or not new_order_id:
        return web.json_response({"ok": False, "error": "invalid_order_id"}, status=400)
    old_order_id = body.get("old_order_id")

    from src.defi.execution.pending_plans import list_by_wallet, rekey

    if old_order_id:
        result = await rekey(old_order_id, new_order_id)
        if result is None:
            return web.json_response(
                {"ok": False, "error": "no_pending_plan_for_old_order_id"},
                status=404,
            )
        return web.json_response({
            "ok": True, "plan_id": plan_id,
            "old_order_id": old_order_id,
            "order_id": new_order_id,
            "step_id": result.deposit_step.step_id,
        })

    # No old_order_id provided — caller wants to register the order_id
    # directly without a rekey. Look up the plan by plan_id + wallet.
    user_wallet = (body.get("wallet") or "").lower()
    if not user_wallet.startswith("0x") or len(user_wallet) != 42:
        return web.json_response(
            {"ok": False, "error": "invalid_wallet"}, status=400,
        )
    plans = await list_by_wallet(user_wallet)
    target = next((p for p in plans if p.plan_id == plan_id), None)
    if target is None:
        return web.json_response(
            {"ok": False, "error": "no_pending_plan_for_plan_id"},
            status=404,
        )
    await rekey(target.order_id, new_order_id)
    return web.json_response({
        "ok": True, "plan_id": plan_id,
        "order_id": new_order_id,
        "step_id": target.deposit_step.step_id,
    })


def setup_bridge_confirmed_routes(app: web.Application) -> None:
    app.router.add_post(
        "/api/v1/plans/{plan_id}/bridge-confirmed", bridge_confirmed,
    )
