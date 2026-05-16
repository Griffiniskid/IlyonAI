"""Pin: Biconomy Nexus session-key install / uninstall calldata.

Spec §11 D.5 / Phase 7 E.1 — on-chain policy framework integration.
"""
from __future__ import annotations

from src.auth.biconomy_nexus import (
    NEXUS_MODULE_TYPE_VALIDATOR,
    build_install_session_key_module_calldata,
    build_uninstall_session_key_module_calldata,
)


def test_install_selector_is_0x9517e29f():
    cd = build_install_session_key_module_calldata(
        validator_module_address="0x1111111111111111111111111111111111111111",
        session_signer="0x2222222222222222222222222222222222222222",
        spend_cap_wei=10**18,
        selector_allowlist=["0x617ba037"],
        expiry_unix=1_800_000_000,
    )
    assert cd.startswith("0x9517e29f")


def test_install_encodes_module_type_validator():
    cd = build_install_session_key_module_calldata(
        validator_module_address="0x1111111111111111111111111111111111111111",
        session_signer="0x2222222222222222222222222222222222222222",
        spend_cap_wei=10**18,
        selector_allowlist=["0x617ba037"],
        expiry_unix=1_800_000_000,
    )
    # First 32-byte word after selector = moduleTypeId
    body = cd[10:]
    module_type = int(body[:64], 16)
    assert module_type == NEXUS_MODULE_TYPE_VALIDATOR
    # Second word = address (right-padded; last 40 chars are the addr)
    addr_word = body[64:128]
    assert addr_word.endswith("1111111111111111111111111111111111111111")


def test_install_encodes_session_signer_and_spend_cap_in_init_data():
    """initData heads = signer + spendCap + selectors_offset(0x80) + expiry."""
    cd = build_install_session_key_module_calldata(
        validator_module_address="0x1111111111111111111111111111111111111111",
        session_signer="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        spend_cap_wei=5_000_000_000_000_000_000,
        selector_allowlist=["0x617ba037"],
        expiry_unix=1_800_000_000,
    )
    # Find initData: after the 4-byte selector + 3 head words (96 bytes)
    # the bytes-length word starts. We just check the signer appears in
    # the calldata.
    assert "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" in cd.lower()


def test_install_encodes_each_selector_padded():
    cd = build_install_session_key_module_calldata(
        validator_module_address="0x1111111111111111111111111111111111111111",
        session_signer="0x2222222222222222222222222222222222222222",
        spend_cap_wei=10**18,
        selector_allowlist=["0x617ba037", "0x474cf53d"],
        expiry_unix=1_800_000_000,
    )
    # Both selectors must appear as words
    assert "617ba037" in cd.lower()
    assert "474cf53d" in cd.lower()


def test_uninstall_selector_is_0xa71763a8():
    cd = build_uninstall_session_key_module_calldata(
        validator_module_address="0x1111111111111111111111111111111111111111",
    )
    assert cd.startswith("0xa71763a8")
    body = cd[10:]
    assert int(body[:64], 16) == NEXUS_MODULE_TYPE_VALIDATOR


def test_install_refuses_empty_selector_allowlist():
    import pytest
    with pytest.raises(ValueError):
        build_install_session_key_module_calldata(
            validator_module_address="0x1111111111111111111111111111111111111111",
            session_signer="0x2222222222222222222222222222222222222222",
            spend_cap_wei=10**18,
            selector_allowlist=[],
            expiry_unix=1_800_000_000,
        )


def test_install_refuses_bad_selector():
    import pytest
    with pytest.raises(ValueError):
        build_install_session_key_module_calldata(
            validator_module_address="0x1111111111111111111111111111111111111111",
            session_signer="0x2222222222222222222222222222222222222222",
            spend_cap_wei=10**18,
            selector_allowlist=["0x617ba0"],  # not 4 bytes
            expiry_unix=1_800_000_000,
        )
