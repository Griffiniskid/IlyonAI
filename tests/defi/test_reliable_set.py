import importlib

from src.defi.execution import reliable_set as rs


def test_only_fork_proven_combos_execute():
    # Only (chain, protocol) pairs broadcast-proven on a fork get EXECUTE.
    assert rs.is_reliable_exec(protocol="aave-v3", chain="ethereum", symbol="USDC", action="supply") == (True, None)
    assert rs.is_reliable_exec(protocol="compound-v3", chain="ethereum", symbol="USDC", action="supply") == (True, None)
    assert rs.is_reliable_exec(protocol="uniswap-v2", chain="ethereum", symbol="USDC-WETH", action="deposit_lp")[0] is True
    assert rs.is_reliable_exec(protocol="aave-v3", chain="base", symbol="USDC", action="supply")[0] is True


def test_unproven_chains_deeplink():
    # BSC passed eth_call sim but reverted on broadcast → must deep-link until
    # a green fork run, even though the protocol family is "reliable".
    ok, reason = rs.is_reliable_exec(protocol="pancakeswap-amm", chain="bsc", symbol="USDT-WBNB", action="deposit_lp")
    assert ok is False and "on-chain-verified" in reason
    ok, _ = rs.is_reliable_exec(protocol="aave-v3", chain="bsc", symbol="USDC", action="supply")
    assert ok is False


def test_deferred_families_deeplink():
    # Curve, V3, and Solana are deferred this pass → not executable.
    for proto, chain, sym in [
        ("curve-dex", "ethereum", "CRVUSD-USDC"),
        ("uniswap-v3", "ethereum", "USDC-WETH"),
        ("marinade", "solana", "MSOL"),
        ("orca-dex", "solana", "SOL-USDC"),
    ]:
        ok, reason = rs.is_reliable_exec(protocol=proto, chain=chain, symbol=sym, action="deposit_lp")
        assert ok is False and reason


def test_exotic_leg_rejected():
    ok, reason = rs.is_reliable_exec(protocol="uniswap-v2", chain="ethereum", symbol="PEPE-WETH", action="deposit_lp")
    assert ok is False and "routable" in reason


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("POOL_EXEC_ENABLED", raising=False)
    importlib.reload(rs)
    assert rs.pool_exec_enabled() is False
    monkeypatch.setenv("POOL_EXEC_ENABLED", "1")
    assert rs.pool_exec_enabled() is True
    monkeypatch.setenv("POOL_EXEC_ENABLED", "off")
    assert rs.pool_exec_enabled() is False
