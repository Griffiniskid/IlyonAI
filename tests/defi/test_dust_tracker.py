"""Pin test for spec §5e dust tracker — `src/defi/dust_tracker.py`."""
from __future__ import annotations

from src.defi.dust_tracker import DustDelta, DustTracker


def test_empty_tracker_does_not_resolve() -> None:
    t = DustTracker()
    assert t.cumulative_usd() == 0
    assert t.should_resolve() is False


def test_three_legs_totaling_over_one_dollar_resolves() -> None:
    t = DustTracker()
    t.record("s1", "USDC", 0.40, 0.40)
    t.record("s2", "WETH", 0.0001, 0.30)
    t.record("s3", "WBTC", 0.000005, 0.50)
    # 0.40 + 0.30 + 0.50 = 1.20 > $1.00
    assert round(t.cumulative_usd(), 4) == 1.20
    assert t.should_resolve() is True


def test_three_legs_under_threshold_does_not_resolve() -> None:
    t = DustTracker()
    t.record("s1", "USDC", 0.10, 0.10)
    t.record("s2", "WETH", 0.00005, 0.15)
    t.record("s3", "WBTC", 0.0000025, 0.25)
    # 0.10 + 0.15 + 0.25 = 0.50 < $1.00
    assert round(t.cumulative_usd(), 4) == 0.50
    assert t.should_resolve() is False


def test_to_resolve_card_shape() -> None:
    t = DustTracker()
    t.record("s1", "USDC", 0.40, 0.40)
    t.record("s2", "WETH", 0.0001, 0.30)
    t.record("s3", "WBTC", 0.000005, 0.50)
    card = t.to_resolve_card()
    # All required keys present
    assert card["kind"] == "dust_resolve"
    assert "total_usd" in card
    assert "deltas" in card
    assert "actions" in card
    # 3 legs recorded → 3 deltas serialized
    assert len(card["deltas"]) == 3
    # Three §5e actions exposed
    assert card["actions"] == ["sweep_to_usdc", "leave", "increase_position"]
    assert card["total_usd"] == 1.20
    # Each delta is a dict with the DustDelta fields
    for d in card["deltas"]:
        assert set(d.keys()) == {"step_id", "token", "amount_token", "amount_usd"}


def test_threshold_override_holds() -> None:
    t = DustTracker(threshold_usd=5.00)
    t.record("s1", "USDC", 1.00, 1.00)
    t.record("s2", "WETH", 0.0005, 2.00)
    # $3 cumulative < $5 override threshold
    assert t.cumulative_usd() == 3.00
    assert t.should_resolve() is False


def test_dust_delta_is_dataclass() -> None:
    d = DustDelta(step_id="s1", token="USDC", amount_token=0.5, amount_usd=0.5)
    assert d.step_id == "s1"
    assert d.token == "USDC"
    assert d.amount_token == 0.5
    assert d.amount_usd == 0.5
