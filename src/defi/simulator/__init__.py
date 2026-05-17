"""V7-010 — Tenderly bundle simulator (EVM) + Solana simulateTransaction.

Spec §4 simulator. The simulator stamps `simulated_calldata_hash` on every
`ExecutionStepV3` BEFORE V7-001's mark_step_status('submitted') bind
invariant fires — so the wallet popup can only sign calldata that was
already round-tripped through a fork (EVM) or a `replaceRecentBlockhash`
sim (Solana).

Public surface:
  - `TenderlyClient`              — EVM bundle simulator (REST).
  - `simulate_transaction`        — Solana RPC `simulateTransaction`.
  - `SimulationResult`            — unified dataclass (success/gas/error).
  - `simulate_step`               — chain-kind dispatcher used by broadcast.
"""
from __future__ import annotations

from src.defi.simulator.solana_simulator import simulate_transaction
from src.defi.simulator.tenderly_client import (
    SimulationResult,
    TenderlyClient,
)

__all__ = [
    "SimulationResult",
    "TenderlyClient",
    "simulate_transaction",
]
