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
    a = EvmLstDirectMintAdapter()
    steps = _run(a.build(_req("swell")))
    assert steps[0].transaction.data == "0xf340fa01"


def test_mantle_emits_stake_no_args():
    a = EvmLstDirectMintAdapter()
    steps = _run(a.build(_req("mantle")))
    assert steps[0].transaction.data == "0xf6326fb3"


def test_kelp_erc20_path_two_step_with_approve():
    a = EvmLstDirectMintAdapter()
    req = _req("kelp", asset_in="ETHx", amount="5",
               extra={"token_address": "0xa35b1b31ce002fbf2058d22f30f95d405200a15b"})
    steps = _run(a.build(req))
    assert len(steps) == 2
    assert steps[0].action == "approve"
    assert steps[0].transaction.data.startswith("0x095ea7b3")
    # depositAsset(address, uint256)
    assert steps[1].transaction.data.startswith("0x47e7ef24")
    body = steps[1].transaction.data[10:]
    assert len(body) == 2 * 64
    assert steps[1].transaction.value == "0x0"


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


def test_kelp_without_token_address_raises():
    a = EvmLstDirectMintAdapter()
    req = _req("kelp", asset_in="ETHx", amount="5")
    with pytest.raises(ValueError, match="extra.token_address"):
        _run(a.build(req))
