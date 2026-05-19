"""Spec §9 — Positions watcher.

A single watch cycle does three things:

  1. `scan_positions(user_id)` — pulls every open LP position the user
     holds. EVM positions come from per-protocol subgraphs (The
     Graph); Solana positions come from Helius parsed-instruction
     streams + Birdeye's position API. This module exposes a single
     wallet-assistant bridge call as the v1 implementation; richer
     subgraph wiring is tracked in Phase 4 backlog.

  2. `detect_drift(snapshots)` — applies the spec §13 freshness logic
     (`src.defi.freshness.check_price_drift`) over each position's
     simulated-vs-current quote, plus the §11 D.7 50 bp threshold. The
     output is a list of `DriftAlert` (one per drifted position) ready
     for the optimiser to synthesise a rebalance plan.

  3. `run_watch_cycle(user_id, *, db)` — composes the two and calls
     `notify_proposal` for every drift alert, returning the persisted
     row ids so the caller (cron scheduler, daemon, test harness) can
     log what fired.

This file deliberately keeps the wallet-fetch + subgraph plumbing
behind an injected `position_source` callable so the pin tests can
stub the wallet without spinning up real RPCs.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from src.defi.freshness import check_price_drift
from src.optimizer.notifier import notify_proposal

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data shapes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PositionSnapshot:
    """One LP position as seen by the indexer at scan time."""

    position_id: str
    user_id: int
    protocol: str           # "uniswap_v3", "raydium_clmm", …
    chain_id: int
    token0: str
    token1: str
    fee_bps: int            # 5, 30, 100, …
    liquidity_usd: float
    # Simulated-quote captured when the plan was last accepted; used as
    # the baseline for the drift gate. Zero/missing means "no baseline,
    # re-simulate on next interaction" — never flagged as drifted.
    simulated_quote: float
    current_quote: float
    # For CL positions: true if the current tick has moved outside
    # [tick_lower, tick_upper]. The §9a deep-dive flags this as the
    # primary rebalance trigger.
    out_of_range: bool = False
    # Realised fee APR over the last 7d (subgraph). The detector flags
    # a >50% drop vs the 14d baseline as "fee_apr_drop".
    fee_apr_7d: float = 0.0
    fee_apr_baseline: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DriftAlert:
    """One actionable rebalance signal."""

    position_id: str
    user_id: int
    kind: str           # "out_of_range" | "price_drift" | "fee_apr_drop"
    rationale: str
    drift_bps: float
    payload: dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Position source — wallet-assistant bridge with override hook
# ─────────────────────────────────────────────────────────────────────────────


PositionSource = Callable[[int], Awaitable[list[PositionSnapshot]]]


async def _default_position_source(user_id: int) -> list[PositionSnapshot]:
    """v1 wallet bridge — returns an empty list when no wallet is
    resolvable. Replaced by per-protocol subgraph clients in Phase 4.

    Intentionally never raises: the watcher must keep running even when
    a single user's wallet resolution fails.
    """
    try:
        from src.optimizer.snapshot import snapshot_from_user
    except Exception as exc:  # noqa: BLE001
        logger.debug("positions_watcher: bridge import failed (%s)", exc)
        return []

    # We do not know the user's wallet address from `user_id` alone in
    # this gap-closer; the daemon layer is responsible for passing a
    # custom `position_source` that resolves the address. v1 surface
    # returns an empty list to keep the contract observable.
    _ = snapshot_from_user
    return []


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


async def scan_positions(
    user_id: int,
    *,
    position_source: Optional[PositionSource] = None,
) -> list[PositionSnapshot]:
    """Return every open LP position for `user_id`.

    The default source is a wallet-assistant bridge; tests + the daemon
    inject a richer source that talks to subgraphs / Birdeye.
    """
    src = position_source or _default_position_source
    try:
        positions = await src(user_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "scan_positions: source raised (%s); returning empty list",
            exc,
        )
        return []
    return list(positions)


async def detect_drift(
    snapshots: list[PositionSnapshot],
    *,
    price_threshold_bps: int = 50,
    fee_drop_pct: float = 0.5,
) -> list[DriftAlert]:
    """Run the drift gates over each snapshot and return one alert per
    drifted position.

    Three signals (spec §9 deep-dive + §11 D.7):

      - `out_of_range`: CL position's current tick outside [lo, hi].
      - `price_drift`: `check_price_drift` flagged >50 bps move.
      - `fee_apr_drop`: realised fee APR fell ≥50% vs baseline.
    """
    alerts: list[DriftAlert] = []
    for snap in snapshots:
        # 1. Out-of-range trigger — highest priority, spec §9a.
        if snap.out_of_range:
            alerts.append(
                DriftAlert(
                    position_id=snap.position_id,
                    user_id=snap.user_id,
                    kind="out_of_range",
                    rationale=(
                        f"{snap.protocol} {snap.token0}/{snap.token1} "
                        f"{snap.fee_bps}bp position drifted out of range — "
                        "rebalance to re-enter fee accrual."
                    ),
                    drift_bps=0.0,
                    payload={
                        "protocol": snap.protocol,
                        "chain_id": snap.chain_id,
                        "fee_bps": snap.fee_bps,
                        "liquidity_usd": snap.liquidity_usd,
                    },
                )
            )
            continue

        # 2. Price-drift trigger — spec §11 D.7 50 bp gate.
        if snap.simulated_quote > 0 and snap.current_quote > 0:
            drift = check_price_drift(
                snap.simulated_quote,
                snap.current_quote,
                threshold_bps=price_threshold_bps,
            )
            if drift.breached:
                alerts.append(
                    DriftAlert(
                        position_id=snap.position_id,
                        user_id=snap.user_id,
                        kind="price_drift",
                        rationale=drift.rationale,
                        drift_bps=drift.drift_bps,
                        payload={
                            "protocol": snap.protocol,
                            "chain_id": snap.chain_id,
                            "simulated_quote": snap.simulated_quote,
                            "current_quote": snap.current_quote,
                        },
                    )
                )
                continue

        # 3. Fee-APR drop — only when we have a baseline to compare.
        if snap.fee_apr_baseline > 0:
            ratio = snap.fee_apr_7d / snap.fee_apr_baseline
            if ratio <= (1.0 - fee_drop_pct):
                drop_pct = (1.0 - ratio) * 100.0
                alerts.append(
                    DriftAlert(
                        position_id=snap.position_id,
                        user_id=snap.user_id,
                        kind="fee_apr_drop",
                        rationale=(
                            f"Realised fee APR fell {drop_pct:.0f}% vs "
                            f"baseline ({snap.fee_apr_7d:.2f}% vs "
                            f"{snap.fee_apr_baseline:.2f}%) — consider "
                            "migrating to a higher-APR pool."
                        ),
                        drift_bps=0.0,
                        payload={
                            "protocol": snap.protocol,
                            "chain_id": snap.chain_id,
                            "fee_apr_7d": snap.fee_apr_7d,
                            "fee_apr_baseline": snap.fee_apr_baseline,
                        },
                    )
                )

    return alerts


async def run_watch_cycle(
    user_id: int,
    *,
    db: Any = None,
    position_source: Optional[PositionSource] = None,
    price_threshold_bps: int = 50,
    fee_drop_pct: float = 0.5,
) -> list[Optional[int]]:
    """End-to-end: scan → detect → notify. Returns the list of
    `notify_proposal` row ids (one per emitted alert).
    """
    snapshots = await scan_positions(user_id, position_source=position_source)
    if not snapshots:
        logger.debug("run_watch_cycle: no positions for user_id=%s", user_id)
        return []

    alerts = await detect_drift(
        snapshots,
        price_threshold_bps=price_threshold_bps,
        fee_drop_pct=fee_drop_pct,
    )
    if not alerts:
        logger.debug("run_watch_cycle: no drift for user_id=%s", user_id)
        return []

    row_ids: list[Optional[int]] = []
    for alert in alerts:
        title = f"Rebalance: {alert.kind} on {alert.payload.get('protocol', 'position')}"
        row_id = await notify_proposal(
            user_id=alert.user_id,
            plan_id=alert.position_id,
            title=title,
            db=db,
            payload={
                "kind": alert.kind,
                "rationale": alert.rationale,
                "drift_bps": alert.drift_bps,
                **alert.payload,
            },
        )
        row_ids.append(row_id)

    return row_ids
