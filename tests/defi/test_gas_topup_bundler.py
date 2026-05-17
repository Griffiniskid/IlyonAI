"""Pin tests for V7-040 gas-topup auto-bundle."""
from src.defi.composed.gas_topup_bundler import (
    GasTopupBundle,
    build_gas_topup_bundle,
    _native_for_chain,
)


def test_cross_chain_topup_returns_bundle_with_two_steps():
    """User has $100 USDC on ethereum, needs $5 gas on arbitrum -> 2-step bundle."""
    inv = {"ethereum": {"USDC": 100}, "arbitrum": {"USDC": 0}}
    b = build_gas_topup_bundle("arbitrum", 5.0, inv)
    assert b is not None
    assert isinstance(b, GasTopupBundle)
    assert b.source_chain == "ethereum"
    assert b.dest_chain == "arbitrum"
    assert b.source_token == "USDC"
    assert b.dest_native_token == "ETH"
    assert b.bridge_route == "debridge"
    assert len(b.bundle_steps) == 2


def test_empty_inventory_returns_none():
    """User has nothing -> None."""
    assert build_gas_topup_bundle("arbitrum", 5.0, {}) is None
    assert build_gas_topup_bundle("arbitrum", 5.0, {"ethereum": {}}) is None
    assert build_gas_topup_bundle("arbitrum", 5.0, {"ethereum": {"USDC": 0}}) is None


def test_same_chain_only_returns_none():
    """User has $5 USDC on arbitrum (same chain) -> None (not cross-chain)."""
    inv = {"arbitrum": {"USDC": 5}}
    assert build_gas_topup_bundle("arbitrum", 5.0, inv) is None


def test_bundle_steps_order_bridge_then_swap():
    """Bundle steps: bridge first, then swap."""
    inv = {"ethereum": {"USDC": 100}}
    b = build_gas_topup_bundle("arbitrum", 5.0, inv)
    assert b is not None
    assert b.bundle_steps[0]["action"] == "bridge"
    assert b.bundle_steps[0]["from"] == "ethereum"
    assert b.bundle_steps[0]["to"] == "arbitrum"
    assert b.bundle_steps[0]["asset"] == "USDC"
    assert b.bundle_steps[0]["amount_usd"] == 5.0
    assert b.bundle_steps[1]["action"] == "swap"
    assert b.bundle_steps[1]["chain"] == "arbitrum"
    assert b.bundle_steps[1]["from"] == "USDC"
    assert b.bundle_steps[1]["to"] == "ETH"
    assert b.bundle_steps[1]["amount_usd"] == 5.0


def test_native_for_chain_mapping():
    """_native_for_chain returns correct native tokens."""
    assert _native_for_chain("polygon") == "MATIC"
    assert _native_for_chain("sonic") == "S"
    assert _native_for_chain("ethereum") == "ETH"
    assert _native_for_chain("arbitrum") == "ETH"
    assert _native_for_chain("base") == "ETH"
    assert _native_for_chain("optimism") == "ETH"
    assert _native_for_chain("bsc") == "BNB"
    assert _native_for_chain("avalanche") == "AVAX"
    assert _native_for_chain("berachain") == "BERA"
    assert _native_for_chain("celo") == "CELO"
    assert _native_for_chain("mantle") == "MNT"
    assert _native_for_chain("gnosis") == "XDAI"
    # case-insensitive
    assert _native_for_chain("POLYGON") == "MATIC"
    assert _native_for_chain("Sonic") == "S"
    # unknown defaults to ETH
    assert _native_for_chain("unknownchain") == "ETH"


def test_insufficient_usdc_returns_none():
    """User has USDC but not enough to cover needed_usd -> None."""
    inv = {"ethereum": {"USDC": 3}}
    assert build_gas_topup_bundle("arbitrum", 5.0, inv) is None


def test_polygon_destination_uses_matic():
    """Cross-chain topup to polygon yields MATIC as dest_native_token."""
    inv = {"ethereum": {"USDC": 50}}
    b = build_gas_topup_bundle("polygon", 10.0, inv)
    assert b is not None
    assert b.dest_native_token == "MATIC"
    assert b.bundle_steps[1]["to"] == "MATIC"
