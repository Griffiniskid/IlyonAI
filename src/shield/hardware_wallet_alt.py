"""Spec §13 Row 15 — Hardware-wallet Solana v0 ALT preflight.

Solana's versioned transactions (v0) compress account references via an
Address Lookup Table (ALT). Ledger firmware up through the current
``Solana app v1.x`` does NOT parse v0 messages — it only signs legacy
(message v0-less) transactions. Signing a v0+ALT tx on a Ledger today
either errors out at the wallet layer or, worse, surfaces a blind-signing
prompt the user can't verify.

This module emits the ``LEDGER_NO_ALT_SUPPORT`` blocker whenever a plan
step requires an ALT *and* the wallet meta declares the connected wallet
as a hardware device (Ledger / Trezor). Frontend supplies ``wallet_meta``
via the wallet capabilities probe (``window.solana.isLedger`` or the
WalletConnect ``hardware`` flag).

Fail-soft: missing wallet_meta or non-Solana steps return clean.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

from src.defi.execution.models import ExecutionBlocker, ExecutionStepV3

logger = logging.getLogger(__name__)

# Canonical blocker code surfaced to the execution layer. Pinned here so
# the preflight wiring and the test suite agree on the spelling.
LEDGER_NO_ALT_BLOCKER_CODE: str = "LEDGER_NO_ALT_SUPPORT"

# Wallet kinds known to refuse Solana v0 ALT messages. Lower-cased for
# case-insensitive matching against `wallet_meta["kind"]`.
_HW_WALLET_KINDS: frozenset[str] = frozenset({
    "ledger",
    "trezor",
    "keystone",  # Keystone QR-signer also lacks v0 support in current fw
})


def _step_requires_alt(step: ExecutionStepV3) -> bool:
    """True when the step's unsigned tx needs an Address Lookup Table.

    Honors (in order):
      1. ``step.transaction.requires_alt`` — adapter-stamped attribute
      2. ``step.receipt["requires_alt"]`` — sidecar/runtime injection
    """
    tx = step.transaction
    if tx is not None:
        flag = getattr(tx, "requires_alt", None)
        if flag is not None:
            return bool(flag)
    if step.receipt and isinstance(step.receipt, dict):
        flag = step.receipt.get("requires_alt")
        if flag is not None:
            return bool(flag)
    return False


def evaluate_hardware_wallet_alt_preflight(
    steps: Iterable[ExecutionStepV3],
    wallet_meta: dict[str, Any] | None,
) -> list[ExecutionBlocker]:
    """Emit ``LEDGER_NO_ALT_SUPPORT`` when a hw-wallet meets an ALT step.

    Returns an empty list when:
      * ``wallet_meta`` is None or missing the ``kind`` field
      * the wallet is not a known hardware kind
      * no step in the plan requires an ALT
      * step's chain is not Solana (ALTs are a Solana primitive)
    """
    if not wallet_meta or not isinstance(wallet_meta, dict):
        return []
    kind = str(wallet_meta.get("kind") or "").strip().lower()
    if kind not in _HW_WALLET_KINDS:
        return []

    affected: list[str] = []
    for step in steps:
        chain = (step.chain or "").strip().lower()
        if chain not in {"solana", "sol"}:
            # ALTs are Solana-only; non-Solana steps are clean even on hw.
            continue
        if _step_requires_alt(step):
            affected.append(step.step_id)

    if not affected:
        return []

    return [ExecutionBlocker(
        code=LEDGER_NO_ALT_BLOCKER_CODE,
        severity="blocker",
        title="Hardware wallet cannot sign Solana v0 ALT transactions",
        detail=(
            f"The connected {kind.title()} device does not support "
            "Solana v0 (versioned) transactions with Address Lookup "
            "Tables. One or more steps in this plan require ALT "
            "compression to fit under the per-tx account limit. "
            "Switch to a software wallet (Phantom, Solflare, Backpack) "
            "for this plan, or wait for a Ledger Solana app update "
            "that adds v0 message parsing."
        ),
        affected_step_ids=affected,
        recoverable=True,
        cta="Connect a software wallet, or ask the planner to rebuild without ALT compression.",
    )]
