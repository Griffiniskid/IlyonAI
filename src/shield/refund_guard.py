"""V7-068 — Global "never auto-refund-swap-back" guard.

Spec §6f hard rule: when an intermediate token is sitting in the wallet
after a partial failure, the assistant must *never* auto-swap that
balance back into the source asset on the user's behalf. A refund swap
is a second taxable event + a second slippage hit, and the user must
explicitly consent to it via a button click.

Historical bugs (resume v5 retro, F03 lifecycle) have shown that this
rule was enforced by convention inside `decide_recovery` but nothing
stopped a future emitter (or a downstream adapter) from synthesising
an auto-swap-back recovery card via a different code path. This module
is the single chokepoint: any caller that wants to materialize a
"refund + swap back" action MUST route through `guard_refund` first.

Returns:
    Optional[str] — a blocker code when the action is forbidden, else
    None when the action is safe to proceed.
"""
from __future__ import annotations

from typing import Optional


# Exact-match forbidden action labels. Callers that emit these strings
# verbatim are refused outright. Membership check is case-insensitive
# at lookup time (see `guard_refund`).
FORBIDDEN_REFUND_CODES: set[str] = {"REFUND_SWAP_BACK", "AUTO_SWAP_REFUND"}

# Spec §6c blocker code surfaced when the guard refuses. Kept in
# lockstep with `src/defi/execution/models.py::KNOWN_BLOCKER_CODES` so
# the frontend recovery card has a stable token to render.
FORBIDDEN_REFUND_SWAP_BACK_BLOCKER_CODE = "FORBIDDEN_REFUND_SWAP_BACK"


def guard_refund(action: str, leg: dict) -> Optional[str]:
    """Refuse forbidden refund-swap-back actions.

    Returns a blocker code string if the proposed recovery action would
    auto-swap a refunded output back to the original input. Returns
    None when the action is safe (normal swap, deposit, withdraw, etc.).

    Decision rules:
        1. Empty / falsy action → None (no action to guard).
        2. Action matches `FORBIDDEN_REFUND_CODES` exactly
           (case-insensitive) → forbidden.
        3. Action contains BOTH "refund" AND "swap" tokens (lowercase
           substring match) → forbidden. Catches free-form labels like
           "swap_refund_back", "auto_refund_swap", "refundSwapBack".

    The `leg` argument is reserved for future per-step context (e.g.
    chain, asset pair, USD notional) so callers can pass the failed
    leg's dict verbatim without reshaping. Currently unused beyond the
    type signature; intentionally permissive so the call site stays
    one line.
    """
    if not action:
        return None
    action_lower = str(action).lower()
    # Exact-match forbidden codes (case-insensitive).
    if action_lower in {c.lower() for c in FORBIDDEN_REFUND_CODES}:
        return FORBIDDEN_REFUND_SWAP_BACK_BLOCKER_CODE
    # Substring co-occurrence — catches free-form labels.
    if "refund" in action_lower and "swap" in action_lower:
        return FORBIDDEN_REFUND_SWAP_BACK_BLOCKER_CODE
    return None
