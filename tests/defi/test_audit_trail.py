"""Tests for spec §11 D.8 audit-trail HMAC."""
from __future__ import annotations

from src.defi.audit_trail import (
    AuditEntry,
    hash_plan,
    hash_prompt,
    sign_audit_entry,
    verify_audit_chain,
    verify_audit_entry,
)


_KEY = b"test-audit-key-do-not-use-in-prod"


def test_hash_prompt_deterministic():
    assert hash_prompt("Add 100 USDC to Aave V3") == hash_prompt("Add 100 USDC to Aave V3")
    assert hash_prompt("a") != hash_prompt("b")


def test_hash_plan_sort_invariant():
    a = {"chain": "base", "protocol": "aave-v3", "amount": 100}
    b = {"amount": 100, "protocol": "aave-v3", "chain": "base"}
    assert hash_plan(a) == hash_plan(b)


def test_hash_plan_detects_calldata_change():
    plan = {"steps": [{"data": "0xabcd"}]}
    plan_modified = {"steps": [{"data": "0xabce"}]}
    assert hash_plan(plan) != hash_plan(plan_modified)


def test_sign_then_verify_round_trip():
    entry = sign_audit_entry(
        key=_KEY,
        prompt="Add 100 USDC to Aave V3 on Base",
        plan_dict={"chain": "base", "amount": 100},
        tx_hash="0xdeadbeef",
        timestamp=1700000000,
    )
    assert verify_audit_entry(entry, key=_KEY)


def test_verify_fails_with_wrong_key():
    entry = sign_audit_entry(
        key=_KEY,
        prompt="x",
        plan_dict={},
        tx_hash="0x1",
    )
    assert not verify_audit_entry(entry, key=b"wrong-key")


def test_tampered_tx_hash_fails_verify():
    entry = sign_audit_entry(key=_KEY, prompt="x", plan_dict={}, tx_hash="0x1")
    bad = AuditEntry(
        prompt_hash=entry.prompt_hash,
        plan_hash=entry.plan_hash,
        tx_hash="0xevil",  # tampered
        timestamp=entry.timestamp,
        prev_hmac=entry.prev_hmac,
        entry_hmac=entry.entry_hmac,
    )
    assert not verify_audit_entry(bad, key=_KEY)


def test_chain_verify_full_genesis_to_tail():
    e0 = sign_audit_entry(key=_KEY, prompt="p0", plan_dict={"a": 1}, tx_hash="0x0", timestamp=1)
    e1 = sign_audit_entry(key=_KEY, prompt="p1", plan_dict={"a": 2}, tx_hash="0x1",
                          prev_hmac=e0.entry_hmac, timestamp=2)
    e2 = sign_audit_entry(key=_KEY, prompt="p2", plan_dict={"a": 3}, tx_hash="0x2",
                          prev_hmac=e1.entry_hmac, timestamp=3)
    assert verify_audit_chain([e0, e1, e2], key=_KEY)


def test_chain_rejects_inserted_entry():
    e0 = sign_audit_entry(key=_KEY, prompt="p0", plan_dict={}, tx_hash="0x0", timestamp=1)
    e1 = sign_audit_entry(key=_KEY, prompt="p1", plan_dict={}, tx_hash="0x1",
                          prev_hmac=e0.entry_hmac, timestamp=2)
    rogue = sign_audit_entry(key=_KEY, prompt="rogue", plan_dict={}, tx_hash="0xrogue",
                             prev_hmac="0" * 64, timestamp=99)
    # rogue's prev_hmac doesn't link to e1.entry_hmac.
    assert not verify_audit_chain([e0, e1, rogue], key=_KEY)


def test_chain_rejects_deleted_middle_entry():
    e0 = sign_audit_entry(key=_KEY, prompt="p0", plan_dict={}, tx_hash="0x0", timestamp=1)
    e1 = sign_audit_entry(key=_KEY, prompt="p1", plan_dict={}, tx_hash="0x1",
                          prev_hmac=e0.entry_hmac, timestamp=2)
    e2 = sign_audit_entry(key=_KEY, prompt="p2", plan_dict={}, tx_hash="0x2",
                          prev_hmac=e1.entry_hmac, timestamp=3)
    # Delete e1 — e2.prev_hmac no longer matches e0.entry_hmac.
    assert not verify_audit_chain([e0, e2], key=_KEY)


def test_chain_rejects_modified_plan_in_middle():
    e0 = sign_audit_entry(key=_KEY, prompt="p0", plan_dict={"x": 1}, tx_hash="0x0", timestamp=1)
    e1 = sign_audit_entry(key=_KEY, prompt="p1", plan_dict={"x": 2}, tx_hash="0x1",
                          prev_hmac=e0.entry_hmac, timestamp=2)
    # Tamper e1: change plan_hash. The recomputed entry_hmac won't match.
    tampered = AuditEntry(
        prompt_hash=e1.prompt_hash,
        plan_hash=hash_plan({"x": 999}),  # tampered
        tx_hash=e1.tx_hash,
        timestamp=e1.timestamp,
        prev_hmac=e1.prev_hmac,
        entry_hmac=e1.entry_hmac,  # stale hmac
    )
    assert not verify_audit_chain([e0, tampered], key=_KEY)


def test_empty_chain_verifies():
    assert verify_audit_chain([], key=_KEY)


def test_genesis_entry_prev_hmac_must_be_zero():
    # If first entry's prev_hmac isn't 0*64, chain rejects.
    bad = sign_audit_entry(
        key=_KEY, prompt="p", plan_dict={}, tx_hash="0x1", prev_hmac="ff" * 32,
    )
    assert not verify_audit_chain([bad], key=_KEY)
