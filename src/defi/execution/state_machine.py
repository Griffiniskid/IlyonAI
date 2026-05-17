"""V7-001 — simulated_calldata_hash == broadcast_calldata_hash invariant.

Spec quote: "One Confirm button: produces an artifact hash; the wallet
popup's calldata must hash-match this artifact, or signing is refused.
Enforces simulated_calldata_hash == broadcast_calldata_hash"

This module is the canonical guard between *what we simulated* and *what
the wallet is about to broadcast*. The runtime computes a stable hash of
the unsigned step transaction at simulation time, stamps it onto
`ExecutionStepV3.simulated_calldata_hash`, and on every flip to
`submitted` we compare it against the broadcast payload's hash. A
mismatch raises `CalldataHashMismatchError` so the broadcast is refused
before the wallet popup is invoked.

The hash is intentionally a plain SHA-256 over the canonicalized
calldata blob — not the on-chain tx hash, which would include nonce/gas
and isn't knowable until the wallet signs. This is a *content* hash of
the calldata bytes the user is about to authorize.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


class CalldataHashMismatchError(Exception):
    """Raised when the broadcast calldata diverges from the simulated one.

    Carries both hashes + an optional context dict so observability sinks
    can record the divergence. The runtime catches this at the broadcast
    boundary and surfaces a hard-block error to the UI.
    """

    def __init__(
        self,
        sim_hash: str,
        broadcast_hash: str,
        *,
        step_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.sim_hash = sim_hash
        self.broadcast_hash = broadcast_hash
        self.step_id = step_id
        self.context = context or {}
        super().__init__(
            f"calldata hash mismatch"
            + (f" on step {step_id}" if step_id else "")
            + f": simulated={sim_hash!s} broadcast={broadcast_hash!s} — "
            "refusing to sign (spec V7-001)"
        )


def compute_calldata_hash(payload: Any) -> str:
    """Return a stable SHA-256 hex digest of an unsigned-tx payload.

    Accepts:
      - `UnsignedStepTransaction` (any object exposing `to_dict()`)
      - plain dict
      - raw hex/string calldata (e.g. `0xabcd...`)
      - bytes

    Dicts are JSON-serialized with `sort_keys=True` so field-order
    permutations don't change the hash. Hex strings are normalized to
    lowercase without the `0x` prefix before hashing. The result is a
    64-char lowercase hex string suitable for direct equality
    comparison between simulation and broadcast.
    """
    if payload is None:
        # Empty/none calldata still gets a deterministic hash so the
        # comparison stays total — callers don't need a None-branch.
        return hashlib.sha256(b"").hexdigest()
    if isinstance(payload, bytes):
        return hashlib.sha256(payload).hexdigest()
    if isinstance(payload, str):
        normalized = payload.strip().lower()
        if normalized.startswith("0x"):
            normalized = normalized[2:]
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    # Object-with-to_dict path (UnsignedStepTransaction) — feed the
    # serialized form so we hash the same bytes the wire layer will.
    if hasattr(payload, "to_dict") and callable(payload.to_dict):
        payload = payload.to_dict()
    if isinstance(payload, dict):
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()
    # Fallback — stringify and hash. Better to have a hash than to crash.
    return hashlib.sha256(str(payload).encode("utf-8")).hexdigest()


def assert_calldata_match(
    sim_hash: str,
    broadcast_hash: str,
    *,
    step_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    """Refuse the broadcast when sim and broadcast calldata diverge.

    Both hashes are normalized (lowercased, `0x`-stripped) before
    comparison so wallet implementations that return calldata in mixed
    case don't trigger false mismatches. Empty/None on either side is
    treated as a mismatch — we never silently allow a broadcast that
    wasn't bound to a simulation.
    """
    if not sim_hash or not broadcast_hash:
        raise CalldataHashMismatchError(
            sim_hash or "<empty>",
            broadcast_hash or "<empty>",
            step_id=step_id,
            context=context,
        )
    sim_norm = sim_hash.strip().lower().removeprefix("0x")
    bc_norm = broadcast_hash.strip().lower().removeprefix("0x")
    if sim_norm != bc_norm:
        raise CalldataHashMismatchError(
            sim_hash, broadcast_hash, step_id=step_id, context=context,
        )


__all__ = [
    "CalldataHashMismatchError",
    "assert_calldata_match",
    "compute_calldata_hash",
]
