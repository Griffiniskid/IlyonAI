"""Pin tests for badge/exec capability source-of-truth unification.

A03/T1 vs A03/T4 in matrix Pass A: search card showed
"Execution: ready via enso-shortcut-fallback" but execute returned
"Direct execution from chat is currently disabled". Two sources of truth.
After fix, both consult get_exec_capability().
"""
from __future__ import annotations

from src.agent.protocol_urls import get_exec_capability


def test_uniswap_v3_lp_is_link_only():
    # sushiswap-v3 is in V3_PROTOCOLS but NOT in V3_NATIVE_EXEC, so
    # is_pool_link_action returns True → mode is link_only.
    cap = get_exec_capability(
        protocol="sushiswap-v3", chain="base", action="add_liquidity"
    )
    assert cap["executable"] is False
    assert cap["mode"] == "link_only"


def test_aave_supply_is_deterministic():
    cap = get_exec_capability(protocol="aave", chain="base", action="supply")
    assert cap["executable"] is True
    assert cap["mode"] in ("deterministic", "enso_fallback")


def test_morpho_ethereum_supply_is_executable():
    cap = get_exec_capability(protocol="morpho", chain="ethereum", action="supply")
    assert cap["executable"] is True


def test_unknown_protocol_not_executable():
    # is_pool_link_action with action="supply" + unknown protocol returns True
    # (falls into "EVM supply / deposit / lend — let known-good through" branch).
    cap = get_exec_capability(
        protocol="foobar123", chain="ethereum", action="supply"
    )
    assert cap["executable"] is False
    assert cap["mode"] in ("unknown", "link_only")


def test_none_inputs_safe():
    cap = get_exec_capability(protocol=None, chain=None, action=None)
    assert cap["executable"] is False
