"""Pin: Kelp/Puffer auto-wrap when user passes ETH but mint requires ERC20.

v4-A18 caught 'Stake 0.05 ETH on Kelp' blocked with 'expects ERC20 input'.
Auto-wrap prepends WETH.deposit() (selector 0xd0e30db0) and uses canonical
WETH as the token_address.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

from src.defi.execution.adapters.evm_lst import EvmLstDirectMintAdapter
from src.defi.execution.adapters.base import YieldBuildRequest


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_kelp_eth_auto_wraps_to_weth():
    a = EvmLstDirectMintAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="kelp", asset_in="ETH",
        amount_in=Decimal("0.05"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "stake", "receipt_symbol": "rsETH"},
    )
    steps = _run(a.build(req))
    assert len(steps) == 3
    wrap, approve, mint = steps
    # Wrap step: WETH.deposit() with msg.value=amount
    assert wrap.transaction.data == "0xd0e30db0"
    assert wrap.transaction.to.lower() == "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
    assert wrap.transaction.value != "0x0"
    # Approve step: approve(Kelp depositPool, amount)
    assert approve.transaction.data.startswith("0x095ea7b3")
    # Mint step: depositAsset(WETH, amount)
    assert mint.transaction.data.startswith("0x47e7ef24")
    assert mint.asset_out == "rsETH"


def test_kelp_native_token_unchanged_when_native_eth_true():
    """Sanity: protocols with native_eth=True (Lido, Renzo) still take ETH directly."""
    a = EvmLstDirectMintAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="lido", asset_in="ETH",
        amount_in=Decimal("0.05"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "stake", "receipt_symbol": "stETH"},
    )
    steps = _run(a.build(req))
    assert len(steps) == 1
    assert steps[0].transaction.data.startswith("0xa1903eab")  # submit(referral)
