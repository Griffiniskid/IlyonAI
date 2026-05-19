"""Spec §6c — unified async-fill PendingPrimitive.

Cross-chain composed plans and time-locked single-chain protocols both
emit steps that cannot complete in the same broadcast as the user's
signature: a deBridge DLN solver fills the destination leg asynchronously,
Pendle V2 entries land on the next epoch boundary, Lido withdrawals sit
in a queue for hours, Solana confirmations need a few seconds of cluster
finality. This module gives the runtime a single typed wire shape for
all four classes so the front-end watch-strategy router + receipt watcher
can share one renderer.

A pending primitive describes:
  - which kind of async fill we're waiting for,
  - roughly how long it should take (front-end uses this for a progress
    ETA),
  - whether to wait via webhook callback, RPC poll, or both,
  - optional webhook URL + RPC check-function locator for the watcher.

The primitive's ``as_blocker_payload()`` produces a JSON-serializable dict
keyed by a stable schema — adding a key requires updating
``test_as_blocker_payload_keys_are_stable``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


PendingKind = Literal[
    "DEBRIDGE_FILL",
    "PENDLE_EPOCH",
    "LIDO_QUEUE",
    "SOLANA_CONFIRMATION",
]

WatchStrategy = Literal["webhook", "rpc_poll", "both"]


_KIND_TO_BLOCKER_CODE: dict[str, str] = {
    "DEBRIDGE_FILL": "PENDING_DST_FILL",
    "PENDLE_EPOCH": "PENDING_EPOCH_ENTRY",
    "LIDO_QUEUE": "PENDING_LIDO_QUEUE",
    "SOLANA_CONFIRMATION": "PENDING_SOLANA_CONFIRMATION",
}


@dataclass(frozen=True)
class PendingPrimitive:
    """A typed descriptor for an async-fill step the runtime will watch.

    Frozen so callers can't mutate after constructing — the watch loop
    snapshots these into blocker payloads and any later mutation would
    silently desync the UI from the watcher.
    """

    kind: PendingKind
    expected_resolve_ms: int
    watch_strategy: WatchStrategy
    webhook_url: Optional[str] = None
    rpc_check_fn_name: Optional[str] = None

    def as_blocker_payload(self) -> dict:
        """Serialize to the wire shape consumed by the blocker renderer.

        The key set is locked by ``test_as_blocker_payload_keys_are_stable``;
        any addition must update that test in lockstep. ``code`` is derived
        from ``kind`` via the canonical KNOWN_BLOCKER_CODES mapping so
        downstream normalization accepts the blocker without warning.
        """
        return {
            "code": _KIND_TO_BLOCKER_CODE[self.kind],
            "kind": self.kind,
            "expected_resolve_ms": self.expected_resolve_ms,
            "watch_strategy": self.watch_strategy,
            "webhook_url": self.webhook_url,
            "rpc_check_fn_name": self.rpc_check_fn_name,
        }


# ──────────────────────────────────────────────────────────────────────────
# Per-kind factories with sensible defaults — callers use these instead of
# hand-constructing PendingPrimitive so future timeout/strategy revisions
# happen in one place.
# ──────────────────────────────────────────────────────────────────────────


def debridge_fill(
    *,
    webhook_url: Optional[str] = None,
    rpc_check_fn_name: Optional[str] = (
        "src.routing.debridge_client.DeBridgeBridge.status"
    ),
    expected_resolve_ms: int = 300_000,  # ~5 minutes typical solver fill
) -> PendingPrimitive:
    """Pending primitive for a deBridge DLN destination-chain fill."""
    return PendingPrimitive(
        kind="DEBRIDGE_FILL",
        expected_resolve_ms=expected_resolve_ms,
        watch_strategy="both" if webhook_url else "rpc_poll",
        webhook_url=webhook_url,
        rpc_check_fn_name=rpc_check_fn_name,
    )


def pendle_epoch(
    *,
    expected_resolve_ms: int = 86_400_000,  # 24 h — Pendle epoch length
) -> PendingPrimitive:
    """Pending primitive for a Pendle V2 epoch boundary entry."""
    return PendingPrimitive(
        kind="PENDLE_EPOCH",
        expected_resolve_ms=expected_resolve_ms,
        watch_strategy="rpc_poll",
    )


def lido_queue(
    *,
    rpc_check_fn_name: Optional[str] = None,
    expected_resolve_ms: int = 7_200_000,  # ~2 h typical Lido withdrawal
) -> PendingPrimitive:
    """Pending primitive for a Lido stETH→ETH withdrawal queue position."""
    return PendingPrimitive(
        kind="LIDO_QUEUE",
        expected_resolve_ms=expected_resolve_ms,
        watch_strategy="rpc_poll",
        rpc_check_fn_name=rpc_check_fn_name,
    )


def solana_confirmation(
    *,
    expected_resolve_ms: int = 30_000,  # ~30 s for confirmed commitment
) -> PendingPrimitive:
    """Pending primitive for a Solana tx awaiting `confirmed` commitment."""
    return PendingPrimitive(
        kind="SOLANA_CONFIRMATION",
        expected_resolve_ms=expected_resolve_ms,
        watch_strategy="rpc_poll",
    )


__all__ = [
    "PendingPrimitive",
    "PendingKind",
    "WatchStrategy",
    "debridge_fill",
    "pendle_epoch",
    "lido_queue",
    "solana_confirmation",
]
