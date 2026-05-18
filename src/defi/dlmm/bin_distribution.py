"""V7 §1 gap — Meteora DLMM bin distribution shapes (spot / curve / bid-ask).

Each function returns a normalized weight per bin (sums to ~1.0) for a
given active bin and a symmetric span of `range_bins` to either side.
Caller multiplies these weights by the deposit amount to derive per-bin
liquidity. Total bin count returned = 2 * range_bins + 1 (centered on
the active bin).
"""
from __future__ import annotations

import math
from typing import Dict


__all__ = [
    "spot_distribution",
    "curve_distribution",
    "bid_ask_distribution",
]


def _bin_indices(active_bin: int, range_bins: int) -> list[int]:
    if range_bins < 0:
        raise ValueError("range_bins must be >= 0")
    return list(range(active_bin - range_bins, active_bin + range_bins + 1))


def _normalize(weights: dict[int, float]) -> dict[int, float]:
    total = sum(weights.values())
    if total <= 0:
        # Degenerate — uniform fallback.
        n = len(weights) or 1
        return {b: 1.0 / n for b in weights}
    return {b: w / total for b, w in weights.items()}


def spot_distribution(active_bin: int, range_bins: int) -> Dict[int, float]:
    """Uniform weight across the range (Spot strategy)."""
    indices = _bin_indices(active_bin, range_bins)
    if not indices:
        return {}
    w = 1.0 / len(indices)
    return {b: w for b in indices}


def curve_distribution(active_bin: int, range_bins: int) -> Dict[int, float]:
    """Bell-curve weight peaking at active bin (Curve strategy).

    Gaussian-like, ``sigma = max(1.0, range_bins / 2)``.
    """
    indices = _bin_indices(active_bin, range_bins)
    if not indices:
        return {}
    sigma = max(1.0, range_bins / 2.0)
    weights: dict[int, float] = {}
    for b in indices:
        d = (b - active_bin) / sigma
        weights[b] = math.exp(-0.5 * d * d)
    return _normalize(weights)


def bid_ask_distribution(active_bin: int, range_bins: int) -> Dict[int, float]:
    """U-shape — weight grows away from the active bin (Bid-Ask strategy).

    Active bin gets near-zero weight; outer bins get max weight. Useful
    when LP wants exposure to mean-reversion plays.
    """
    indices = _bin_indices(active_bin, range_bins)
    if not indices:
        return {}
    if range_bins == 0:
        return {active_bin: 1.0}
    weights: dict[int, float] = {}
    for b in indices:
        # Linear distance from active bin, normalized to [0, 1]
        d = abs(b - active_bin) / float(range_bins)
        weights[b] = d  # near-zero at center, 1.0 at edges
    # Avoid all-zero center degeneracy by floor.
    if weights.get(active_bin, 0.0) == 0.0:
        weights[active_bin] = 1e-6
    return _normalize(weights)
