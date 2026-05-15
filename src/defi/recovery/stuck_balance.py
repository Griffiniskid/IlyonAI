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
    AUTO_REBUILD with wider slippage on the same intent.
    """
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
        return Recovery(
            action=RecoveryAction.ASK_USER,
            posture="Pool unavailable — surfacing alternatives",
            alternatives=alts[:3],
            buttons=["Pick alternative", "Leave funds in wallet", "Swap back to source"],
            rationale=(
                "Pool removed / paused / cap reached. Alternatives ranked by APR "
                "+ similarity. Never auto-route — you pick."
            ),
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
