"""Executability oracle — the single source of truth for "can this pool be
one-click executed right now?".

It dry-runs the SAME builder that real execution uses (`execute_pool_position`),
parses the resulting plan, and classifies the verdict. Results are TTL-cached
per pool so search can ask cheaply.

A pool is EXECUTABLE iff the dry-run produced a signable plan: status `ready`,
or `blocked` whose blockers are ALL soft (user-fixable: balance / gas / stale
sim). Any hard adapter/route/resolution failure, exception, or timeout → NOT
executable (the caller shows a deep link instead of an EXECUTE button).
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

# Soft = the build succeeded but the USER needs to act (fund / re-quote). The
# pool is still executable for a funded wallet, so these keep it executable.
SOFT_BLOCKERS = frozenset({
    "INSUFFICIENT_BALANCE",
    "GAS_TOPUP_REQUIRED",
    "APPROVAL_MISSING",
    "STALE_PRICE_FEED",
    "SIM_STALE",
    "WALLET_NOT_CONNECTED",
})

# Read-only funded mainnet addresses used to dry-run when the caller has no
# wallet connected. Simulation only reads balances — no signing, no funds moved.
_PROBE_SOLANA = "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"
_PROBE_EVM = "0x28C6c06298d514Db089934071355E5743bf21d60"

_CACHE: dict[str, tuple[float, bool, str | None]] = {}
_TTL_S = 300.0
_PROBE_TIMEOUT_S = 10.0


def classify_plan(plan: dict[str, Any] | None) -> tuple[bool, str | None]:
    """Pure classification of a built plan dict. Returns (executable, reason)."""
    if not plan:
        return False, "no execution plan produced"
    if plan.get("status") == "ready":
        return True, None
    codes = [b.get("code") for b in (plan.get("blockers") or [])]
    if codes and all(c in SOFT_BLOCKERS for c in codes):
        return True, None
    return False, f"build failed: {codes or plan.get('status')}"


def _probe_wallet(ctx, chain: str | None) -> str:
    ch = (chain or "").lower()
    if ch in {"solana", "sol"}:
        return (getattr(ctx, "solana_wallet", None) if ctx else None) or _PROBE_SOLANA
    return (getattr(ctx, "evm_wallet", None) if ctx else None) or _PROBE_EVM


async def probe_pool(
    ctx,
    *,
    pool_id: str | None,
    chain: str | None,
    protocol: str | None,
    symbol: str | None = None,
    underlying_tokens: list[str] | None = None,
    amount: float = 20.0,
    asset_in: str | None = None,
) -> tuple[bool, str | None]:
    """Dry-run the real builder for a pool and classify it. Cached per pool."""
    key = str(pool_id) if pool_id else f"{(protocol or '').lower()} {(symbol or '').upper()}".strip()
    hit = _CACHE.get(key)
    now = time.monotonic()
    if hit and (now - hit[0]) < _TTL_S:
        return hit[1], hit[2]

    async def _one_build() -> tuple[bool, str | None]:
        from src.agent.tools.execute_pool_position import execute_pool_position
        env = await asyncio.wait_for(
            execute_pool_position(
                ctx,
                pool=key,
                amount=amount,
                amount_is_usd=True,
                chain=chain,
                asset_in=asset_in,
                user_address=_probe_wallet(ctx, chain),
                extra={
                    "underlying_tokens": underlying_tokens or [],
                    "pool_symbol": symbol,
                    "skip_balance_preflight": True,
                },
            ),
            timeout=_PROBE_TIMEOUT_S,
        )
        plan = getattr(env, "card_payload", None) if getattr(env, "ok", False) else None
        return classify_plan(plan)

    # Double-confirm: external routers (Enso position resolution) are
    # intermittently flaky — a pool that builds once may fail the next call.
    # Require TWO consecutive successful builds before calling it executable so
    # we never advertise an EXECUTE button that a fresh execute will fail.
    ok, reason = False, "not probed"
    try:
        ok, reason = await _one_build()
        if ok:
            ok2, reason2 = await _one_build()
            if not ok2:
                ok, reason = False, f"flaky (2nd build failed): {reason2}"
    except Exception as exc:  # noqa: BLE001 — any failure means "can't build now"
        ok, reason = False, f"probe error: {type(exc).__name__}"

    _CACHE[key] = (now, ok, reason)
    return ok, reason
