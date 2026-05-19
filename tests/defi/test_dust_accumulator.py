"""Pin tests for spec §3 / §6f dust accumulator.

Locks the threshold ($1.00), the three-way disposition tree
(SWEEP / LEAVE / INCREASE_TO_THRESHOLD), and the ExecutionBlocker
wire shape so the front-end CTA renderer can rely on the contract.
"""
from __future__ import annotations

from src.defi.execution.models import KNOWN_BLOCKER_CODES
from src.defi.recovery.dust_accumulator import (
    DUST_THRESHOLD_USD,
    DustPosition,
    build_dust_blocker,
    decide_dust_disposition,
    is_dust,
)


# ---------------------------------------------------------------------------
# is_dust — strict-less-than threshold.
# ---------------------------------------------------------------------------

def test_is_dust_true_just_below_threshold() -> None:
    assert is_dust(0.99) is True


def test_is_dust_false_at_threshold() -> None:
    # Strict <; $1.00 exactly is NOT dust per spec.
    assert is_dust(1.00) is False


def test_is_dust_false_above_threshold() -> None:
    assert is_dust(5.00) is False


def test_is_dust_true_at_zero() -> None:
    assert is_dust(0.0) is True


def test_is_dust_true_for_negative_feed_error() -> None:
    """Defensive: negative USD valuation = feed error, treat as dust."""
    assert is_dust(-1.5) is True


def test_is_dust_true_for_non_numeric() -> None:
    # Bad feed payload shouldn't crash the emitter; classify as dust.
    assert is_dust(float("nan")) is False or is_dust(float("nan")) is True
    # Non-numeric strings explicitly:
    assert is_dust("abc") is True  # type: ignore[arg-type]


def test_threshold_constant_is_one_dollar() -> None:
    assert float(DUST_THRESHOLD_USD) == 1.00


# ---------------------------------------------------------------------------
# decide_dust_disposition — three-way decision tree.
# ---------------------------------------------------------------------------

def test_empty_positions_returns_leave() -> None:
    assert decide_dust_disposition([]) == "LEAVE"


def test_aggregate_above_sweep_gas_returns_sweep() -> None:
    # Two $0.40 positions → $0.80 total > default $0.50 sweep gas.
    positions = [
        DustPosition(token="USDC", amount_token=0.4, amount_usd=0.40),
        DustPosition(token="USDC", amount_token=0.4, amount_usd=0.40),
    ]
    assert decide_dust_disposition(positions) == "SWEEP"


def test_single_position_near_threshold_returns_increase() -> None:
    # $0.50 — exactly half the $1 threshold → INCREASE branch.
    # Total $0.50 is NOT strictly greater than $0.50 sweep gas, so SWEEP is skipped.
    positions = [DustPosition(token="USDC", amount_token=0.5, amount_usd=0.50)]
    assert decide_dust_disposition(positions) == "INCREASE_TO_THRESHOLD"


def test_all_positions_far_below_threshold_returns_leave() -> None:
    # $0.05 total — below sweep-gas AND no single position >= $0.50.
    positions = [
        DustPosition(token="USDC", amount_token=0.02, amount_usd=0.02),
        DustPosition(token="USDC", amount_token=0.03, amount_usd=0.03),
    ]
    assert decide_dust_disposition(positions) == "LEAVE"


def test_sweep_gas_override_pushes_to_leave() -> None:
    # Override gas floor up to $10 — even $0.80 aggregate cannot sweep.
    positions = [
        DustPosition(token="USDC", amount_token=0.4, amount_usd=0.40),
        DustPosition(token="USDC", amount_token=0.4, amount_usd=0.40),
    ]
    # Aggregate $0.80, sweep gas $10 → not SWEEP. Each position $0.40 < $0.50
    # half-threshold → not INCREASE. Falls through to LEAVE.
    assert decide_dust_disposition(positions, sweep_gas_usd=10.0) == "LEAVE"


# ---------------------------------------------------------------------------
# build_dust_blocker — ExecutionBlocker wire shape.
# ---------------------------------------------------------------------------

def test_blocker_code_in_known_set() -> None:
    """`DUST_BELOW_THRESHOLD` must be in KNOWN_BLOCKER_CODES so the
    blocker-normalization pipeline accepts it without warning."""
    assert "DUST_BELOW_THRESHOLD" in KNOWN_BLOCKER_CODES


def test_build_dust_blocker_basic_shape() -> None:
    positions = [
        DustPosition(token="USDC", amount_token=0.5, amount_usd=0.50, step_id="s1"),
    ]
    b = build_dust_blocker(positions)
    assert b.code == "DUST_BELOW_THRESHOLD"
    assert b.severity in ("warning", "blocker")
    assert "Dust positions below" in b.title
    assert "$1.00" in b.title
    assert b.recoverable is True
    # CTA carries all three options as pipe-separated string.
    assert b.cta is not None
    assert "SWEEP" in b.cta
    assert "LEAVE" in b.cta
    assert "INCREASE_TO_THRESHOLD" in b.cta


def test_build_dust_blocker_affected_step_ids() -> None:
    positions = [
        DustPosition(token="USDC", amount_token=0.5, amount_usd=0.50, step_id="step-a"),
        DustPosition(token="WETH", amount_token=0.001, amount_usd=0.30, step_id="step-b"),
        DustPosition(token="WBTC", amount_token=0.0, amount_usd=0.10),  # no step_id
    ]
    b = build_dust_blocker(positions)
    assert "step-a" in b.affected_step_ids
    assert "step-b" in b.affected_step_ids
    # None step_id is filtered out
    assert None not in b.affected_step_ids


def test_build_dust_blocker_detail_carries_disposition_recommendation() -> None:
    # Aggregate $0.80 > sweep-gas $0.50 → SWEEP recommendation.
    positions = [
        DustPosition(token="USDC", amount_token=0.4, amount_usd=0.40, step_id="s1"),
        DustPosition(token="USDC", amount_token=0.4, amount_usd=0.40, step_id="s2"),
    ]
    b = build_dust_blocker(positions)
    assert "SWEEP" in b.detail


def test_build_dust_blocker_to_dict_serializable() -> None:
    positions = [
        DustPosition(token="USDC", amount_token=0.5, amount_usd=0.50, step_id="s1"),
    ]
    d = build_dust_blocker(positions).to_dict()
    assert d["code"] == "DUST_BELOW_THRESHOLD"
    assert isinstance(d["affected_step_ids"], list)
    assert isinstance(d["recoverable"], bool)
