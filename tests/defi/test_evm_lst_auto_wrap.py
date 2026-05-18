"""Pin: Kelp + Puffer ETH handling.

History:
  v4-A18 caught 'Stake 0.05 ETH on Kelp' blocked with 'expects ERC20 input'.
  Initial fix prepended a WETH.deposit() wrap + approve + depositAsset chain.
  Pass-A (2026-05-18) confirmed the registry now wires Kelp's native
  ``depositETH(uint256 minRSETH, string referralId)`` payable selector
  ``0x72c51c0b``, so the wrap+approve chain is unnecessary for ETH input
  and the entire stake collapses into a single native-mint step.

  Puffer remains a true ERC-4626 vault (ERC20 in), so its auto-wrap path
  is still required for ETH input.
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


def test_kelp_eth_uses_native_depositETH_single_step():
    """Pass-A regression: Kelp ETH stake must be a single native-mint step.

    Selector 0x72c51c0b = depositETH(uint256,string). msg.value carries the
    ETH. No wrap, no approve.
    """
    a = EvmLstDirectMintAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="kelp", asset_in="ETH",
        amount_in=Decimal("0.05"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "stake", "receipt_symbol": "rsETH"},
    )
    steps = _run(a.build(req))
    assert len(steps) == 1
    s = steps[0]
    assert s.transaction.data.startswith("0x72c51c0b")
    assert s.transaction.to.lower() == "0x036676389e48133b63a802f8635ad39e752d375d"
    assert s.transaction.value != "0x0"
    assert s.asset_out == "rsETH"


def test_puffer_eth_still_auto_wraps_to_weth():
    """Puffer is a true ERC-4626 vault and still needs WETH input.

    The auto-wrap path remains active for ETH → ERC-4626 deposits.
    """
    a = EvmLstDirectMintAdapter()
    req = YieldBuildRequest(
        chain="ethereum", protocol="puffer", asset_in="ETH",
        amount_in=Decimal("0.05"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "stake", "receipt_symbol": "pufETH"},
    )
    steps = _run(a.build(req))
    assert len(steps) == 3
    wrap, approve, mint = steps
    assert wrap.transaction.data == "0xd0e30db0"  # WETH.deposit()
    assert wrap.transaction.to.lower() == "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
    assert approve.transaction.data.startswith("0x095ea7b3")
    assert mint.transaction.data.startswith("0xb6b55f25")  # ERC-4626 deposit(uint256)


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
