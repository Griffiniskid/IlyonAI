"""Pass-A pin: 3 LST direct-mint adapters surfaced by Matrix hand-read.

Background
==========
Matrix Pass A turns 3/4 on A15_swell_rsweth / A17_mantle_meth / A18_kelp_rseth
fell back to generic pool_link cards instead of emitting native-mint
calldata, because the registry entries either had stale on-chain selectors
or expected the wrong arg shape for native ETH input. This file pins the
canonical on-chain values so a regression instantly fails CI.

Each selector here was verified against a live mainnet transaction in
2026-05 (see comments next to each assertion).
"""
from __future__ import annotations

from src.defi.execution.lst_registry import (
    get_lst_mint_route,
    lookup_lst,
)


# ─────────────────────────────────────────────────────────────────────────────
# A17 — Mantle mETH
# ─────────────────────────────────────────────────────────────────────────────


def test_mantle_meth_mint_route() -> None:
    """A17 turns 3/4: stake ETH via Mantle must hit Mantle Staking proxy."""
    route = get_lst_mint_route(token="meth", chain="ethereum")
    assert route is not None, "Mantle mETH must be in the LST registry"
    # Mantle Staking proxy on Ethereum mainnet
    # (see Etherscan 0xe3cBd06D7dadB3F4e6557bAb7EdD924CD1489E8f)
    assert route["contract"].lower() == "0xe3cbd06d7dadb3f4e6557bab7edd924cd1489e8f"
    # stake(uint256 minMETHAmount) external payable — selector verified via
    # tx 0x3fe0045191a7617a607b04a32dcbc07bdc95ca1adeb31a93a842a9a2fbf24217.
    assert route["selector"] == "0xa694fc3a"
    assert route["native_payable"] is True
    assert route["protocol"] == "mantle"
    assert route["receipt_token"] == "mETH"
    assert route["chain"] == "ethereum"


def test_mantle_meth_uppercase_symbol() -> None:
    """Routing layer often hands us upper-case symbols — must still resolve."""
    assert get_lst_mint_route(token="METH", chain="ethereum") is not None
    assert get_lst_mint_route(token="MeTh", chain="Ethereum") is not None


# ─────────────────────────────────────────────────────────────────────────────
# A18 — Kelp rsETH
# ─────────────────────────────────────────────────────────────────────────────


def test_kelp_rseth_mint_route() -> None:
    """A18 turns 3/4: stake ETH via Kelp must hit LRTDepositPool natively."""
    route = get_lst_mint_route(token="rseth", chain="ethereum")
    assert route is not None, "Kelp rsETH must be in the LST registry"
    # LRTDepositPool proxy on Ethereum mainnet
    assert route["contract"].lower() == "0x036676389e48133b63a802f8635ad39e752d375d"
    # depositETH(uint256 minRSETHAmountExpected, string referralId) payable —
    # selector verified via tx
    # 0x854f15912bfc56c97938208aae54c40f6fae0a242576fcbd5cbd7fdd5fa840e8.
    assert route["selector"] == "0x72c51c0b"
    assert route["native_payable"] is True
    assert route["protocol"] == "kelp"
    assert route["receipt_token"] == "rsETH"


def test_kelp_rseth_mixed_case() -> None:
    """rsETH / RSETH / rseth must all resolve to the same registry entry."""
    a = get_lst_mint_route(token="rsETH", chain="ethereum")
    b = get_lst_mint_route(token="RSETH", chain="ethereum")
    c = get_lst_mint_route(token="rseth", chain="ethereum")
    assert a == b == c
    assert a is not None


# ─────────────────────────────────────────────────────────────────────────────
# A15 — Swell rswETH
# ─────────────────────────────────────────────────────────────────────────────


def test_swell_rsweth_mint_route() -> None:
    """A15 turns 3/4: stake ETH via Swell must hit the rswETH proxy."""
    route = get_lst_mint_route(token="rsweth", chain="ethereum")
    assert route is not None, "Swell rswETH must be in the LST registry"
    # rswETH proxy on Ethereum mainnet
    assert route["contract"].lower() == "0xfae103dc9cf190ed75350761e95403b7b8afa6c0"
    # deposit() external payable — selector verified via tx
    # 0x2d390499a244a2502fd26937b85d0ec0a0a3594eae593ef5aba55c33799076c5.
    assert route["selector"] == "0xd0e30db0"
    assert route["native_payable"] is True
    assert route["protocol"] == "swell"
    assert route["receipt_token"] == "rswETH"


def test_swell_rsweth_lowercase() -> None:
    """rsweth (all-lower) must still resolve."""
    assert get_lst_mint_route(token="rsweth", chain="ethereum") is not None
    assert get_lst_mint_route(token="RSWETH", chain="ethereum") is not None


# ─────────────────────────────────────────────────────────────────────────────
# Cross-cutting invariants
# ─────────────────────────────────────────────────────────────────────────────


def test_unknown_token_returns_none() -> None:
    """Absent tokens return None so callers cleanly fall back to pool_link."""
    assert get_lst_mint_route(token="GARBAGE_TOKEN", chain="ethereum") is None
    assert get_lst_mint_route(token="mETH", chain="polygon") is None


def test_lookup_lst_case_insensitive() -> None:
    """`lookup_lst` must accept any-case symbol — used by the EVM LST adapter."""
    canonical = lookup_lst("ethereum", "mETH")
    assert canonical is not None
    assert lookup_lst("ethereum", "METH") is canonical
    assert lookup_lst("ethereum", "meth") is canonical
    assert lookup_lst("Ethereum", "mETH") is canonical


def test_get_lst_mint_route_dict_shape_stable() -> None:
    """The returned dict must contain every key consumers rely on."""
    route = get_lst_mint_route(token="stETH", chain="ethereum")  # Lido sanity check
    assert route is not None
    for key in ("contract", "selector", "native_payable", "protocol",
                "receipt_token", "min_native", "chain", "symbol"):
        assert key in route, f"missing key {key} in get_lst_mint_route output"
    assert route["protocol"] == "lido"
    assert route["selector"] == "0xa1903eab"  # Lido submit(address)


def test_pass_a_three_native_payable_set() -> None:
    """All three Pass-A entries must be native-ETH payable (single-step mint)."""
    for token in ("meth", "rseth", "rsweth"):
        r = get_lst_mint_route(token=token, chain="ethereum")
        assert r is not None, f"{token} missing"
        assert r["native_payable"] is True, f"{token} must be native-ETH payable"
        # 4-byte selector shape
        assert r["selector"].startswith("0x") and len(r["selector"]) == 10
