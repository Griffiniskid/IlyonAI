"""Pool Index ranking score — dev-plan §1.2.

  weighted_score = 0.4*log(TVL) + 0.3*log(7d_vol) + 0.15*fee_apr_30d
                 + 0.1*pool_age_yrs + 0.05*audit_status

Higher = better. Pools are ranked descending. Shield-blocked pools
should be filtered out BEFORE ranking, not scored low.
"""
from __future__ import annotations

import math
from decimal import Decimal

from src.defi.pool_index.schema import PoolRecord


_AUDIT_STATUS_SCORE: dict[str, float] = {
    "audited": 1.0,
    "audit_pending": 0.5,
    "unaudited": 0.1,
    "blocked": 0.0,
}


def _safe_log(x: Decimal | float | None, *, floor: float = 1.0) -> float:
    """log(max(x, floor)) — clamp to floor so log never blows up on
    zero / negative / null. Floor=1 means log(0|None) = 0."""
    v = float(x or 0.0)
    if v <= 0:
        v = floor
    return math.log(max(v, floor))


def weighted_score(p: PoolRecord) -> float:
    """Compute the dev-plan ranking score for a single PoolRecord."""
    tvl = _safe_log(p.tvl_usd)
    vol = _safe_log(p.volume_7d_usd)
    fee_apr = float(p.fee_apr_30d or 0.0)
    age_yrs = float(p.pool_age_days or 0) / 365.0
    audit = _AUDIT_STATUS_SCORE.get((p.audit_status or "").lower(), 0.3)
    return (
        0.4 * tvl
        + 0.3 * vol
        + 0.15 * fee_apr
        + 0.10 * age_yrs
        + 0.05 * audit
    )


def rank_pools(pools: list[PoolRecord]) -> list[PoolRecord]:
    """Return `pools` sorted by weighted_score descending. Skip
    Shield-blocked entries — caller filters those out, but defensive."""
    return sorted(
        (p for p in pools if (p.shield_status or "allowed") != "blocked"),
        key=weighted_score,
        reverse=True,
    )
