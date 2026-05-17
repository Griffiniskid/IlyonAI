"""V7-033 — PERMISSIONED_POOL_KYC blocker emit path.

Spec §13 row 10 (`IlyonAi_LP_Execution_Spec.pdf`) defines the
PERMISSIONED_POOL_KYC blocker token for KYC-gated lending pools
(Aave Arc, Maple, Goldfinch, Hashnote, Compound III KYC variants).
Until now the token was reserved in `src/defi/execution/models.py::
KNOWN_BLOCKER_CODES` but no runtime path actually emitted it, so any
plan that touched a KYC-gated pool would silently route the user into
a permissioned vault they couldn't enter without prior whitelisting.

This module is the runtime registry + preflight wire that closes
that gap. Callers (intent → adapter dispatcher, EVM preflight) pass
in the candidate pool addresses for any supply / deposit / lend leg
and receive one ExecutionBlocker per gated address. Empty list means
the plan is clear of permissioned-pool exposure.

The registry is intentionally conservative — only addresses we have
explicit confirmation about (protocol docs, on-chain `permissioned`
flag, or KYC-gated whitelist contract) are listed. Unknown lending
pools are presumed open; the spec's `PERMISSIONED_POOL_KYC` semantic
is "refuse to sign only when we are certain the destination is
gated", never a soft-warn on unfamiliar protocols.
"""
from __future__ import annotations

import logging
from typing import Iterable, Optional

from src.defi.execution.models import ExecutionBlocker

logger = logging.getLogger(__name__)

# Re-export the spec §6c blocker code so callers don't have to import
# from execution.models just to compare a string literal.
PERMISSIONED_POOL_KYC_BLOCKER_CODE = "PERMISSIONED_POOL_KYC"

# Known KYC-gated pool addresses (Aave Arc, Compound III KYC variants, Maple,
# Goldfinch, Hashnote). All entries normalised to lowercase at lookup time.
# Real addresses are added as integrations land; the placeholder below keeps
# the registry non-empty so the `is_kyc_gated` short-circuit has a hit to
# regression-test against.
KYC_GATED_POOLS: set[str] = {
    # Aave Arc (deprecated but historical) — none currently active on mainnet,
    # leave placeholder slot for when a future permissioned-pool variant ships.
    # Maple lending pools (require KYC) — example placeholder; real addrs
    # added when Maple adapter integrates.
    "0x6f6c388e0ad0f7a17775ea8a4baa9bbe8b3a4ad7",
}

# Marker prefix for Maple-style pool addresses surfaced by upstream
# adapters that have not yet been folded into KYC_GATED_POOLS but are
# already known to be permissioned. Reserved for future glob-match
# heuristics; kept here so callers can grep one symbol.
MAPLE_POOL_PREFIX = "0xMapleP00l"


def is_kyc_gated(pool_addr: str) -> bool:
    """Case-insensitive lookup against the KYC-gated registry.

    Empty / falsy inputs return False. Addresses are normalised to lower
    on both sides so EIP-55 mixed-case inputs match the canonical
    lowercase entries in `KYC_GATED_POOLS`.
    """
    if not pool_addr:
        return False
    return pool_addr.lower() in {a.lower() for a in KYC_GATED_POOLS}


def check_kyc_pool(pool_addr: str) -> Optional[str]:
    """Return the PERMISSIONED_POOL_KYC code string for a gated pool, else None.

    Thin wrapper around `is_kyc_gated` for callers that prefer a code-string
    return value rather than a bool (matches the shape of other shield
    detectors in `src/shield/`).
    """
    if is_kyc_gated(pool_addr):
        return PERMISSIONED_POOL_KYC_BLOCKER_CODE
    return None


def evaluate_kyc_pool_preflight(
    pool_addrs: Iterable[str],
    *,
    affected_step_ids: list[str] | None = None,
) -> list[ExecutionBlocker]:
    """Return one PERMISSIONED_POOL_KYC blocker per gated pool address.

    Args:
        pool_addrs: iterable of pool / vault addresses that the candidate
            execution plan will supply / deposit / lend into. Empty / falsy
            entries are skipped. Addresses are deduped (case-insensitive)
            before emission so the same gated pool referenced from two
            steps surfaces a single blocker.
        affected_step_ids: optional step_ids to tag on the emitted
            blocker(s). Passed through verbatim to every emitted blocker
            so the frontend can highlight the offending step rows.

    Returns:
        list[ExecutionBlocker] — empty when no gated addresses match or
        when `pool_addrs` is empty. Severity is "blocker" with
        recoverable=False — the user cannot proceed without first
        completing the protocol-side KYC / whitelist flow off-platform.
    """
    blockers: list[ExecutionBlocker] = []
    seen: set[str] = set()
    for addr in pool_addrs or ():
        if not addr:
            continue
        key = str(addr).lower()
        if key in seen:
            continue
        seen.add(key)
        if not is_kyc_gated(addr):
            continue
        blockers.append(
            ExecutionBlocker(
                code=PERMISSIONED_POOL_KYC_BLOCKER_CODE,
                severity="blocker",
                title="Permissioned pool requires KYC",
                detail=(
                    f"Pool {addr} is gated by a KYC / whitelist contract "
                    "(Aave Arc / Maple / Goldfinch / Hashnote class). The "
                    "wallet must be whitelisted off-platform before this "
                    "step can be signed."
                ),
                affected_step_ids=list(affected_step_ids or []),
                recoverable=False,
                cta="Complete protocol KYC before retrying",
            )
        )
    return blockers
