"""RC7b — native-ETH wrap detection pin tests.

Pin: native ETH / MATIC / BNB / AVAX → ERC20-shape supply/LP must
prepend a WETH9.deposit() wrap step, NEVER a swap-router round-trip.
Pass A H03 captured a plan that swapped ETH→WETH via Enso instead of
calling WETH9.deposit() at 0xc02a...756cc2 — paying router fees on a
free 1:1 conversion.

Verifies:
  * is_native_wrap_required fires on (ETH, ethereum, lp_mint)
  * is_native_wrap_required returns False for non-native asset
  * is_native_wrap_required returns False for non-LP action
  * build_wrap_step emits canonical 0xd0e30db0 selector + value=amount
  * build_wrap_step refuses chains without canonical wrapped native
"""
from __future__ import annotations

import pytest

from src.defi.execution.composed_plan import (
    WETH9_DEPOSIT_SELECTOR,
    build_wrap_step,
    get_wrapped_native_for_chain,
    is_native_wrap_required,
)


class TestIsNativeWrapRequired:
    def test_eth_on_ethereum_lp_mint(self):
        assert is_native_wrap_required(
            chain="ethereum", asset_in="ETH", action="lp_mint",
        )

    def test_eth_on_base_deposit_lp(self):
        assert is_native_wrap_required(
            chain="base", asset_in="ETH", action="deposit_lp",
        )

    def test_eth_on_arbitrum_supply(self):
        assert is_native_wrap_required(
            chain="arbitrum", asset_in="ETH", action="supply",
        )

    def test_matic_on_polygon_lp_mint(self):
        assert is_native_wrap_required(
            chain="polygon", asset_in="MATIC", action="lp_mint",
        )

    def test_bnb_on_bsc_provide_liquidity(self):
        assert is_native_wrap_required(
            chain="bsc", asset_in="BNB", action="provide_liquidity",
        )

    def test_avax_on_avalanche_lp_mint(self):
        assert is_native_wrap_required(
            chain="avalanche", asset_in="AVAX", action="lp_mint",
        )

    def test_eth_on_linea_supply(self):
        assert is_native_wrap_required(
            chain="linea", asset_in="ETH", action="supply",
        )

    def test_wrapped_asset_already_does_not_trigger(self):
        """WETH on ethereum — already wrapped, no wrap step needed."""
        assert not is_native_wrap_required(
            chain="ethereum", asset_in="WETH", action="lp_mint",
        )

    def test_usdc_does_not_trigger(self):
        assert not is_native_wrap_required(
            chain="base", asset_in="USDC", action="supply",
        )

    def test_eth_on_solana_does_not_trigger(self):
        """Solana wraps via SPL Token::SyncNative, not WETH9 — sidecar
        handles it. Our EVM helper must not fire for Solana."""
        assert not is_native_wrap_required(
            chain="solana", asset_in="SOL", action="lp_mint",
        )

    def test_swap_action_does_not_trigger_wrap(self):
        """Swap is its own action — wrap is not needed before swap."""
        assert not is_native_wrap_required(
            chain="ethereum", asset_in="ETH", action="swap",
        )

    def test_stake_action_does_not_trigger_wrap(self):
        """LST stake adapters handle wrap themselves (native deposit())."""
        assert not is_native_wrap_required(
            chain="ethereum", asset_in="ETH", action="stake",
        )


class TestGetWrappedNativeForChain:
    def test_ethereum_returns_canonical_weth9(self):
        result = get_wrapped_native_for_chain("ethereum")
        assert result is not None
        sym, addr = result
        assert sym == "WETH"
        # Canonical WETH9: 0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2
        assert addr.lower() == "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"

    def test_base_returns_weth(self):
        result = get_wrapped_native_for_chain("base")
        assert result is not None
        sym, addr = result
        assert sym == "WETH"
        # Base WETH: 0x4200...0006
        assert addr.lower() == "0x4200000000000000000000000000000000000006"

    def test_polygon_returns_wmatic(self):
        result = get_wrapped_native_for_chain("polygon")
        assert result is not None
        sym, addr = result
        assert sym == "WMATIC"

    def test_bsc_returns_wbnb(self):
        result = get_wrapped_native_for_chain("bsc")
        assert result is not None
        sym, addr = result
        assert sym == "WBNB"

    def test_avalanche_returns_wavax(self):
        result = get_wrapped_native_for_chain("avalanche")
        assert result is not None
        sym, addr = result
        assert sym == "WAVAX"

    def test_unknown_chain_returns_none(self):
        assert get_wrapped_native_for_chain("aptos") is None


class TestBuildWrapStep:
    def test_eth_ethereum_emits_canonical_deposit_selector(self):
        step = build_wrap_step(
            chain="ethereum", native_symbol="ETH",
            amount_wei=10**18,  # 1 ETH
        )
        assert step.asset_in == "ETH"
        assert step.asset_out == "WETH"
        assert step.transaction is not None
        # Canonical WETH9.deposit() selector — full calldata is just the
        # selector because deposit() takes no args.
        assert step.transaction.data == WETH9_DEPOSIT_SELECTOR
        assert step.transaction.data == "0xd0e30db0"
        # value=amount in hex
        assert step.transaction.value == "0xde0b6b3a7640000"  # 10**18 hex
        assert step.transaction.to.lower() == "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
        assert step.transaction.chain_id == 1
        assert step.transaction.chain_kind == "evm"
        # Zero slippage on a 1:1 native wrap.
        assert step.slippage_bps == 0

    def test_matic_polygon_emits_wmatic_to(self):
        step = build_wrap_step(
            chain="polygon", native_symbol="MATIC", amount_wei=5 * 10**18,
        )
        assert step.asset_in == "MATIC"
        assert step.asset_out == "WMATIC"
        # WMATIC contract address.
        assert step.transaction.to.lower() == "0x0d500b1d8e8ef31e21c99d1db9a6444d3adf1270"
        assert step.transaction.chain_id == 137

    def test_bnb_bsc_emits_wbnb_to(self):
        step = build_wrap_step(
            chain="bsc", native_symbol="BNB", amount_wei=2 * 10**18,
        )
        assert step.asset_out == "WBNB"
        # WBNB: 0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c
        assert step.transaction.to.lower() == "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"

    def test_avax_avalanche_emits_wavax(self):
        step = build_wrap_step(
            chain="avalanche", native_symbol="AVAX", amount_wei=10**17,
        )
        assert step.asset_out == "WAVAX"
        # WAVAX: 0xb31f66aa3c1e785363f0875a1b74e27b85fd66c7
        assert step.transaction.to.lower() == "0xb31f66aa3c1e785363f0875a1b74e27b85fd66c7"

    def test_zero_amount_refused(self):
        with pytest.raises(ValueError, match="amount_wei must be > 0"):
            build_wrap_step(chain="ethereum", native_symbol="ETH", amount_wei=0)

    def test_unknown_chain_refused(self):
        with pytest.raises(ValueError, match="no canonical wrapped native"):
            build_wrap_step(
                chain="aptos", native_symbol="APT", amount_wei=10**8,
            )

    def test_selector_is_deposit_paren_paren_keccak(self):
        """Sanity-pin: keccak256('deposit()')[:4] == 0xd0e30db0."""
        # Don't pull in eth_utils; just verify our constant matches the
        # well-known on-chain WETH9 selector.
        assert WETH9_DEPOSIT_SELECTOR == "0xd0e30db0"
