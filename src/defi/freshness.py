"""Spec §11 D.2 — 30-second simulation freshness gate.

Every broadcast must be preceded by a simulation no older than 30s. The
gate is consumed by the Signer Orchestrator: when the user clicks
Confirm more than 30 seconds after the simulation artifact was produced,
re-simulate before broadcasting. Spec §11 invariant 2.

This module ships pure logic — `is_simulation_fresh(simulated_at,
now=None, threshold_s=30)` — plus a typed Result for callers to act on.
The runtime/signer-orchestrator wire-up consumes the Result and either
proceeds or triggers re-simulation.
"""
from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class FreshnessResult:
    is_fresh: bool
    elapsed_s: float
    threshold_s: int
    must_resimulate: bool      # True when stale AND user is about to broadcast
    rationale: str

    def to_dict(self) -> dict:
        return {
            "is_fresh": self.is_fresh,
            "elapsed_s": round(self.elapsed_s, 2),
            "threshold_s": self.threshold_s,
            "must_resimulate": self.must_resimulate,
            "rationale": self.rationale,
        }


def is_simulation_fresh(
    simulated_at: float,
    *,
    now: float | None = None,
    threshold_s: int = 30,
) -> FreshnessResult:
    """Return whether the simulation artifact is still within the
    30-second freshness window. `simulated_at` and `now` are
    POSIX timestamps; `simulated_at` is typically captured when the
    simulator returns its artifact.
    """
    if simulated_at <= 0:
        return FreshnessResult(
            is_fresh=False,
            elapsed_s=0.0,
            threshold_s=threshold_s,
            must_resimulate=True,
            rationale="No simulation timestamp — re-simulate before signing.",
        )
    now_ts = float(now if now is not None else time.time())
    elapsed = max(0.0, now_ts - float(simulated_at))
    fresh = elapsed < threshold_s
    return FreshnessResult(
        is_fresh=fresh,
        elapsed_s=elapsed,
        threshold_s=threshold_s,
        must_resimulate=not fresh,
        rationale=(
            f"Simulation produced {elapsed:.1f}s ago — "
            f"{'within' if fresh else 'past'} {threshold_s}s freshness window. "
            f"{'Safe to broadcast.' if fresh else 'Re-simulate first (spec §11 D.2).'}"
        ),
    )


def assert_fresh_before_broadcast(
    simulated_at: float,
    *,
    now: float | None = None,
    threshold_s: int = 30,
) -> None:
    """Raise ValueError when the simulation is stale and a broadcast
    is about to happen. The signer-orchestrator should call this just
    before submitting calldata; the runtime should catch and re-simulate.
    """
    r = is_simulation_fresh(simulated_at, now=now, threshold_s=threshold_s)
    if r.must_resimulate:
        raise ValueError(
            f"Simulation stale: elapsed={r.elapsed_s:.1f}s > {threshold_s}s. "
            "Refuse to broadcast — re-simulate first."
        )


# ── Spec §11 D.7 — explicit price-drift re-simulation gate ──
#
# D.2 is *time-based* (30s). D.7 is *value-based*: even if a simulation
# is fresh in wall-clock time, the underlying price quote may have moved
# enough between simulate and broadcast to invalidate the slippage cap.
# Spec threshold = 50 bps absolute drift on the headline quote.

@dataclass
class DriftResult:
    drift_bps: float
    threshold_bps: int
    breached: bool
    must_resimulate: bool
    rationale: str

    def to_dict(self) -> dict:
        return {
            "drift_bps": round(self.drift_bps, 2),
            "threshold_bps": self.threshold_bps,
            "breached": self.breached,
            "must_resimulate": self.must_resimulate,
            "rationale": self.rationale,
        }


def check_price_drift(
    simulated_quote: float,
    current_quote: float,
    *,
    threshold_bps: int = 50,
) -> DriftResult:
    """Compare a quote captured at simulate-time with the freshly polled
    quote. Drift in basis points = |Δ / simulated| × 10_000.

    Spec §11 D.7: when drift > 50 bps the plan must be re-simulated before
    the broadcast goes out. This is independent of D.2 freshness — a
    quote can shift 200 bps inside the 30s window during high-volatility
    moments and the user's slippage cap would be silently invalidated.
    """
    if simulated_quote <= 0:
        return DriftResult(
            drift_bps=0.0,
            threshold_bps=threshold_bps,
            breached=True,
            must_resimulate=True,
            rationale="No simulated quote captured — cannot compare; force re-sim.",
        )
    if current_quote <= 0:
        return DriftResult(
            drift_bps=0.0,
            threshold_bps=threshold_bps,
            breached=True,
            must_resimulate=True,
            rationale="No current quote available — cannot compare; force re-sim.",
        )
    delta = abs(current_quote - simulated_quote)
    drift_bps = (delta / float(simulated_quote)) * 10_000.0
    breached = drift_bps > threshold_bps
    return DriftResult(
        drift_bps=drift_bps,
        threshold_bps=threshold_bps,
        breached=breached,
        must_resimulate=breached,
        rationale=(
            f"Price drift {drift_bps:.1f} bps "
            f"({'>' if breached else '≤'} {threshold_bps} bps). "
            f"{'Re-simulate before broadcast (spec §11 D.7).' if breached else 'Safe to broadcast.'}"
        ),
    )


def assert_drift_within_threshold(
    simulated_quote: float,
    current_quote: float,
    *,
    threshold_bps: int = 50,
) -> None:
    """Raise ValueError when the price drift exceeds the spec threshold.
    Signer-orchestrator should call this just before broadcast alongside
    the time-based freshness check.
    """
    r = check_price_drift(simulated_quote, current_quote, threshold_bps=threshold_bps)
    if r.must_resimulate:
        raise ValueError(
            f"Price drift {r.drift_bps:.1f} bps > {threshold_bps} bps. "
            "Refuse to broadcast — re-simulate first."
        )
