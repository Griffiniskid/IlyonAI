"""POST /api/v1/plans/{plan_id}/steps/{step_id}/permit2 — frontend signature handoff.

When the user signs the Permit2 PermitSingle in MetaMask, the frontend
POSTs the signature here. The runtime caches it on the step so the
final modifyLiquidities/swap calldata can include it without re-prompting.
"""
from __future__ import annotations

import logging
from typing import Any

from aiohttp import web

logger = logging.getLogger(__name__)


async def attach_permit2_signature(request: web.Request) -> web.Response:
    plan_id = request.match_info["plan_id"]
    step_id = request.match_info["step_id"]
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "bad_json"}, status=400)

    signature = body.get("signature")
    permit = body.get("permit")
    if not isinstance(signature, str) or not signature.startswith("0x"):
        return web.json_response({"ok": False, "error": "invalid_signature"}, status=400)
    if not isinstance(permit, dict):
        return web.json_response({"ok": False, "error": "invalid_permit"}, status=400)

    cache: dict[str, dict[str, Any]] = request.app.setdefault(
        "_permit2_signatures", {}
    )
    cache[f"{plan_id}:{step_id}"] = {
        "signature": signature,
        "permit": permit,
    }
    logger.info("permit2 signature cached: plan=%s step=%s", plan_id, step_id)
    return web.json_response({
        "ok": True, "plan_id": plan_id, "step_id": step_id, "cached": True,
    })


async def read_permit2_signature(request: web.Request) -> web.Response:
    plan_id = request.match_info["plan_id"]
    step_id = request.match_info["step_id"]
    cache: dict = request.app.get("_permit2_signatures", {}) or {}
    row = cache.get(f"{plan_id}:{step_id}")
    if row is None:
        return web.json_response({"ok": False, "error": "not_found"}, status=404)
    return web.json_response({"ok": True, **row})


def setup_plan_permit2_routes(app: web.Application) -> None:
    app.router.add_post(
        "/api/v1/plans/{plan_id}/steps/{step_id}/permit2",
        attach_permit2_signature,
    )
    app.router.add_get(
        "/api/v1/plans/{plan_id}/steps/{step_id}/permit2",
        read_permit2_signature,
    )
