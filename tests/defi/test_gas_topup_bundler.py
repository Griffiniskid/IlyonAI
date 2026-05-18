"""Pin tests for V7-040 gas-topup auto-bundle."""
import asyncio

import pytest

from src.defi.composed.gas_topup_bundler import (
    GasTopupBundle,
    build_gas_topup_bundle,
    build_gas_topup_bundle_async,
    _native_for_chain,
    _score_quote,
    _select_bridge_quote,
)


class _StubClient:
    """Stub matching the Bridge.quote() protocol used by deBridge/LI.FI/Socket."""

    def __init__(self, *, expected_dst_amount=None, ttl_s=300, raises=None, quote_id="q"):
        self.expected_dst_amount = expected_dst_amount
        self.ttl_s = ttl_s
        self.raises = raises
        self.quote_id = quote_id
        self.calls = 0

    async def quote(self, **kwargs):
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return {
            "expected_dst_amount": self.expected_dst_amount,
            "slippage_bps_band": {"min": 0, "max": 50},
            "quote_id": self.quote_id,
            "ttl_s": self.ttl_s,
            "via": self.quote_id,
        }


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


# ----- V7-040: real quote-based bridge selection -----


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_select_bridge_quote_picks_lowest_score():
    """Lowest (cost_usd + minutes*0.10) wins.

    debridge: cost=$0.30, ttl=600s (10min)  -> 0.30 + 1.0  = 1.30
    lifi:     cost=$0.10, ttl=900s (15min)  -> 0.10 + 1.5  = 1.60
    socket:   cost=$0.20, ttl=120s (2min)   -> 0.20 + 0.2  = 0.40  <-- winner
    """
    needed = 5.0
    debridge = _StubClient(expected_dst_amount=int((needed - 0.30) * 1_000_000), ttl_s=600, quote_id="dbr-1")
    lifi = _StubClient(expected_dst_amount=int((needed - 0.10) * 1_000_000), ttl_s=900, quote_id="lifi-1")
    socket = _StubClient(expected_dst_amount=int((needed - 0.20) * 1_000_000), ttl_s=120, quote_id="sock-1")
    sel = _run(
        _select_bridge_quote(
            source_chain="ethereum",
            dest_chain="arbitrum",
            needed_usd=needed,
            recipient="0xabc",
            debridge_client=debridge,
            lifi_client=lifi,
            socket_client=socket,
        )
    )
    assert sel["all_failed"] is False
    assert sel["winner"]["route"] == "socket"
    assert sel["winner"]["quote_id"] == "sock-1"
    # Both losing quotes captured for observability.
    dropped_routes = {q["route"] for q in sel["dropped"]}
    assert dropped_routes == {"debridge", "lifi"}


def test_all_three_clients_fail_emits_blocker():
    """If all 3 bridges raise, async builder returns GAS_TOPUP_REQUIRED blocker."""
    inv = {"ethereum": {"USDC": 100}}
    debridge = _StubClient(raises=RuntimeError("dlcn 500"))
    lifi = _StubClient(raises=RuntimeError("li.fi timeout"))
    socket = _StubClient(raises=RuntimeError("socket 429"))
    out = _run(
        build_gas_topup_bundle_async(
            "arbitrum",
            5.0,
            inv,
            recipient="0xabc",
            debridge_client=debridge,
            lifi_client=lifi,
            socket_client=socket,
        )
    )
    assert "bundle" not in out
    assert out["blocker"]["code"] == "GAS_TOPUP_REQUIRED"
    assert "all 3 bridge quotes failed" in out["blocker"]["reason"]
    # Every client was actually called (no silent short-circuit).
    assert debridge.calls == 1 and lifi.calls == 1 and socket.calls == 1


def test_one_fails_two_succeed_winner_picked_from_survivors():
    """If 1 raises and 2 return, winner is the lowest score of the surviving 2."""
    inv = {"ethereum": {"USDC": 100}}
    needed = 5.0
    debridge = _StubClient(raises=RuntimeError("dlcn 500"))
    # lifi: cost=$0.05, ttl=900s -> 0.05 + 1.5 = 1.55
    lifi = _StubClient(expected_dst_amount=int((needed - 0.05) * 1_000_000), ttl_s=900, quote_id="lifi-1")
    # socket: cost=$0.40, ttl=60s -> 0.40 + 0.1 = 0.50  <-- winner
    socket = _StubClient(expected_dst_amount=int((needed - 0.40) * 1_000_000), ttl_s=60, quote_id="sock-1")
    out = _run(
        build_gas_topup_bundle_async(
            "arbitrum",
            needed,
            inv,
            recipient="0xabc",
            debridge_client=debridge,
            lifi_client=lifi,
            socket_client=socket,
        )
    )
    assert "bundle" in out
    bundle = out["bundle"]
    assert bundle.bridge_route == "socket"
    assert bundle.selected_quote_id == "sock-1"
    # Only the lifi quote should appear in dropped (debridge raised, never scored).
    assert len(bundle.dropped_quotes) == 1
    assert bundle.dropped_quotes[0]["route"] == "lifi"
    # Bundle steps still 2 (bridge + swap), bridge step carries `via`+`quote_id`.
    assert len(bundle.bundle_steps) == 2
    assert bundle.bundle_steps[0]["via"] == "sock-1"
    assert bundle.bundle_steps[0]["quote_id"] == "sock-1"


def test_no_source_emits_blocker():
    """No cross-chain USDC -> GAS_TOPUP_REQUIRED blocker (not silent None)."""
    out = _run(
        build_gas_topup_bundle_async(
            "arbitrum",
            5.0,
            {"arbitrum": {"USDC": 0}},
            recipient="0xabc",
            debridge_client=_StubClient(expected_dst_amount=4_900_000),
            lifi_client=_StubClient(expected_dst_amount=4_900_000),
            socket_client=_StubClient(expected_dst_amount=4_900_000),
        )
    )
    assert "bundle" not in out
    assert out["blocker"]["code"] == "GAS_TOPUP_REQUIRED"


def test_score_function_penalty_weighting():
    """_score_quote(cost, time) = cost + (time/60)*0.10."""
    assert _score_quote(1.0, 0) == pytest.approx(1.0)
    assert _score_quote(1.0, 600) == pytest.approx(1.0 + 1.0)
    assert _score_quote(0.0, 300) == pytest.approx(0.5)
