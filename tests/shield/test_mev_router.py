"""V7-037 pin tests — MEV auto-flip thresholds + chain routing."""

from src.shield.mev_router import (
    JITO_TIP_LAMPORTS_DEFAULT,
    MEVBLOCKER_RPC,
    private_rpc_for_chain,
    should_route_private,
)


def test_should_route_private_slippage_above_threshold():
    assert should_route_private(31, 100) is True


def test_should_route_private_slippage_at_threshold_is_false():
    # strict > so 30 bps exact is NOT private
    assert should_route_private(30, 100) is False


def test_should_route_private_notional_above_threshold():
    assert should_route_private(20, 6_000) is True


def test_should_route_private_below_both_thresholds():
    assert should_route_private(20, 100) is False


def test_private_rpc_ethereum_returns_mevblocker():
    cfg = private_rpc_for_chain("ethereum", 50, 100)
    assert cfg is not None
    assert cfg["rpc_url"] == MEVBLOCKER_RPC
    assert cfg["lane"] == "mevblocker"


def test_private_rpc_solana_returns_jito_tip():
    cfg = private_rpc_for_chain("solana", 50, 100)
    assert cfg is not None
    assert cfg["jito_tip_lamports"] == JITO_TIP_LAMPORTS_DEFAULT
    assert cfg["lane"] == "jito"


def test_private_rpc_base_returns_none_unsupported():
    # base chain has no MEV protection wired yet
    assert private_rpc_for_chain("base", 50, 100) is None


def test_private_rpc_ethereum_below_threshold_returns_none():
    assert private_rpc_for_chain("ethereum", 20, 100) is None


def test_private_rpc_eth_alias_works():
    cfg = private_rpc_for_chain("eth", 100, 100)
    assert cfg is not None
    assert cfg["lane"] == "mevblocker"


def test_private_rpc_sol_alias_works():
    cfg = private_rpc_for_chain("sol", 100, 100)
    assert cfg is not None
    assert cfg["lane"] == "jito"
