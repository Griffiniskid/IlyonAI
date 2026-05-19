"""Spec §9 — Positions Indexer (Phase 4).

Subgraphs per protocol for EVM, Helius parsed-instruction stream +
Birdeye position API for Solana (spec §35). The indexer scans a user's
open LP positions, detects drift (out-of-range CL, fee-APR drop, TVL
exodus, gas-favorable rebalance window), and fans alerts through
`src.optimizer.notifier.notify_proposal`.

Public surface:
    - `scan_positions(user_id, ...)` → list[PositionSnapshot]
    - `detect_drift(snapshots, ...)` → list[DriftAlert]
    - `run_watch_cycle(user_id, *, db, ...)` → list of emitted proposal ids
"""
from __future__ import annotations

from src.indexer.positions_watcher import (  # noqa: F401
    DriftAlert,
    PositionSnapshot,
    detect_drift,
    run_watch_cycle,
    scan_positions,
)

__all__ = [
    "PositionSnapshot",
    "DriftAlert",
    "scan_positions",
    "detect_drift",
    "run_watch_cycle",
]
