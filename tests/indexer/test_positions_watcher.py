"""Spec §9 positions-watcher pin tests.

Stub the wallet source and assert that `detect_drift` + the full
`run_watch_cycle` correctly fan three classes of drift signal through
`notify_proposal`:

  - out_of_range CL position
  - >50 bp price drift between simulated and current quote
  - >50% fee-APR drop vs baseline
"""
from __future__ import annotations

import pytest

from src.indexer.positions_watcher import (
    DriftAlert,
    PositionSnapshot,
    detect_drift,
    run_watch_cycle,
    scan_positions,
)
from src.optimizer.notifier import (
    get_pending_fallback,
    reset_pending_fallback,
    reset_proposal_bus,
)


@pytest.fixture(autouse=True)
def _fresh_state():
    reset_pending_fallback()
    reset_proposal_bus()
    yield
    reset_pending_fallback()
    reset_proposal_bus()


def _make(**kw) -> PositionSnapshot:
    base = dict(
        position_id="pos-1",
        user_id=7,
        protocol="uniswap_v3",
        chain_id=1,
        token0="WETH",
        token1="USDC",
        fee_bps=5,
        liquidity_usd=10_000.0,
        simulated_quote=0.0,
        current_quote=0.0,
        out_of_range=False,
        fee_apr_7d=0.0,
        fee_apr_baseline=0.0,
    )
    base.update(kw)
    return PositionSnapshot(**base)


# ─────────────────────────────────────────────────────────────────────────────
# scan_positions — injected source
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scan_positions_uses_injected_source():
    fixture = [_make(position_id="alpha"), _make(position_id="beta")]

    async def src(user_id: int):
        assert user_id == 7
        return fixture

    out = await scan_positions(user_id=7, position_source=src)
    assert [s.position_id for s in out] == ["alpha", "beta"]


@pytest.mark.asyncio
async def test_scan_positions_swallows_source_errors():
    async def boom(user_id: int):
        raise RuntimeError("subgraph down")

    out = await scan_positions(user_id=1, position_source=boom)
    assert out == []


# ─────────────────────────────────────────────────────────────────────────────
# detect_drift — three signal classes
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detect_drift_flags_out_of_range():
    snaps = [_make(out_of_range=True)]
    alerts = await detect_drift(snaps)
    assert len(alerts) == 1
    assert alerts[0].kind == "out_of_range"
    assert "drifted out of range" in alerts[0].rationale


@pytest.mark.asyncio
async def test_detect_drift_flags_price_drift_above_50bps():
    # 1.0 → 1.01 = 100 bps drift, breaches the 50 bp gate
    snaps = [_make(simulated_quote=1.0, current_quote=1.01)]
    alerts = await detect_drift(snaps)
    assert len(alerts) == 1
    assert alerts[0].kind == "price_drift"
    assert alerts[0].drift_bps == pytest.approx(100.0, rel=1e-3)


@pytest.mark.asyncio
async def test_detect_drift_ignores_price_drift_below_threshold():
    # 1.0 → 1.001 = 10 bps drift, below the 50 bp gate
    snaps = [_make(simulated_quote=1.0, current_quote=1.001)]
    alerts = await detect_drift(snaps)
    assert alerts == []


@pytest.mark.asyncio
async def test_detect_drift_flags_fee_apr_drop():
    snaps = [_make(fee_apr_baseline=10.0, fee_apr_7d=4.0)]
    alerts = await detect_drift(snaps)
    assert len(alerts) == 1
    assert alerts[0].kind == "fee_apr_drop"
    assert "fell" in alerts[0].rationale.lower()


@pytest.mark.asyncio
async def test_detect_drift_skips_clean_position():
    snaps = [_make(simulated_quote=1.0, current_quote=1.0001)]
    assert await detect_drift(snaps) == []


# ─────────────────────────────────────────────────────────────────────────────
# run_watch_cycle — scan + detect + notify
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_watch_cycle_emits_proposal_per_alert():
    drifted = [
        _make(position_id="pos-oor", out_of_range=True),
        _make(position_id="pos-drift", simulated_quote=1.0, current_quote=1.02),
    ]

    async def src(user_id: int):
        return drifted

    row_ids = await run_watch_cycle(
        user_id=7,
        db=None,                         # in-memory fallback
        position_source=src,
    )
    assert len(row_ids) == 2
    assert all(rid is not None for rid in row_ids)

    pending = get_pending_fallback()
    assert len(pending) == 2
    plan_ids = {p["plan_id"] for p in pending}
    assert plan_ids == {"pos-oor", "pos-drift"}

    titles = {p["title"] for p in pending}
    assert any("out_of_range" in t for t in titles)
    assert any("price_drift" in t for t in titles)


@pytest.mark.asyncio
async def test_run_watch_cycle_noop_when_no_positions():
    async def empty(user_id: int):
        return []

    row_ids = await run_watch_cycle(user_id=7, db=None, position_source=empty)
    assert row_ids == []
    assert get_pending_fallback() == []


@pytest.mark.asyncio
async def test_run_watch_cycle_noop_when_no_drift():
    snaps = [_make(simulated_quote=1.0, current_quote=1.0001)]

    async def src(user_id: int):
        return snaps

    row_ids = await run_watch_cycle(user_id=7, db=None, position_source=src)
    assert row_ids == []
    assert get_pending_fallback() == []


@pytest.mark.asyncio
async def test_drift_alert_dataclass_shape():
    alert = DriftAlert(
        position_id="x",
        user_id=1,
        kind="out_of_range",
        rationale="r",
        drift_bps=0.0,
    )
    assert alert.position_id == "x"
    assert alert.payload == {}
