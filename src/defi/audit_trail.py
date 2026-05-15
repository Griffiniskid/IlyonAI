"""Spec §11 D.8 — cryptographically signed audit trail.

Every prompt-to-tx pair is recorded as {prompt_hash, plan_hash, tx_hash,
timestamp} and HMAC-signed with the server's audit key. The hash chain
makes any retroactive tamper detectable: each entry's hmac depends on
the previous entry's hmac. Verifiers replay the chain to confirm
no entry was inserted, deleted, or modified.

Audit key lives in `settings.audit_trail_hmac_key`. Lost / rotated keys
break verification — surface as a deployment concern in
docs/SECURITY.md.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass


def _sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def hash_prompt(prompt: str) -> str:
    """Sha-256 hex of the raw user prompt."""
    return _sha256_hex(prompt or "")


def hash_plan(plan_dict: dict) -> str:
    """Sha-256 hex of the canonical JSON form of the plan dict.

    Uses sort_keys=True so equivalent plans hash identically regardless
    of dict ordering. Tx data (potentially huge calldata) is included
    so any silent calldata edit is detected.
    """
    canonical = json.dumps(plan_dict or {}, sort_keys=True, default=str, separators=(",", ":"))
    return _sha256_hex(canonical)


@dataclass(frozen=True)
class AuditEntry:
    prompt_hash: str
    plan_hash: str
    tx_hash: str
    timestamp: int        # epoch seconds
    prev_hmac: str        # hmac of previous entry, "0"*64 for genesis
    entry_hmac: str       # hmac chained over (prompt|plan|tx|ts|prev_hmac)

    def to_dict(self) -> dict:
        return {
            "prompt_hash": self.prompt_hash,
            "plan_hash": self.plan_hash,
            "tx_hash": self.tx_hash,
            "timestamp": self.timestamp,
            "prev_hmac": self.prev_hmac,
            "entry_hmac": self.entry_hmac,
        }


def _compute_entry_hmac(
    *,
    key: bytes,
    prompt_hash: str,
    plan_hash: str,
    tx_hash: str,
    timestamp: int,
    prev_hmac: str,
) -> str:
    msg = f"{prompt_hash}|{plan_hash}|{tx_hash}|{timestamp}|{prev_hmac}".encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def sign_audit_entry(
    *,
    key: bytes | str,
    prompt: str,
    plan_dict: dict,
    tx_hash: str,
    prev_hmac: str = "0" * 64,
    timestamp: int | None = None,
) -> AuditEntry:
    """Produce a signed audit entry for a prompt→plan→tx triple.

    `prev_hmac` is the previous entry's entry_hmac; pass "0"*64 for
    the genesis entry. The chain is broken if any entry is modified —
    verify_audit_chain catches it.
    """
    if isinstance(key, str):
        key_b = key.encode("utf-8")
    else:
        key_b = key
    p_h = hash_prompt(prompt)
    plan_h = hash_plan(plan_dict)
    ts = int(timestamp if timestamp is not None else time.time())
    entry_hmac = _compute_entry_hmac(
        key=key_b,
        prompt_hash=p_h,
        plan_hash=plan_h,
        tx_hash=tx_hash,
        timestamp=ts,
        prev_hmac=prev_hmac,
    )
    return AuditEntry(
        prompt_hash=p_h,
        plan_hash=plan_h,
        tx_hash=tx_hash,
        timestamp=ts,
        prev_hmac=prev_hmac,
        entry_hmac=entry_hmac,
    )


def verify_audit_entry(entry: AuditEntry, *, key: bytes | str) -> bool:
    """Re-compute the hmac from the entry's fields + audit key and
    compare. Returns False if any field was tampered or the key
    differs.
    """
    if isinstance(key, str):
        key_b = key.encode("utf-8")
    else:
        key_b = key
    recomputed = _compute_entry_hmac(
        key=key_b,
        prompt_hash=entry.prompt_hash,
        plan_hash=entry.plan_hash,
        tx_hash=entry.tx_hash,
        timestamp=entry.timestamp,
        prev_hmac=entry.prev_hmac,
    )
    return hmac.compare_digest(recomputed, entry.entry_hmac)


def verify_audit_chain(entries: list[AuditEntry], *, key: bytes | str) -> bool:
    """Walk the chain end-to-end. Every entry must verify AND link to
    its predecessor's entry_hmac. Genesis entry's prev_hmac must be
    "0"*64. Returns False on any tamper.
    """
    if not entries:
        return True
    expected_prev = "0" * 64
    for e in entries:
        if e.prev_hmac != expected_prev:
            return False
        if not verify_audit_entry(e, key=key):
            return False
        expected_prev = e.entry_hmac
    return True
