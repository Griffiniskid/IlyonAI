"""Pin tests for the 5 verified Morpho MetaMorpho USDC vaults on Arbitrum.

Underlying is native USDC: 0xaf88d065e77c8cC2239327C5EDb3A432268e5831 (6 dec).
Default registry entry points at Gauntlet USDC Prime (highest TVL); the
per-curator override registry maps the other 4 vaults by curator key.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from src.defi.execution.adapters.base import YieldBuildRequest
from src.defi.execution.adapters.erc4626 import (
    _ARB_MORPHO_USDC_VAULTS,
    _VAULT_REGISTRY,
    ERC4626VaultAdapter,
)


_USDC_ARB = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# --- Default registry entry (Gauntlet USDC Prime) ---------------------------

def test_default_morpho_blue_arb_usdc_is_gauntlet_prime():
    vault, asset, dec = _VAULT_REGISTRY[("arbitrum", "morpho-blue", "USDC")]
    assert vault == "0x7c574174DA4b2be3f705c6244B4BfA0815a8B3Ed"
    assert asset == _USDC_ARB
    assert dec == 6


def test_default_metamorpho_arb_usdc_alias_matches():
    """morpho-blue and metamorpho slugs both resolve to Gauntlet USDC Prime."""
    primary = _VAULT_REGISTRY[("arbitrum", "morpho-blue", "USDC")]
    alias = _VAULT_REGISTRY[("arbitrum", "metamorpho", "USDC")]
    assert primary == alias


# --- Per-curator vault address pins ----------------------------------------

@pytest.mark.parametrize(
    "curator,expected",
    [
        ("gauntlet-prime",   "0x7c574174DA4b2be3f705c6244B4BfA0815a8B3Ed"),
        ("gauntlet-core",    "0x7e97fa6893871A2751B5fE961978DCCb2c201E65"),
        ("steakhouse-prime", "0x250CF7c82bAc7cB6cf899b6052979d4B5BA1f9ca"),
        ("steakhouse-high",  "0x5c0C306Aaa9F877de636f4d5822cA9F2E81563BA"),
        ("kpk-yield",        "0x5837e4189819637853a357aF36650902347F5e73"),
    ],
)
def test_curator_registry_address_pin(curator: str, expected: str):
    assert _ARB_MORPHO_USDC_VAULTS[curator] == expected


def test_curator_registry_has_exactly_five_entries():
    """Lock the registry size — adding a vault should be a deliberate edit
    with a paired test, not a silent expansion."""
    assert len(_ARB_MORPHO_USDC_VAULTS) == 5


# --- Adapter build emits correct vault address per curator -----------------

def test_build_default_targets_gauntlet_prime():
    a = ERC4626VaultAdapter()
    req = YieldBuildRequest(
        chain="arbitrum", protocol="morpho-blue", asset_in="USDC",
        amount_in=Decimal("100"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    steps = _run(a.build(req))
    # deposit step (index 2) targets the vault contract
    deposit_step = steps[1]
    assert deposit_step.transaction.to.lower() == "0x7c574174DA4b2be3f705c6244B4BfA0815a8B3Ed".lower()


@pytest.mark.parametrize(
    "curator,expected_vault",
    [
        ("gauntlet-prime",   "0x7c574174DA4b2be3f705c6244B4BfA0815a8B3Ed"),
        ("gauntlet-core",    "0x7e97fa6893871A2751B5fE961978DCCb2c201E65"),
        ("steakhouse-prime", "0x250CF7c82bAc7cB6cf899b6052979d4B5BA1f9ca"),
        ("steakhouse-high",  "0x5c0C306Aaa9F877de636f4d5822cA9F2E81563BA"),
        ("kpk-yield",        "0x5837e4189819637853a357aF36650902347F5e73"),
    ],
)
def test_build_with_curator_override_targets_correct_vault(
    curator: str, expected_vault: str,
):
    a = ERC4626VaultAdapter()
    req = YieldBuildRequest(
        chain="arbitrum", protocol="morpho-blue", asset_in="USDC",
        amount_in=Decimal("100"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"vault_curator": curator},
    )
    steps = _run(a.build(req))
    deposit_step = steps[1]
    assert deposit_step.transaction.to.lower() == expected_vault.lower()
    # Approve step (index 1) spender is the vault — also verify.
    approve_step = steps[0]
    assert approve_step.transaction.spender.lower() == expected_vault.lower()


def test_unknown_curator_raises():
    a = ERC4626VaultAdapter()
    req = YieldBuildRequest(
        chain="arbitrum", protocol="morpho-blue", asset_in="USDC",
        amount_in=Decimal("100"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"vault_curator": "made-up-curator"},
    )
    with pytest.raises(ValueError, match="Unknown Morpho Arb USDC curator"):
        _run(a.build(req))
