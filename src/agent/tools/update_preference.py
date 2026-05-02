"""Chat-callable tool that persists user preferences."""
from __future__ import annotations

from typing import Any

from src.agent.tools._base import ToolCtx, err_envelope, ok_envelope
from src.api.schemas.agent import ToolEnvelope
from src.storage.agent_preferences import get_or_default, upsert
from src.storage.database import get_database


_ALLOWED_FIELDS = {
    "risk_budget",
    "preferred_chains",
    "blocked_protocols",
    "gas_cap_usd",
    "slippage_cap_bps",
    "notional_double_confirm_usd",
    "auto_rebalance_opt_in",
}


async def update_preference(ctx: ToolCtx, **kwargs: Any) -> ToolEnvelope:
    """Persist a partial patch of user preferences."""
    if ctx.user_id == 0:
        return err_envelope(
            "not_authenticated",
            "Sign in to save preferences. Settings will not persist for guest sessions.",
        )

    patch = {k: v for k, v in kwargs.items() if k in _ALLOWED_FIELDS}
    if not patch:
        return err_envelope(
            "nothing_to_update",
            f"No allowed preference fields provided. Allowed: {sorted(_ALLOWED_FIELDS)}",
        )

    db = await get_database()
    await upsert(db, user_id=ctx.user_id, **patch)
    prefs = await get_or_default(db, user_id=ctx.user_id)
    return ok_envelope(
        data=prefs.as_dict(),
        card_type="preferences",
        card_payload={
            "risk_budget": prefs.risk_budget,
            "preferred_chains": prefs.preferred_chains,
            "blocked_protocols": prefs.blocked_protocols,
            "slippage_cap_bps": prefs.slippage_cap_bps,
            "gas_cap_usd": prefs.gas_cap_usd,
            "notional_double_confirm_usd": prefs.notional_double_confirm_usd,
            "auto_rebalance_opt_in": prefs.auto_rebalance_opt_in,
        },
    )
