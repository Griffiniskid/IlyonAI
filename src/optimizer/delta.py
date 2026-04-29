from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MoveCandidate:
    usd_value: float
    apy_delta: float
    sentinel_delta: int
    estimated_gas_usd: float


def should_move(candidate: MoveCandidate) -> bool:
    annual_benefit = candidate.usd_value * (candidate.apy_delta / 100.0)
    return (
        candidate.apy_delta >= 2.0
        and candidate.sentinel_delta >= 0
        and annual_benefit > 4 * candidate.estimated_gas_usd
    )
