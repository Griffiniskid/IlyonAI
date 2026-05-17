"""V7-024 pin tests for the four position-health alert detectors."""
from __future__ import annotations

from datetime import datetime, timedelta

from src.defi.position_monitor.detectors import (
    detect_fee_apr_drop,
    detect_gas_favorable,
    detect_out_of_range,
    detect_tvl_exodus,
)


# --------------------------------------------------------------------------- #
# detect_out_of_range
# --------------------------------------------------------------------------- #

def _ooo_snap(in_range: bool, ts: datetime | None = None) -> dict:
    """Minimal V3 snapshot shaped like PositionHealth.to_dict()."""
    d = {"position_id": "pos-1", "in_range": in_range, "realized_fee_apr": 1.0}
    if ts is not None:
        d["snapshot_at"] = ts.isoformat()
    return d


def test_out_of_range_25_contiguous_false_fires():
    base = datetime(2026, 1, 1, 0, 0, 0)
    # 25 snapshots, one per hour, all out-of-range → 24h span breached.
    snaps = [_ooo_snap(False, base + timedelta(hours=i)) for i in range(25)]
    alert = detect_out_of_range(snaps)
    assert alert is not None
    assert alert["alert_type"] == "OUT_OF_RANGE"
    assert alert["severity"] == "warning"
    assert alert["payload"]["hours_out_of_range"] >= 24.0
    assert alert["payload"]["contiguous_snapshots"] == 25
    assert "out of range" in alert["message"].lower()


def test_out_of_range_all_in_range_returns_none():
    base = datetime(2026, 1, 1, 0, 0, 0)
    snaps = [_ooo_snap(True, base + timedelta(hours=i)) for i in range(30)]
    assert detect_out_of_range(snaps) is None


def test_out_of_range_brief_6h_below_threshold_returns_none():
    base = datetime(2026, 1, 1, 0, 0, 0)
    snaps = [_ooo_snap(False, base + timedelta(hours=i)) for i in range(6)]
    assert detect_out_of_range(snaps) is None


def test_out_of_range_skips_v2_positions_without_in_range_key():
    # V2 / stable: no `in_range` key at all → detector returns None.
    snaps = [{"position_id": "pos-v2", "realized_fee_apr": 1.0} for _ in range(50)]
    assert detect_out_of_range(snaps) is None


def test_out_of_range_recent_return_to_range_resets():
    # 20h out-of-range, then a single in-range snap at the tail → tail is empty.
    base = datetime(2026, 1, 1, 0, 0, 0)
    snaps = [_ooo_snap(False, base + timedelta(hours=i)) for i in range(20)]
    snaps.append(_ooo_snap(True, base + timedelta(hours=20)))
    assert detect_out_of_range(snaps) is None


# --------------------------------------------------------------------------- #
# detect_fee_apr_drop
# --------------------------------------------------------------------------- #

def _apr_snap(apr: float) -> dict:
    return {"position_id": "pos-fee", "in_range": True, "realized_fee_apr": apr}


def test_fee_apr_drop_60pct_drop_fires():
    # 24 baseline snapshots at APR=10, then current=4 → 60% drop.
    snaps = [_apr_snap(10.0) for _ in range(24)] + [_apr_snap(4.0)]
    alert = detect_fee_apr_drop(snaps)
    assert alert is not None
    assert alert["alert_type"] == "FEE_APR_DROP"
    assert alert["payload"]["current_apr"] == 4.0
    assert abs(alert["payload"]["prior_avg_apr"] - 10.0) < 1e-9
    assert abs(alert["payload"]["drop_pct"] - 0.6) < 1e-9


def test_fee_apr_drop_stable_apr_returns_none():
    # Flat APR — zero drop, well below 50% threshold.
    snaps = [_apr_snap(8.5) for _ in range(25)]
    assert detect_fee_apr_drop(snaps) is None


def test_fee_apr_drop_increase_returns_none():
    # APR went UP — never alert on a rising fee rate.
    snaps = [_apr_snap(2.0) for _ in range(24)] + [_apr_snap(9.0)]
    assert detect_fee_apr_drop(snaps) is None


def test_fee_apr_drop_just_below_threshold_returns_none():
    # avg=10, current=5.5 → 45% drop, below 50% default.
    snaps = [_apr_snap(10.0) for _ in range(24)] + [_apr_snap(5.5)]
    assert detect_fee_apr_drop(snaps) is None


# --------------------------------------------------------------------------- #
# detect_tvl_exodus
# --------------------------------------------------------------------------- #

def test_tvl_exodus_35pct_drop_fires():
    # 24-hour TVL history: 1.0M → 0.65M over the window = 35% drop.
    history = [1_000_000.0] + [950_000.0] * 22 + [650_000.0]
    alert = detect_tvl_exodus(history)
    assert alert is not None
    assert alert["alert_type"] == "TVL_EXODUS"
    assert alert["payload"]["start_tvl_usd"] == 1_000_000.0
    assert alert["payload"]["current_tvl_usd"] == 650_000.0
    assert abs(alert["payload"]["drop_pct"] - 0.35) < 1e-9


def test_tvl_exodus_10pct_drop_returns_none():
    # 1.0M → 0.9M = 10% drop, below 30% default.
    history = [1_000_000.0] + [950_000.0] * 22 + [900_000.0]
    assert detect_tvl_exodus(history) is None


def test_tvl_exodus_critical_severity_on_large_drop():
    # 60% drop → severity bumped to critical.
    history = [1_000_000.0] * 23 + [400_000.0]
    alert = detect_tvl_exodus(history)
    assert alert is not None
    assert alert["severity"] == "critical"


# --------------------------------------------------------------------------- #
# detect_gas_favorable
# --------------------------------------------------------------------------- #

def test_gas_favorable_evm_25_gwei_fires():
    alert = detect_gas_favorable("ethereum", 25.0)
    assert alert is not None
    assert alert["alert_type"] == "GAS_FAVORABLE"
    assert alert["severity"] == "info"
    assert alert["payload"]["current_gas_gwei"] == 25.0
    assert alert["payload"]["chain"] == "ethereum"


def test_gas_favorable_evm_80_gwei_returns_none():
    assert detect_gas_favorable("ethereum", 80.0) is None


def test_gas_favorable_solana_returns_none():
    # No gas oracle / gwei concept on Solana — must skip silently.
    assert detect_gas_favorable("solana", 25.0) is None


def test_gas_favorable_arbitrum_low_gas_fires():
    # Other EVM chains qualify too.
    alert = detect_gas_favorable("arbitrum", 0.5)
    assert alert is not None
    assert alert["payload"]["chain"] == "arbitrum"


def test_gas_favorable_chain_case_insensitive():
    alert = detect_gas_favorable("Base", 10.0)
    assert alert is not None
    assert alert["payload"]["chain"] == "base"
