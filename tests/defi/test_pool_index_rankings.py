"""Tests for Pool Index ranking score (dev-plan §1.2)."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from src.defi.pool_index import PoolRecord, weighted_score
from src.defi.pool_index.rankings import rank_pools


def _pool(**overrides) -> PoolRecord:
    base = dict(
        pool_id="p", chain_id=1, protocol="uniswap-v3",
        protocol_version="v3",
        pool_address="0x0", pool_key_hash=None, pool_pubkey=None,
        token0_address="0xa", token1_address="0xb", token2_address=None,
        fee_bps=500, tick_spacing=10, bin_step_bps=None, hooks_address=None,
        tvl_usd=Decimal(1_000_000), volume_7d_usd=Decimal(100_000),
        fee_apr_30d=10.0, reward_apr_30d=0.0,
        pool_age_days=365, audit_status="audited",
        shield_status="allowed",
        last_refreshed=datetime.now(timezone.utc),
    )
    base.update(overrides)
    return PoolRecord(**base)


def test_high_tvl_pool_ranks_above_low_tvl_pool():
    big = _pool(pool_id="big", tvl_usd=Decimal(100_000_000), volume_7d_usd=Decimal(10_000_000))
    small = _pool(pool_id="small", tvl_usd=Decimal(10_000), volume_7d_usd=Decimal(1_000))
    assert weighted_score(big) > weighted_score(small)


def test_higher_apr_breaks_tie_when_tvl_matches():
    low_apr = _pool(pool_id="low", fee_apr_30d=2.0)
    high_apr = _pool(pool_id="high", fee_apr_30d=20.0)
    assert weighted_score(high_apr) > weighted_score(low_apr)


def test_audited_beats_unaudited_when_else_equal():
    audited = _pool(pool_id="aud", audit_status="audited")
    unaudited = _pool(pool_id="unaud", audit_status="unaudited")
    assert weighted_score(audited) > weighted_score(unaudited)


def test_zero_tvl_doesnt_crash_with_log():
    p = _pool(pool_id="empty", tvl_usd=Decimal(0), volume_7d_usd=None)
    s = weighted_score(p)
    # log(0|None) clamps to 0 — score should be finite and small.
    assert s >= 0
    assert s < 100


def test_rank_pools_filters_shield_blocked():
    ok = _pool(pool_id="ok", shield_status="allowed")
    blocked = _pool(pool_id="blocked", shield_status="blocked", tvl_usd=Decimal(10**12))  # high TVL but blocked
    ranked = rank_pools([ok, blocked])
    assert blocked not in ranked
    assert ranked == [ok]


def test_rank_pools_sorts_descending():
    a = _pool(pool_id="a", tvl_usd=Decimal(1_000_000), volume_7d_usd=Decimal(10_000))
    b = _pool(pool_id="b", tvl_usd=Decimal(100_000_000), volume_7d_usd=Decimal(10_000_000))
    c = _pool(pool_id="c", tvl_usd=Decimal(50_000_000), volume_7d_usd=Decimal(5_000_000))
    ranked = rank_pools([a, b, c])
    assert [p.pool_id for p in ranked] == ["b", "c", "a"]


def test_total_apr_property():
    p = _pool(fee_apr_30d=12.0, reward_apr_30d=8.5)
    assert p.total_apr == 20.5


def test_is_clmm_property():
    v3 = _pool(protocol_version="v3", tick_spacing=10)
    v4 = _pool(protocol_version="v4", tick_spacing=60)
    v2 = _pool(protocol_version=None, tick_spacing=None, bin_step_bps=None)
    dlmm = _pool(protocol_version="dlmm", tick_spacing=None, bin_step_bps=20)
    assert v3.is_clmm
    assert v4.is_clmm
    assert not v2.is_clmm
    assert not dlmm.is_clmm  # dlmm is its own category, not clmm


def test_is_dlmm_property():
    p = _pool(protocol_version="dlmm", bin_step_bps=20)
    assert p.is_dlmm
