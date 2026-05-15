"""Pool Index — daily-refreshed cache of (chain, protocol, pool) tuples.

Replaces the 12-entry hardcoded catalog in
src/agent/tools/execute_pool_position.py:55-95 with a DB-backed
queryable index keyed by (chain, token0, token1, protocol?, fee_tier?).

Spec dev-plan §1.2: weighted_score = 0.4*log(TVL) + 0.3*log(7d_vol) +
0.15*fee_apr + 0.1*pool_age_yrs + 0.05*audit_status.
"""
from src.defi.pool_index.schema import PoolRecord
from src.defi.pool_index.rankings import weighted_score

__all__ = ["PoolRecord", "weighted_score"]
