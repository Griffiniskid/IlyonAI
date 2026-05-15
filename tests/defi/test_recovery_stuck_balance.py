"""Tests for spec §6f stuck-balance decision tree."""
from __future__ import annotations

from src.defi.recovery.stuck_balance import (
    FailureKind,
    Recovery,
    RecoveryAction,
    decide_recovery,
)


def test_slippage_breach_recent_auto_rebuild_wider():
    r = decide_recovery(
        FailureKind.SLIPPAGE_BREACH,
        elapsed_since_fail_s=120,
        current_slippage_bps=50,
        user_slippage_cap_bps=500,
    )
    assert r.action == RecoveryAction.AUTO_REBUILD
    assert r.new_slippage_bps == 100  # doubled, within cap
    assert "wider slippage" in r.posture.lower()


def test_slippage_breach_at_cap_falls_to_ask():
    r = decide_recovery(
        FailureKind.SLIPPAGE_BREACH,
        elapsed_since_fail_s=60,
        current_slippage_bps=500,
        user_slippage_cap_bps=500,
    )
    # Already at user's cap → no auto, falls through to default ASK_USER.
    assert r.action == RecoveryAction.ASK_USER
    assert r.new_slippage_bps is None


def test_slippage_breach_old_falls_to_ask():
    r = decide_recovery(
        FailureKind.SLIPPAGE_BREACH,
        elapsed_since_fail_s=600,
        current_slippage_bps=50,
        user_slippage_cap_bps=500,
    )
    assert r.action == RecoveryAction.ASK_USER


def test_pool_paused_asks_user_with_alternatives():
    def _alt_lookup(pid):
        return [
            {"pool_id": "p2", "apr": 12.0, "tvl": 5_000_000},
            {"pool_id": "p3", "apr": 11.0, "tvl": 8_000_000},
        ]

    r = decide_recovery(
        FailureKind.POOL_PAUSED,
        pool_id="orig",
        alternatives_lookup=_alt_lookup,
    )
    assert r.action == RecoveryAction.ASK_USER
    assert len(r.alternatives) == 2
    assert "alternative" in r.posture.lower()


def test_deposit_cap_reached_asks_user():
    r = decide_recovery(FailureKind.DEPOSIT_CAP_REACHED, pool_id="capped-pool")
    assert r.action == RecoveryAction.ASK_USER
    assert "alternative" in r.posture.lower()


def test_pool_removed_alternatives_lookup_failure_still_safe():
    def _broken(pid):
        raise RuntimeError("subgraph down")

    r = decide_recovery(
        FailureKind.POOL_REMOVED,
        pool_id="dead",
        alternatives_lookup=_broken,
    )
    assert r.action == RecoveryAction.ASK_USER
    assert r.alternatives == []


def test_bridge_submission_failed_offers_alts():
    r = decide_recovery(FailureKind.BRIDGE_SUBMISSION_FAILED, step_kind="bridge")
    assert r.action == RecoveryAction.ASK_USER
    assert "LI.FI" in r.buttons[0]
    assert any("DLN" in b for b in r.buttons)


def test_bridge_step_with_exec_revert_offers_alts():
    r = decide_recovery(FailureKind.EXEC_REVERT, step_kind="bridge")
    assert r.action == RecoveryAction.ASK_USER
    assert "LI.FI" in r.buttons[0]


def test_user_cancelled_no_auto_three_buttons():
    r = decide_recovery(FailureKind.USER_CANCELLED)
    assert r.action == RecoveryAction.NO_AUTO
    assert "Resume deposit" in r.buttons
    assert "Swap back to source" in r.buttons
    assert "Leave in wallet" in r.buttons


def test_long_absence_notify_only():
    r = decide_recovery(FailureKind.UNKNOWN, elapsed_since_fail_s=2_000)
    assert r.action == RecoveryAction.NOTIFY
    assert "in_app" in r.channels


def test_default_ask_user_for_unknown_recent():
    r = decide_recovery(FailureKind.UNKNOWN, elapsed_since_fail_s=10)
    assert r.action == RecoveryAction.ASK_USER
    assert "Retry step" in r.buttons


def test_recovery_to_dict_serialisable():
    r = decide_recovery(
        FailureKind.SLIPPAGE_BREACH,
        elapsed_since_fail_s=10,
        current_slippage_bps=50,
        user_slippage_cap_bps=500,
    )
    d = r.to_dict()
    assert d["action"] == "AUTO_REBUILD"
    assert d["new_slippage_bps"] == 100
    assert isinstance(d["alternatives"], list)


def test_string_failure_kind_accepted():
    r = decide_recovery(
        "slippage_breach",  # string form, not enum
        elapsed_since_fail_s=10,
        current_slippage_bps=50,
        user_slippage_cap_bps=500,
    )
    assert r.action == RecoveryAction.AUTO_REBUILD


def test_unknown_string_failure_falls_back():
    r = decide_recovery("garbage_value", elapsed_since_fail_s=10)
    assert r.action == RecoveryAction.ASK_USER


def test_hard_rule_no_auto_refund_swap_back():
    """Spec §6f hard rule: never auto-refund-swap-back. Walk every
    failure kind and assert no decision returns an auto action that
    performs swap-back.
    """
    for kind in FailureKind:
        r = decide_recovery(kind, elapsed_since_fail_s=10)
        # AUTO_REBUILD never includes swap-back; AUTO_REBUILD only
        # widens slippage on the same intent.
        assert r.action != RecoveryAction.AUTO_REBUILD or "swap back" not in r.posture.lower()
        # NO_AUTO and ASK_USER may surface swap-back as a button — that's
        # user-explicit, allowed.
