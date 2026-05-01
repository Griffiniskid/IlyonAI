"""Agent preferences REST API routes."""
from __future__ import annotations

from aiohttp import web

from src.storage.database import get_database
from src.storage.agent_preferences import get_or_default, upsert

routes = web.RouteTableDef()


def _get_user_id(request: web.Request) -> int:
    """Extract user_id from X-User-Id header or request storage."""
    header = request.headers.get("X-User-Id")
    if header:
        try:
            return int(header)
        except ValueError:
            pass
    return request.get("user_id", 0)


def _prefs_to_dict(prefs):
    """Serialize AgentPreferences to a dict."""
    return {
        "user_id": prefs.user_id,
        "risk_budget": prefs.risk_budget,
        "preferred_chains": prefs.preferred_chains,
        "blocked_protocols": prefs.blocked_protocols,
        "gas_cap_usd": prefs.gas_cap_usd,
        "slippage_cap_bps": prefs.slippage_cap_bps,
        "notional_double_confirm_usd": prefs.notional_double_confirm_usd,
        "auto_rebalance_opt_in": prefs.auto_rebalance_opt_in,
        "rebalance_auth_signature": prefs.rebalance_auth_signature,
        "rebalance_auth_nonce": prefs.rebalance_auth_nonce,
        "updated_at": prefs.updated_at.isoformat() if prefs.updated_at else None,
    }


@routes.get("/api/v1/agent/preferences")
async def get_preferences(request: web.Request) -> web.Response:
    """Get agent preferences for the authenticated user."""
    user_id = _get_user_id(request)
    if not user_id:
        return web.json_response({"error": "auth_required"}, status=401)

    try:
        db = await get_database()
        prefs = await get_or_default(db, user_id=user_id)
        return web.json_response({
            "status": "ok",
            "data": _prefs_to_dict(prefs),
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@routes.post("/api/v1/agent/preferences")
async def post_preferences(request: web.Request) -> web.Response:
    """Create or update agent preferences for the authenticated user."""
    user_id = _get_user_id(request)
    if not user_id:
        return web.json_response({"error": "auth_required"}, status=401)

    try:
        body = await request.json()
        if not isinstance(body, dict):
            return web.json_response({"error": "invalid_body"}, status=400)
    except Exception:
        return web.json_response({"error": "invalid_body"}, status=400)

    # Filter to valid preference fields
    valid_fields = {
        "risk_budget", "preferred_chains", "blocked_protocols",
        "gas_cap_usd", "slippage_cap_bps", "notional_double_confirm_usd",
        "auto_rebalance_opt_in", "rebalance_auth_signature", "rebalance_auth_nonce",
    }
    kwargs = {k: v for k, v in body.items() if k in valid_fields}

    try:
        db = await get_database()
        await upsert(db, user_id=user_id, **kwargs)
        prefs = await get_or_default(db, user_id=user_id)
        return web.json_response({
            "status": "ok",
            "data": _prefs_to_dict(prefs),
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


def setup_agent_preferences_routes(app: web.Application) -> None:
    """Register agent preferences routes on *app*."""
    app.router.add_routes(routes)
