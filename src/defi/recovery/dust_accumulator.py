"""Spec §3 / §6f — dust accumulator.

When a position leg ends up worth less than ``DUST_THRESHOLD_USD`` ($1.00)
the runtime emits a ``DUST_BELOW_THRESHOLD`` blocker and the front-end
offers the user three dispositions: SWEEP, LEAVE, or INCREASE_TO_THRESHOLD.

This module exposes:
- ``DUST_THRESHOLD_USD`` — the canonical $1.00 cutoff.
- ``is_dust(usd)`` — strict less-than threshold; treats negative/non-numeric
  feed errors as dust (defensive).
- ``DustPosition`` — per-leg dust descriptor consumed by the disposition
  decision tree.
- ``decide_dust_disposition(positions, sweep_gas_usd=0.50)`` — three-way
  recommendation: SWEEP when aggregate USD exceeds sweep gas, INCREASE
  when a single leg sits at >= half-threshold but the aggregate doesn't
  clear sweep gas, LEAVE otherwise.
- ``build_dust_blocker(positions)`` — wire-shape ``ExecutionBlocker``
  with affected step ids, the recommended disposition embedded in the
  detail string, and the three-way CTA.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Literal, Optional

from src.defi.execution.models import ExecutionBlocker


DUST_THRESHOLD_USD: float = 1.00

# Default per-sweep gas cost — used to decide whether aggregating dust
# legs into a SWEEP makes economic sense. Conservative default; callers
# can override per chain / per gas regime.
DEFAULT_SWEEP_GAS_USD: float = 0.50

# Half the dust threshold — a single leg at or above this floor is close
# enough that a one-shot top-up to clear $1.00 is worth offering.
_HALF_THRESHOLD_USD: float = DUST_THRESHOLD_USD / 2.0

Disposition = Literal["SWEEP", "LEAVE", "INCREASE_TO_THRESHOLD"]


@dataclass
class DustPosition:
    """A single dust leg: a token amount worth less than the threshold.

    ``step_id`` is optional — composed plans may surface dust against a
    snapshotted balance that has no source step (e.g. residual wrapped-SOL
    after a swap unwind). ``chain`` is optional — defaults to empty
    string for callers that don't have chain context.
    """

    token: str
    amount_token: float
    amount_usd: float
    step_id: Optional[str] = None
    chain: str = ""


def is_dust(value: object) -> bool:
    """True when ``value`` represents less than ``DUST_THRESHOLD_USD``.

    Defensive: negative USD = feed error → dust. Non-numeric / NaN strings
    that can't be coerced to float → dust (the alternative is letting a
    bad feed silently route real funds). Float NaN itself returns False
    because NaN comparisons all return False — the test contract accepts
    either outcome there.
    """
    try:
        usd = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return True
    if math.isnan(usd):
        return False
    return usd < DUST_THRESHOLD_USD


def decide_dust_disposition(
    positions: Iterable[DustPosition],
    *,
    sweep_gas_usd: float = DEFAULT_SWEEP_GAS_USD,
) -> Disposition:
    """Recommend SWEEP / LEAVE / INCREASE_TO_THRESHOLD.

    Order of decision:
      1. Empty list → LEAVE (nothing to act on).
      2. Aggregate USD > sweep_gas_usd → SWEEP (worth paying the gas).
      3. Any single position >= half-threshold ($0.50) → INCREASE
         (one quick top-up clears it).
      4. Otherwise → LEAVE (not worth gas, not close enough to top up).

    The half-threshold gate prevents recommending INCREASE for legs so
    small the user would pay more in gas than they'd reclaim.
    """
    pos_list = list(positions)
    if not pos_list:
        return "LEAVE"
    aggregate_usd = sum(p.amount_usd for p in pos_list)
    if aggregate_usd > sweep_gas_usd:
        return "SWEEP"
    if any(p.amount_usd >= _HALF_THRESHOLD_USD for p in pos_list):
        return "INCREASE_TO_THRESHOLD"
    return "LEAVE"


def build_dust_blocker(
    positions: Iterable[DustPosition],
    *,
    sweep_gas_usd: float = DEFAULT_SWEEP_GAS_USD,
    threshold_usd: float = DUST_THRESHOLD_USD,
) -> ExecutionBlocker:
    """Build the canonical ``DUST_BELOW_THRESHOLD`` blocker.

    The wire shape is consumed by the front-end CTA renderer:
      - ``cta`` carries the three dispositions pipe-separated so the
        renderer can mount one button per option.
      - ``detail`` embeds the recommended disposition for the default
        button highlight.
      - ``affected_step_ids`` lets the renderer dim the dust legs in the
        plan view; positions without a ``step_id`` are filtered out (they
        correspond to wallet-residual dust unbound to a step).
    """
    pos_list = list(positions)
    aggregate_usd = sum(p.amount_usd for p in pos_list)
    disposition = decide_dust_disposition(pos_list, sweep_gas_usd=sweep_gas_usd)
    affected = [p.step_id for p in pos_list if p.step_id is not None]
    legs_desc = ", ".join(
        f"{p.amount_token:g} {p.token} (${p.amount_usd:.2f})"
        for p in pos_list
    ) or "no positions"
    detail = (
        f"Aggregate dust ${aggregate_usd:.2f} across {len(pos_list)} leg(s): "
        f"{legs_desc}. Recommended disposition: {disposition}."
    )
    return ExecutionBlocker(
        code="DUST_BELOW_THRESHOLD",
        severity="warning",
        title=f"Dust positions below ${threshold_usd:.2f}",
        detail=detail,
        affected_step_ids=affected,
        recoverable=True,
        cta="SWEEP|LEAVE|INCREASE_TO_THRESHOLD",
    )


__all__ = [
    "DUST_THRESHOLD_USD",
    "DEFAULT_SWEEP_GAS_USD",
    "DustPosition",
    "Disposition",
    "is_dust",
    "decide_dust_disposition",
    "build_dust_blocker",
]
