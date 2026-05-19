"""Spec §1 invariant 5 — critical session-key limits mirrored on-chain.

After the user signs the on-chain installation tx for a session-key policy,
the runtime MUST verify that what landed on-chain matches the off-chain
proposal that was shown to the user. Drift → block.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class SessionKeyPolicy:
    key_address: str
    daily_limit_usd: Optional[Decimal] = None
    expires_at: int = 0  # unix seconds
    allowed_contracts: tuple[str, ...] = field(default_factory=tuple)
    allowed_selectors: tuple[str, ...] = field(default_factory=tuple)  # hex 0xXXXXXXXX


@dataclass(frozen=True)
class MirrorVerdict:
    matches: bool
    drift_fields: tuple[str, ...]  # which fields differ
    reason: str
    onchain_policy: Optional[SessionKeyPolicy] = None


async def fetch_onchain_policy(
    account_address: str,
    session_key: str,
    chain_id: int,
    aa_kind: str,  # "biconomy_nexus" | "zerodev_kernel"
    rpc_client,
) -> Optional[SessionKeyPolicy]:
    """Read on-chain policy via aa_kind-specific getter.

    Stub: returns None when getter not available.
    Real implementations should query:
    - Biconomy Nexus: `getInstalledPolicies(session_key)` selector keccak("getInstalledPolicies(address)")[:4]
    - ZeroDev Kernel: `policyOf(session_key)` selector keccak("policyOf(address)")[:4]
    """
    # STUB: real selector verification + ABI decode requires verified contract ABIs.
    # Mark stub-mode so callers can branch on a known-unsupported chain × kind.
    return None


def compare_policies(
    expected: SessionKeyPolicy,
    onchain: Optional[SessionKeyPolicy],
) -> MirrorVerdict:
    """Compare off-chain expected vs on-chain reading. Field-by-field drift."""
    if onchain is None:
        return MirrorVerdict(
            matches=False,
            drift_fields=("onchain_unavailable",),
            reason="On-chain policy getter not available for this AA kind / chain — install pending or stub mode.",
            onchain_policy=None,
        )
    drift = []
    if expected.key_address.lower() != onchain.key_address.lower():
        drift.append("key_address")
    if expected.daily_limit_usd != onchain.daily_limit_usd:
        drift.append("daily_limit_usd")
    if expected.expires_at != onchain.expires_at:
        drift.append("expires_at")
    if tuple(c.lower() for c in expected.allowed_contracts) != tuple(c.lower() for c in onchain.allowed_contracts):
        drift.append("allowed_contracts")
    if tuple(s.lower() for s in expected.allowed_selectors) != tuple(s.lower() for s in onchain.allowed_selectors):
        drift.append("allowed_selectors")
    if not drift:
        return MirrorVerdict(matches=True, drift_fields=(), reason="All fields match.", onchain_policy=onchain)
    return MirrorVerdict(
        matches=False,
        drift_fields=tuple(drift),
        reason=f"Drift in: {', '.join(drift)}.",
        onchain_policy=onchain,
    )


async def assert_onchain_mirrors(
    account_address: str,
    expected: SessionKeyPolicy,
    chain_id: int,
    aa_kind: str,
    rpc_client,
) -> MirrorVerdict:
    """Public entry point. Always returns a verdict — caller must check `.matches`."""
    onchain = await fetch_onchain_policy(
        account_address, expected.key_address, chain_id, aa_kind, rpc_client
    )
    return compare_policies(expected, onchain)


def build_mirror_drift_blocker(verdict: MirrorVerdict) -> dict:
    """Emit SESSION_KEY_MIRROR_DRIFT blocker when verdict.matches is False."""
    return {
        "code": "SESSION_KEY_MIRROR_DRIFT",
        "severity": "blocker",
        "title": "Session-key on-chain mirror failed",
        "detail": verdict.reason,
        "drift_fields": list(verdict.drift_fields),
        "affected_step_ids": [],
        "recommended_action": (
            "Re-install the session-key policy on-chain or revoke and retry. "
            "Off-chain proposal must match on-chain state before proceeding."
        ),
    }
