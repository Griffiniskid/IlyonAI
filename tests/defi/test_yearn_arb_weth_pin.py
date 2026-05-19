"""V7-065 — Pin test for Yearn V3 yvWETH vault on Arbitrum.

Status (2026-05-19): NO canonical Yearn V3 yvWETH vault on Arbitrum could be
verified via the authoritative ydaemon registry (ydaemon.yearn.fi). A query
for chainID=42161 with underlying token 0x82af49447d8a07e3bd95bd0d56f35241523fbab1
returned only one match — `0x71B34b7c4A0592a186DDB2FDE1fCDEBe299150dd`
("Prize Compound WETH - Beefy" / przcWETH) — which is a third-party Beefy
strategy wrapper with zero TVL and is NOT a canonical yvWETH vault.

The best-guess address `0x044E75fCbF7BD3f8f4577FF317554e9c0037F145` returned
HTTP 404 on the Yearn V3 UI and on the ydaemon by-address endpoint, confirming
it is not a registered vault.

Per the repo HARD RULE — "NEVER guess on-chain addresses; must verify via
WebFetch or via repo's existing registries" — the registry entry is NOT
written. This pin test is `xfail` until a canonical Yearn V3 yvWETH-Arb vault
is deployed and indexed by ydaemon. When that happens, the address can be
filled in here, the entry added to `_VAULT_REGISTRY`, and the `xfail` removed.

Generic ERC-4626 dispatch already handles the symbol-only fallback path:
`erc4626.py:_VAULT_REGISTRY.get(...)` falls back to single-match-by-(chain,
asset) when the protocol-keyed lookup misses, so end users are not blocked —
they simply lack an explicit pin.
"""
from __future__ import annotations

import pytest

from src.defi.execution.adapters.erc4626 import _VAULT_REGISTRY


_WETH_ARB = "0x82af49447d8a07e3bd95bd0d56f35241523fbab1"


@pytest.mark.xfail(
    reason=(
        "Yearn V3 yvWETH-Arb vault address not verifiable as of 2026-05-19 — "
        "ydaemon.yearn.fi has no canonical Yearn V3 vault with WETH underlying "
        "on chain 42161. Best-guess address 0x044E75fCbF7BD3f8f4577FF317554e9c0037F145 "
        "returned 404. Per HARD RULE, no address is pinned until verifiable."
    ),
    strict=True,
)
def test_yearn_v3_weth_arb_registry_pin():
    """Expected pin once a canonical yvWETH-Arb vault is verifiable.

    When un-xfail'd, this test will assert:
    - registry entry exists under ("arbitrum", "yearn-finance", "WETH")
    - underlying asset address == WETH on Arbitrum (verified)
    - decimals == 18
    - vault address is a non-zero 0x-prefixed 42-char string
    """
    key = ("arbitrum", "yearn-finance", "WETH")
    assert key in _VAULT_REGISTRY, (
        "Yearn yvWETH-Arb pin missing — see file docstring for verification status."
    )
    vault, asset, decimals = _VAULT_REGISTRY[key]
    assert asset.lower() == _WETH_ARB.lower()
    assert decimals == 18
    assert vault.startswith("0x") and len(vault) == 42
    assert int(vault, 16) != 0


def test_weth_arb_address_constant_is_canonical():
    """Sanity: the WETH-Arb token address used by the pending pin is the
    canonical Arbitrum WETH (https://arbiscan.io/token/0x82aF49447D8a07e3bd95BD0d56f35241523fBab1).
    This guards against typo regressions in the xfail body above."""
    assert _WETH_ARB == "0x82af49447d8a07e3bd95bd0d56f35241523fbab1"


def test_yearn_finance_in_adapter_protocol_set():
    """yearn-finance must remain in the adapter's supported protocols so the
    pin can be wired without further plumbing once an address is verified."""
    from src.defi.execution.adapters.erc4626 import ERC4626VaultAdapter
    a = ERC4626VaultAdapter()
    assert "yearn-finance" in a.protocols
    assert "arbitrum" in a.chains
