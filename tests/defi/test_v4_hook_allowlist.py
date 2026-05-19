"""Tests for spec §6a V4 hook allowlist (Shield gate)."""
from __future__ import annotations

from src.shield.v4_hook_allowlist import (
    NO_HOOK,
    describe_hook,
    is_allowed,
    is_no_hook,
    shield_verdict_for_hook,
)


def test_no_hook_address_is_no_hook():
    assert is_no_hook(NO_HOOK)
    assert is_no_hook("0x0000000000000000000000000000000000000000")
    assert is_no_hook(None)
    assert is_no_hook("")


def test_real_hook_address_is_not_no_hook():
    assert not is_no_hook("0x1234567890123456789012345678901234567890")


def test_zero_hook_always_allowed():
    assert is_allowed(NO_HOOK, chain_id=1)
    assert is_allowed(None, chain_id=8453)


def test_unknown_hook_refused_by_default():
    assert not is_allowed("0x1234567890123456789012345678901234567890", chain_id=1)


def test_unknown_hook_admitted_with_explicit_opt_in():
    assert is_allowed(
        "0x1234567890123456789012345678901234567890",
        chain_id=1,
        allow_experimental=True,
    )


def test_describe_hook_returns_none_for_unknown():
    assert describe_hook("0x1234567890123456789012345678901234567890", chain_id=1) is None


def test_shield_verdict_for_no_hook():
    v = shield_verdict_for_hook(None, chain_id=1)
    assert v["allowlist_match"] is True
    assert v["severity"] == "info"


def test_shield_verdict_for_unknown_hook_is_critical():
    v = shield_verdict_for_hook("0x1234567890123456789012345678901234567890", chain_id=1)
    assert v["allowlist_match"] is False
    assert v["severity"] == "critical"
    assert "experimental" in str(v.get("detail", "")).lower()


def test_shield_verdict_headline_includes_address_for_unknown():
    addr = "0xABCDEFabcdef0123456789012345678901234567"
    v = shield_verdict_for_hook(addr, chain_id=1)
    assert addr in str(v["headline"])


# Angstrom + BunniHook were added so the shield gate (adapter-build) and
# the preflight gate (src/data/v4_hooks_allowlist.py) cannot diverge.
_ANGSTROM = "0x0000000aa232009084bd71a5797d089aa4edfad4"
_BUNNI = "0x00001f3b9712708127b1fcad61cb892535951888"


def test_angstrom_allowed_on_mainnet():
    assert is_allowed(_ANGSTROM, chain_id=1)


def test_bunni_hook_allowed_on_mainnet():
    assert is_allowed(_BUNNI, chain_id=1)


def test_angstrom_refused_on_other_chains():
    # Strict per-chain: audited on mainnet does NOT auto-allow on Base.
    assert not is_allowed(_ANGSTROM, chain_id=8453)


def test_describe_hook_returns_audit_url_for_angstrom():
    entry = describe_hook(_ANGSTROM, chain_id=1)
    assert entry is not None
    assert "spearbit" in entry.audit_report.lower()
    assert "MEV-resistant" in entry.properties


def test_shield_and_data_allowlists_stay_in_sync():
    """If shield/_ALLOWLIST and data/V4_HOOKS_ALLOWLIST_BY_CHAIN drift,
    preflight allows what adapter-build refuses (or vice versa) and the
    UX silently 502s. Assert they cover the same (chain_id, addr) set."""
    from src.shield.v4_hook_allowlist import _ALLOWLIST
    from src.data.v4_hooks_allowlist import V4_HOOKS_ALLOWLIST_BY_CHAIN

    shield_keys = {(addr.lower(), int(chain)) for (addr, chain) in _ALLOWLIST}
    data_keys = {(addr.lower(), int(chain)) for (chain, addr) in V4_HOOKS_ALLOWLIST_BY_CHAIN}
    assert shield_keys == data_keys, (
        f"Shield-only: {shield_keys - data_keys}; "
        f"Data-only: {data_keys - shield_keys}"
    )
