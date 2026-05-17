"""Slippage budget splitter for multi-leg execution.

Spec ref: §3 — total slippage budget split across legs so heavier-impact legs
(LP-add, bridge) get a larger share than simple swaps. Allocations are integer
basis points (bps) that sum exactly to the input total.

Example:
    >>> split_slippage(50, ["swap", "swap", "lp_add"])
    [14, 14, 22]  # sums to 50, lp_add ≥ swap

    >>> split_slippage(60, ["swap", "swap"])
    [30, 30]
"""

from __future__ import annotations

# Per-leg weight multipliers. Heavier-impact legs (LP-add, bridge) get a
# larger share of the total slippage budget. Unknown leg kinds default to 1.0
# (treated like a plain swap).
LEG_WEIGHTS: dict[str, float] = {
    "swap": 1.0,
    "bridge": 1.5,
    "lp_add": 1.3,
    "lp_increase": 1.3,
    "stake": 0.5,
    "supply": 0.5,
}


def split_slippage(total_bps: int, leg_kinds: list[str]) -> list[int]:
    """Split a total slippage budget across legs proportional to LEG_WEIGHTS.

    Args:
        total_bps: Total slippage budget in basis points (e.g. 50 = 0.50%).
        leg_kinds: Ordered list of leg kind strings (e.g. ["swap", "lp_add"]).

    Returns:
        List of integer bps allocations, same length as ``leg_kinds``, summing
        exactly to ``total_bps``. Any rounding remainder is distributed by
        adding 1 bp at a time to legs in descending weight order (ties broken
        by earlier position).

    Raises:
        ValueError: If ``leg_kinds`` is empty.
    """
    if not leg_kinds:
        raise ValueError("leg_kinds must not be empty")

    weights = [LEG_WEIGHTS.get(kind, 1.0) for kind in leg_kinds]
    sum_weights = sum(weights)
    if sum_weights <= 0:
        # Degenerate: all weights are zero. Fall back to equal split.
        weights = [1.0] * len(leg_kinds)
        sum_weights = float(len(leg_kinds))

    # Initial proportional allocation, rounded down to preserve budget.
    allocations = [int(total_bps * w / sum_weights) for w in weights]
    remainder = total_bps - sum(allocations)

    # Distribute remainder bp-by-bp to legs with the largest weight first
    # (stable order: earlier index wins ties).
    if remainder > 0:
        order = sorted(
            range(len(weights)),
            key=lambda i: (-weights[i], i),
        )
        for i in range(remainder):
            allocations[order[i % len(order)]] += 1
    elif remainder < 0:
        # Over-allocated (only possible with negative total or rounding edge);
        # peel back from the smallest-weight legs first.
        order = sorted(
            range(len(weights)),
            key=lambda i: (weights[i], i),
        )
        for i in range(-remainder):
            allocations[order[i % len(order)]] -= 1

    return allocations


def validate_split(
    allocations: list[int],
    total_bps: int,
    min_per_leg: int = 5,
) -> bool:
    """Validate that a split allocation is well-formed.

    Args:
        allocations: Per-leg bps allocations as returned by ``split_slippage``.
        total_bps: Expected total to match.
        min_per_leg: Minimum acceptable bps for any single leg (default 5 bps =
            0.05%). Used to reject splits where a leg is so small it would
            almost certainly revert at execution.

    Returns:
        True iff allocations sum to ``total_bps`` and every leg ≥ ``min_per_leg``.
    """
    if not allocations:
        return False
    if sum(allocations) != total_bps:
        return False
    if any(a < min_per_leg for a in allocations):
        return False
    return True
