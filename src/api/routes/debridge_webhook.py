"""POST /api/v1/debridge/webhook — DLN order lifecycle callback.

deBridge DLN can push order events to a registered webhook URL instead of
the plan runtime polling the order status. This route accepts those events
and turns them into the composed_plan FillResolution shape, which the
runtime rebuild loop consumes via the order_events table.
"""
from __future__ import annotations

import json
import logging
import time

from aiohttp import web

from src.routing.debridge_client import parse_webhook_payload

logger = logging.getLogger(__name__)


async def debridge_webhook(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError):
        return web.json_response({"ok": False, "error": "invalid_json"}, status=400)

    parsed = parse_webhook_payload(payload)
    order_id = parsed.get("order_id")
    state = parsed.get("state")
    if not order_id:
        return web.json_response({"ok": False, "error": "missing_order_id"}, status=400)

    logger.info(
        "debridge webhook: order_id=%s state=%s actual=%s",
        order_id, state, parsed.get("actual_dst_amount"),
    )

    # Persist into an order_events table so the runtime rebuild loop can
    # observe the resolution next time it polls a pending composed plan.
    # The schema (agent_008 migration, deferred) will own this table; for
    # now we cache in app state so live composed-plan tests can drive a
    # fill resolution without waiting for the DB write path.
    cache: dict = request.app.setdefault("_debridge_events", {})
    cache[order_id] = {
        "state": state,
        "actual_dst_amount": parsed.get("actual_dst_amount"),
        "received_at": time.time(),
    }

    return web.json_response({"ok": True, "order_id": order_id, "state": state})


def setup_debridge_routes(app: web.Application) -> None:
    app.router.add_post("/api/v1/debridge/webhook", debridge_webhook)
    app.router.add_get("/api/v1/debridge/events/{order_id}", debridge_event_lookup)


async def debridge_event_lookup(request: web.Request) -> web.Response:
    """Convenience read-back for the runtime + tests to fetch a cached event."""
    order_id = request.match_info["order_id"]
    cache: dict = request.app.get("_debridge_events", {})
    event = cache.get(order_id)
    if not event:
        return web.json_response({"ok": False, "error": "not_found"}, status=404)
    return web.json_response({"ok": True, "order_id": order_id, **event})
