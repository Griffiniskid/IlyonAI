"""Spec §6f — stuck-balance recovery posture.

When tx N of M succeeds but tx N+1 fails, the user has an intermediate
token sitting in their wallet (post-swap, pre-deposit). The assistant
must take a clear posture. This module is the decision tree.

HARD RULE (spec §6f): never auto-refund-swap-back without user consent.
A refund swap is a second taxable event and a second slippage cost. The
only auto-action allowed is auto-rebuild with wider slippage on the same
intent, within the user's slippage_cap_bps.

The recovery decision is consumed by the planner runtime to emit a
recovery_offer step / blocker card in chat. Callers should feed the
failed step's typed error_kind, elapsed time since failure, and the
user's slippage cap, then surface the returned Recovery as the next UI
state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class RecoveryAction(str, Enum):
    AUTO_REBUILD = "AUTO_REBUILD"      # wider slippage, same intent, no user prompt
    ASK_USER = "ASK_USER"              # surface alternatives ranked by similarity
    NO_AUTO = "NO_AUTO"                # three explicit buttons — user picks
    NOTIFY = "NOTIFY"                  # in-app (+ optional channels) notification
    ESCALATE = "ESCALATE"              # surface as support-needed (rare)


class FailureKind(str, Enum):
    SLIPPAGE_BREACH = "slippage_breach"
    POOL_PAUSED = "pool_paused"
    POOL_REMOVED = "pool_removed"
    DEPOSIT_CAP_REACHED = "deposit_cap_reached"
    BRIDGE_SUBMISSION_FAILED = "bridge_submission_failed"
    USER_CANCELLED = "user_cancelled"
    GAS_INSUFFICIENT = "gas_insufficient"
    EXEC_REVERT = "exec_revert"
    SIMULATION_FAIL = "simulation_fail"
    BLOCKHASH_EXPIRED = "blockhash_expired"
    BASE_FEE_SPIKE = "base_fee_spike"
    # V7-067 — typed failure kinds for the blocker codes that previously
    # only existed as plain strings on ExecutionBlocker.code. Adding them
    # to the enum lets the recovery dispatcher route on a single typed
    # union without string fallbacks in callsites.
    NULL_ROUTE = "null_route"
    AGGREGATOR_CIRCUIT_BREAKER = "aggregator_circuit_breaker"
    WALLET_CHAIN_MISMATCH = "wallet_chain_mismatch"
    INSUFFICIENT_BALANCE = "insufficient_balance"
    GAS_TOPUP_REQUIRED = "gas_topup_required"
    UNKNOWN = "unknown"


@dataclass
class Recovery:
    """Typed recovery decision for a failed step."""

    action: RecoveryAction
    posture: str                              # one-line headline for chat
    new_slippage_bps: int | None = None       # set when action=AUTO_REBUILD
    alternatives: list[dict] = field(default_factory=list)  # ranked alt pools
    buttons: list[str] = field(default_factory=list)        # NO_AUTO / ASK_USER
    channels: list[str] = field(default_factory=list)       # NOTIFY destinations
    rationale: str = ""                       # detail line for chat

    def to_dict(self) -> dict:
        return {
            "action": self.action.value,
            "posture": self.posture,
            "new_slippage_bps": self.new_slippage_bps,
            "alternatives": self.alternatives,
            "buttons": self.buttons,
            "channels": self.channels,
            "rationale": self.rationale,
        }


def decide_recovery(
    failure_kind: FailureKind | str,
    *,
    step_kind: str = "deposit",
    elapsed_since_fail_s: int = 0,
    current_slippage_bps: int = 50,
    user_slippage_cap_bps: int = 500,
    alternatives_lookup: Callable[[str], list[dict]] | None = None,
    pool_id: str | None = None,
    proposed_action: str | None = None,
) -> Recovery:
    """Map a failed-step context to a typed Recovery posture.

    Decision tree (evaluated top-down, spec §6f):
        1. Slippage breach within 5 min → AUTO_REBUILD with wider slippage
           (capped by user's slippage_cap_bps). One-click resume.
        2. Pool paused / removed / deposit cap reached → ASK_USER with
           ranked alternatives. Never auto-route — user picks.
        3. Bridge submission failed (step_kind=bridge) → hold balance,
           offer alternative bridges (LI.FI / Socket / cancel-refund-DLN).
        4. User cancelled in wallet → NO_AUTO with three buttons (Resume
           deposit / Swap back to source / Leave in wallet).
        5. >30 minutes since failure without user action → NOTIFY in-app.
        6. Default: ASK_USER with three generic buttons.

    HARD RULE: never auto-refund-swap-back. The only auto-action is
    AUTO_REBUILD with wider slippage on the same intent. V7-068 wires
    `src.shield.refund_guard.guard_refund` as a chokepoint: if the
    caller's `proposed_action` (or the step_kind itself) names a
    refund-swap-back action, we short-circuit to a NO_AUTO recovery
    with FORBIDDEN_REFUND_SWAP_BACK so the frontend renders a refusal
    card instead of building calldata.
    """
    # V7-068 — global refund-swap-back guard.
    from src.shield.refund_guard import guard_refund as _guard_refund
    for _candidate in (proposed_action, step_kind):
        _blocker = _guard_refund(_candidate or "", {"step_kind": step_kind, "pool_id": pool_id})
        if _blocker:
            return Recovery(
                action=RecoveryAction.NO_AUTO,
                posture="Refused: auto-refund-swap-back is never allowed",
                buttons=["Leave in wallet", "Resume deposit", "Swap back (explicit)"],
                rationale=(
                    f"Shield refused proposed action '{_candidate}' (code {_blocker}). "
                    f"Spec §6f hard rule: refund-swap-back is a second taxable event + "
                    f"second slippage hit and requires explicit user button-click. "
                    f"Never auto."
                ),
            )

    if isinstance(failure_kind, str):
        try:
            failure_kind = FailureKind(failure_kind)
        except ValueError:
            failure_kind = FailureKind.UNKNOWN

    # 1. Slippage breach + recent → auto-rebuild wider, capped by user pref.
    if failure_kind == FailureKind.SLIPPAGE_BREACH and elapsed_since_fail_s < 300:
        widened = min(max(current_slippage_bps * 2, current_slippage_bps + 25), user_slippage_cap_bps)
        if widened > current_slippage_bps:
            return Recovery(
                action=RecoveryAction.AUTO_REBUILD,
                posture="Auto-rebuild with wider slippage",
                new_slippage_bps=widened,
                rationale=(
                    f"Slippage breach within 5 min. Retrying with {widened} bps "
                    f"(within your cap {user_slippage_cap_bps} bps). No refund swap."
                ),
            )
        # Already at user's cap — fall through to ASK_USER.

    # 2. Pool paused / removed / capped → ranked alternatives, never auto.
    if failure_kind in {
        FailureKind.POOL_PAUSED,
        FailureKind.POOL_REMOVED,
        FailureKind.DEPOSIT_CAP_REACHED,
    }:
        alts: list[dict] = []
        if alternatives_lookup is not None and pool_id:
            try:
                alts = list(alternatives_lookup(pool_id) or [])
            except Exception:  # noqa: BLE001 — alternatives lookup is best-effort
                alts = []
        # BUG-RC-019: the prior text always said "surfacing alternatives"
        # even when the lookup returned zero — tester saw the promise but
        # no alternatives followed. Only promise alternatives when the
        # lookup actually returned options; otherwise tell the user that
        # no equivalent pool is available and suggest a fresh search.
        if alts:
            posture = "Pool unavailable — surfacing alternatives"
            rationale = (
                "Pool removed / paused / cap reached. Alternatives ranked by APR "
                "+ similarity. Never auto-route — you pick."
            )
            buttons = ["Pick alternative", "Leave funds in wallet", "Swap back to source"]
        else:
            posture = "Pool unavailable — no equivalent alternatives in registry"
            rationale = (
                "Pool removed / paused / cap reached. No equivalent pool was "
                "found in the executable registry for this asset / chain / risk "
                "tier. Run a fresh search with broader constraints, or pick a "
                "different protocol family entirely."
            )
            buttons = ["Run a fresh search", "Leave funds in wallet", "Swap back to source"]
        return Recovery(
            action=RecoveryAction.ASK_USER,
            posture=posture,
            alternatives=alts[:3],
            buttons=buttons,
            rationale=rationale,
        )

    # 3. Bridge submission failed mid-flow → hold + alt bridges.
    if failure_kind == FailureKind.BRIDGE_SUBMISSION_FAILED or (
        step_kind.lower() == "bridge" and failure_kind == FailureKind.EXEC_REVERT
    ):
        return Recovery(
            action=RecoveryAction.ASK_USER,
            posture="Bridge submission failed — alternative bridges available",
            buttons=["Try LI.FI", "Try Socket", "Cancel and refund via DLN"],
            rationale=(
                "Bridge submission errored. Intermediate balance held on source chain. "
                "Pick an alternative bridge or cancel + refund through DLN."
            ),
        )

    # 4. User cancelled wallet popup → three explicit buttons.
    if failure_kind == FailureKind.USER_CANCELLED:
        return Recovery(
            action=RecoveryAction.NO_AUTO,
            posture="You cancelled in the wallet — pick how to proceed",
            buttons=["Resume deposit", "Swap back to source", "Leave in wallet"],
            rationale=(
                "Wallet popup was rejected. Three explicit buttons. Hard rule: "
                "swap-back is user-explicit only (second taxable event + slippage)."
            ),
        )

    # 5. Long elapsed without recovery → notify, don't act.
    if elapsed_since_fail_s > 1800:
        return Recovery(
            action=RecoveryAction.NOTIFY,
            posture="Stuck >30 min — notifying via in-app channel",
            channels=["in_app"],
            rationale=(
                "User absent for >30 minutes. Send notification but never auto-act "
                "on funds. Surface intermediate balance with explicit recovery card "
                "when user returns."
            ),
        )

    # 6. Default: ASK_USER with safe-default buttons.
    return Recovery(
        action=RecoveryAction.ASK_USER,
        posture="Step failed — pick recovery",
        buttons=["Retry step", "Swap back to source", "Leave in wallet"],
        rationale=(
            f"Step failure kind={failure_kind.value}. Surfacing three user-explicit "
            f"options. Hard rule: never auto-refund-swap-back."
        ),
    )


# ── V7-066 — recovery enrichment wiring for blocker callsites ────────────────
#
# Blocker emit sites across the codebase (pool executor, wallet_swap,
# execute_pool_position, composed_plan_orchestrator) historically surfaced an
# `ExecutionBlocker` (or `err_envelope`) with only a static `code` + `detail`.
# That left the frontend without the structured recovery posture the user
# needs ("auto-rebuild with wider slippage", "swap-back forbidden", "pick an
# alternative pool"). V7-066 wires every blocker callsite through
# `enrich_blocker_with_recovery` so the recovery dict is always attached.
#
# The helper is intentionally non-invasive: it never mutates the blocker's
# `code` or `title`, it only appends a `Recovery: <posture> — <rationale>`
# line to `detail` and attaches the full Recovery.to_dict() under a
# `_recovery` attribute (frontend can pick it up via the to_dict roundtrip
# the orchestrator already does). Callers that emit an `err_envelope`
# instead of a blocker can use `enrich_err_envelope_with_recovery` which
# stitches the recovery dict into the envelope's payload.

def enrich_blocker_with_recovery(
    blocker,
    failure_kind: FailureKind | str,
    *,
    step_kind: str = "deposit",
    pool_id: str | None = None,
    proposed_action: str | None = None,
    current_slippage_bps: int = 50,
    user_slippage_cap_bps: int = 500,
    elapsed_since_fail_s: int = 0,
    alternatives_lookup: Callable[[str], list[dict]] | None = None,
) -> "Recovery":
    """Attach a Recovery posture to an in-flight ExecutionBlocker.

    Mutates the blocker's `detail` in place (appends a one-line recovery
    summary) and stashes the full recovery payload on `blocker._recovery`
    for the SSE / plan serializer to pick up.

    Returns the Recovery so callers can also surface it directly (e.g. in
    an SSE plan_update event from the composed_plan orchestrator).
    """
    recovery = decide_recovery(
        failure_kind,
        step_kind=step_kind,
        elapsed_since_fail_s=elapsed_since_fail_s,
        current_slippage_bps=current_slippage_bps,
        user_slippage_cap_bps=user_slippage_cap_bps,
        alternatives_lookup=alternatives_lookup,
        pool_id=pool_id,
        proposed_action=proposed_action,
    )
    # Append a recovery summary line so the existing frontend that only
    # reads `detail` still shows the recovery posture to the user.
    summary_line = f"Recovery: {recovery.posture} — {recovery.rationale}"
    try:
        existing = getattr(blocker, "detail", "") or ""
        if summary_line not in existing:
            blocker.detail = (existing + ("\n\n" if existing else "") + summary_line).strip()
    except Exception:  # noqa: BLE001 — blocker may be a frozen dataclass in some paths
        pass
    # Stash the full structured dict so richer UIs can render alternatives,
    # buttons, channels, new_slippage_bps, etc.
    try:
        setattr(blocker, "_recovery", recovery.to_dict())
    except Exception:  # noqa: BLE001
        pass
    return recovery


def enrich_err_envelope_with_recovery(
    envelope,
    failure_kind: FailureKind | str,
    *,
    step_kind: str = "swap",
    pool_id: str | None = None,
    proposed_action: str | None = None,
    current_slippage_bps: int = 50,
    user_slippage_cap_bps: int = 500,
    elapsed_since_fail_s: int = 0,
) -> "Recovery":
    """Attach a Recovery posture to a ToolEnvelope returned from a tool.

    Mutates the envelope's `error.message` in place (appends a one-line
    recovery summary) and stashes the full recovery payload under
    `envelope.card_payload["_recovery"]` (creating the dict if needed).
    Returns the Recovery so callers can route on it.
    """
    recovery = decide_recovery(
        failure_kind,
        step_kind=step_kind,
        elapsed_since_fail_s=elapsed_since_fail_s,
        current_slippage_bps=current_slippage_bps,
        user_slippage_cap_bps=user_slippage_cap_bps,
        pool_id=pool_id,
        proposed_action=proposed_action,
    )
    summary_line = f"Recovery: {recovery.posture} — {recovery.rationale}"
    try:
        err = getattr(envelope, "error", None)
        if err is not None:
            msg = getattr(err, "message", "") or ""
            if summary_line not in msg:
                err.message = (msg + ("\n\n" if msg else "") + summary_line).strip()
    except Exception:  # noqa: BLE001
        pass
    try:
        payload = getattr(envelope, "card_payload", None)
        if payload is None:
            envelope.card_payload = {"_recovery": recovery.to_dict()}
        elif isinstance(payload, dict):
            payload["_recovery"] = recovery.to_dict()
    except Exception:  # noqa: BLE001
        pass
    return recovery
