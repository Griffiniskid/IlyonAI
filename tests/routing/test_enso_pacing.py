"""Pin test: Enso global pacing interval.

Spec §A.1 mandates `_MIN_INTERVAL_S = 1.15`. Free-tier Enso allows 1 req/s;
1.15s adds a 150 ms cushion to absorb clock drift / network jitter without
tripping the 429 ratelimiter. Any deviation (e.g. the prior 1.6s value) burns
through Enso budget per-conversation and slows multi-turn flows for no
ratelimit-safety gain.

If this test fails, the cap was tweaked without spec update — revert the
constant before merging.
"""
from __future__ import annotations

from src.routing import enso_client


def test_enso_min_interval_is_1_15() -> None:
    assert enso_client._MIN_INTERVAL_S == 1.15, (
        f"Enso pacing must be 1.15s per spec §A.1, "
        f"got {enso_client._MIN_INTERVAL_S}"
    )
