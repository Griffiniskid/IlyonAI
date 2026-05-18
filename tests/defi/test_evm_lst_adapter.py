"""EVM LST direct-mint adapter — per-protocol selector + arg shape."""
from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from src.defi.execution.adapters.base import YieldBuildRequest
from src.defi.execution.adapters.evm_lst import EvmLstDirectMintAdapter


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _req(protocol: str, asset_in: str = "ETH", amount: str = "1", **over):
    base = dict(
        chain="ethereum", protocol=protocol, asset_in=asset_in,
        amount_in=Decimal(amount),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        slippage_bps=0,
    )
    base.update(over)
    return YieldBuildRequest(**base)


def test_lido_emits_submit_with_referral():
    a = EvmLstDirectMintAdapter()
    steps = _run(a.build(_req("lido")))
    assert len(steps) == 1
    s = steps[0]
    assert s.transaction.data.startswith("0xa1903eab")
    # 1 word arg = referral = user address (left-padded)
    body = s.transaction.data[10:]
    assert len(body) == 64
    assert body.endswith("a" * 40)
    # msg.value = 1 ETH
    assert s.transaction.value == "0xde0b6b3a7640000"
    assert s.transaction.to == "0xae7ab96520de3a18e5e111b5eaab095312d7fe84"


def test_rocket_pool_emits_deposit_no_args():
    a = EvmLstDirectMintAdapter()
    steps = _run(a.build(_req("rocket-pool")))
    s = steps[0]
    # selector-only calldata (deposit() takes no args)
    assert s.transaction.data == "0xa3e0464d"
    assert s.transaction.value == "0xde0b6b3a7640000"


def test_etherfi_emits_deposit_no_args():
    a = EvmLstDirectMintAdapter()
    steps = _run(a.build(_req("ether.fi")))
    assert steps[0].transaction.data == "0xd5c08a72"


def test_renzo_emits_depositETH_with_referral():
    a = EvmLstDirectMintAdapter()
    steps = _run(a.build(_req("renzo")))
    s = steps[0]
    assert s.transaction.data.startswith("0xfdaf83a3")
    body = s.transaction.data[10:]
    assert len(body) == 64
    assert s.transaction.value == "0xde0b6b3a7640000"


def test_frax_emits_submit_no_args():
    a = EvmLstDirectMintAdapter()
    steps = _run(a.build(_req("frax-ether")))
    assert steps[0].transaction.data == "0x4dcd4547"


def test_swell_emits_deposit_no_args():
    """Swell rswETH deposit() is no-arg native ETH (selector 0xd0e30db0)."""
    a = EvmLstDirectMintAdapter()
    steps = _run(a.build(_req("swell")))
    assert steps[0].transaction.data == "0xd0e30db0"
    assert steps[0].transaction.value == "0xde0b6b3a7640000"


def test_mantle_emits_stake_uint256():
    """Mantle stake(uint256 minMETHAmount) is payable; default min=0."""
    a = EvmLstDirectMintAdapter()
    steps = _run(a.build(_req("mantle")))
    s = steps[0]
    assert s.transaction.data.startswith("0xa694fc3a")
    body = s.transaction.data[10:]
    # uint256 arg = 1 word
    assert len(body) == 64
    # default min_receive = 0 → zero-padded uint256
    assert int(body, 16) == 0
    assert s.transaction.value == "0xde0b6b3a7640000"


def test_mantle_min_receive_override():
    """extra.min_receive must round-trip into the uint256 calldata word."""
    a = EvmLstDirectMintAdapter()
    steps = _run(a.build(_req("mantle", extra={"min_receive": 123_456_789})))
    body = steps[0].transaction.data[10:]
    assert int(body, 16) == 123_456_789


def test_kelp_native_eth_path_emits_depositETH():
    """Kelp now uses native depositETH(uint256, string) — single step, msg.value=ETH."""
    a = EvmLstDirectMintAdapter()
    steps = _run(a.build(_req("kelp", asset_in="ETH", amount="1")))
    assert len(steps) == 1
    s = steps[0]
    assert s.transaction.data.startswith("0x72c51c0b")
    body = s.transaction.data[10:]
    # ABI layout: min(uint256) ‖ offset(uint256=0x40) ‖ len(uint256=0)
    # With empty referral string: 3 words = 192 hex chars exactly.
    assert len(body) == 3 * 64
    # word 0 = min_receive (default 0)
    assert int(body[0:64], 16) == 0
    # word 1 = string-tail offset = 0x40
    assert int(body[64:128], 16) == 0x40
    # word 2 = string length = 0 (empty referralId)
    assert int(body[128:192], 16) == 0
    # msg.value carries 1 ETH
    assert s.transaction.value == "0xde0b6b3a7640000"


def test_kelp_with_referral_id_encodes_string():
    """Non-empty referralId pads the dynamic string to a 32-byte boundary."""
    a = EvmLstDirectMintAdapter()
    steps = _run(a.build(_req(
        "kelp", asset_in="ETH", amount="1",
        extra={"referral_id": "kelp-abc"},  # 8 bytes
    )))
    body = steps[0].transaction.data[10:]
    # min + offset + len + 1 padded word for 8-byte body
    assert len(body) == 4 * 64
    assert int(body[128:192], 16) == 8  # length field
    # body word = "kelp-abc" hex-encoded + 24-byte zero pad
    expected_body = b"kelp-abc".hex() + ("00" * 24)
    assert body[192:256] == expected_body


def test_puffer_erc4626_deposit_uint256():
    a = EvmLstDirectMintAdapter()
    req = _req("puffer", asset_in="stETH", amount="2",
               extra={"token_address": "0xae7ab96520de3a18e5e111b5eaab095312d7fe84"})
    steps = _run(a.build(req))
    assert len(steps) == 2
    # ERC-4626 deposit(uint256)
    assert steps[1].transaction.data.startswith("0xb6b55f25")
    body = steps[1].transaction.data[10:]
    # 1 word arg = uint256
    assert len(body) == 64


def test_min_deposit_rejected_below_threshold():
    a = EvmLstDirectMintAdapter()
    # Lido min = 0.0001 ETH; try 0.00001 ETH.
    req = _req("lido", amount="0.00001")
    with pytest.raises(ValueError, match="min deposit"):
        _run(a.build(req))


def test_supports_each_protocol():
    a = EvmLstDirectMintAdapter()
    for proto in ("lido", "rocket-pool", "ether.fi", "frax-ether", "mantle",
                  "renzo", "kelp", "swell", "puffer"):
        r = a.supports(chain="ethereum", protocol=proto, action="stake")
        assert r.supported is True, f"protocol {proto} not supported"


def test_amount_in_must_be_positive():
    a = EvmLstDirectMintAdapter()
    req = _req("lido", amount="0")
    with pytest.raises(ValueError, match="amount_in must be > 0"):
        _run(a.build(req))


def test_unsupported_chain_raises():
    a = EvmLstDirectMintAdapter()
    req = _req("lido")
    req.chain = "polygon"
    with pytest.raises(ValueError, match="No LST registry entry"):
        _run(a.build(req))


def test_puffer_without_token_address_raises_for_non_eth():
    """Puffer is ERC-4626; non-ETH non-token_address input must be rejected."""
    a = EvmLstDirectMintAdapter()
    req = _req("puffer", asset_in="stETH", amount="5")
    with pytest.raises(ValueError, match="extra.token_address"):
        _run(a.build(req))
