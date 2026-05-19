"""Pin tests for §13 spec-scenario blockers (fix-wave-3).

Covers H07/H08/H09/H10/H11/H12/H14/H15 + E15 — Pass C 58517bf hand-read
caught nine §13 scenarios where the build path silently produced a
signable plan instead of a structured blocker. These pins lock the
behavior shipped in `src/defi/execution/scenarios/scenario_blockers.py`
and the wire-up inside `build_yield_execution_plan`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import pytest

from src.defi.execution.models import (
    ExecutionStepV3,
    KNOWN_BLOCKER_CODES,
    UnsignedStepTransaction,
    make_step,
)
from src.defi.execution.preflight import WalletInventory
from src.defi.execution.scenarios import (
    detect_claim_compound_blocker,
    detect_dust_below_threshold_blocker,
    detect_gas_missing_dst_blocker,
    detect_lst_already_deposited_blocker,
    detect_nft_lp_refinance_blocker,
    detect_partial_allowance_blocker,
    detect_price_impact_too_high_blocker,
    detect_v2_to_v3_migrate_blocker,
    detect_wallet_mismatch_blocker,
    scan_scenario_blockers,
)


def _make_step(
    *,
    index: int = 1,
    action: str = "supply",
    chain: str = "ethereum",
    asset_in: str = "USDC",
    amount_in: str = "100",
    protocol: str = "aave-v3",
    spender: str | None = None,
    snapshot: dict | None = None,
) -> ExecutionStepV3:
    tx = None
    if spender:
        tx = UnsignedStepTransaction(
            chain_kind="evm", chain_id=1, to=spender,
            data="0x", value="0x0", spender=spender,
        )
    s = make_step(
        index=index, action=action,
        title=f"{action} {asset_in}",
        description="", chain=chain, wallet="MetaMask",
        protocol=protocol, asset_in=asset_in, amount_in=amount_in,
        transaction=tx,
    )
    if snapshot is not None:
        s.snapshot = snapshot
    return s


# ── H07 — DUST_BELOW_THRESHOLD ─────────────────────────────────────────────
class TestDustBelowThreshold:
    def test_sub_dollar_stable_emits(self):
        step = _make_step(asset_in="USDC", amount_in="0.5")
        out = detect_dust_below_threshold_blocker(steps=[step])
        assert len(out) == 1
        assert out[0].code == "DUST_BELOW_THRESHOLD"

    def test_dollar_plus_does_not_emit(self):
        step = _make_step(asset_in="USDC", amount_in="100")
        out = detect_dust_below_threshold_blocker(steps=[step])
        assert out == []

    def test_resolver_fallback(self):
        # Non-stable token: must use resolver or snapshot.amount_usd
        step = _make_step(asset_in="WBTC", amount_in="0.000001")
        # With resolver returning 0.5 USD → dust
        out = detect_dust_below_threshold_blocker(
            steps=[step],
            amount_in_usd_resolver=lambda sym, amt, ch: 0.5,
        )
        assert len(out) == 1
        assert out[0].code == "DUST_BELOW_THRESHOLD"

    def test_snapshot_amount_usd_used(self):
        step = _make_step(asset_in="WBTC", amount_in="0.000001",
                          snapshot={"amount_usd": 0.7})
        out = detect_dust_below_threshold_blocker(steps=[step])
        assert len(out) == 1


# ── H08 — PARTIAL_ALLOWANCE_REMAINING ──────────────────────────────────────
class TestPartialAllowance:
    def test_partial_allowance_emits_blocker(self):
        spender = "0xAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAa"
        step = _make_step(action="supply", asset_in="USDC", amount_in="100",
                          spender=spender)
        inv = WalletInventory(
            evm_address="0x1111111111111111111111111111111111111111",
            allowances={("ethereum", "USDC", spender.lower()): Decimal("25")},
        )
        out = detect_partial_allowance_blocker(steps=[step], inventory=inv)
        assert len(out) == 1
        assert out[0].code == "PARTIAL_ALLOWANCE_REMAINING"

    def test_zero_allowance_does_not_emit_partial(self):
        spender = "0xBbBbBbBbBbBbBbBbBbBbBbBbBbBbBbBbBbBbBbBb"
        step = _make_step(action="supply", asset_in="USDC", amount_in="100",
                          spender=spender)
        inv = WalletInventory(
            evm_address="0x1111111111111111111111111111111111111111",
            allowances={("ethereum", "USDC", spender.lower()): Decimal("0")},
        )
        # Zero is NOT partial; preflight's `missing_allowance` handles it.
        out = detect_partial_allowance_blocker(steps=[step], inventory=inv)
        assert out == []

    def test_full_allowance_does_not_emit(self):
        spender = "0xCcCcCcCcCcCcCcCcCcCcCcCcCcCcCcCcCcCcCcCc"
        step = _make_step(action="supply", asset_in="USDC", amount_in="100",
                          spender=spender)
        inv = WalletInventory(
            evm_address="0x1111111111111111111111111111111111111111",
            allowances={("ethereum", "USDC", spender.lower()): Decimal("100")},
        )
        out = detect_partial_allowance_blocker(steps=[step], inventory=inv)
        assert out == []

    def test_usdt_quirk_in_cta(self):
        spender = "0xDdDdDdDdDdDdDdDdDdDdDdDdDdDdDdDdDdDdDdDd"
        step = _make_step(action="supply", asset_in="USDT", amount_in="100",
                          spender=spender)
        inv = WalletInventory(
            evm_address="0x1111111111111111111111111111111111111111",
            allowances={("ethereum", "USDT", spender.lower()): Decimal("25")},
        )
        out = detect_partial_allowance_blocker(steps=[step], inventory=inv)
        assert len(out) == 1
        assert "0" in out[0].cta and "USDT" in out[0].cta


# ── H09 — GAS_MISSING_DST → GAS_TOPUP_REQUIRED ─────────────────────────────
class TestGasMissingDst:
    def test_insufficient_dst_gas_emits(self):
        step = _make_step(chain="base", action="supply", asset_in="USDC")
        inv = WalletInventory(
            evm_address="0x1111111111111111111111111111111111111111",
            native_gas={"base": Decimal("0")},
        )
        out = detect_gas_missing_dst_blocker(
            steps=[step], inventory=inv, dst_chain="base",
        )
        assert len(out) == 1
        assert out[0].code == "GAS_TOPUP_REQUIRED"
        assert "ETH" in out[0].title  # base native gas symbol

    def test_sufficient_dst_gas_does_not_emit(self):
        step = _make_step(chain="base", action="supply", asset_in="USDC")
        inv = WalletInventory(
            evm_address="0x1111111111111111111111111111111111111111",
            native_gas={"base": Decimal("1")},
        )
        out = detect_gas_missing_dst_blocker(
            steps=[step], inventory=inv, dst_chain="base",
        )
        assert out == []

    def test_no_dst_chain_no_emit(self):
        step = _make_step()
        inv = WalletInventory(evm_address="0x0")
        out = detect_gas_missing_dst_blocker(
            steps=[step], inventory=inv, dst_chain=None,
        )
        assert out == []


# ── H10 — LST_ALREADY_DEPOSITED ────────────────────────────────────────────
class TestLstAlreadyDeposited:
    def test_lido_with_existing_steth(self):
        inv = WalletInventory(
            evm_address="0x1111111111111111111111111111111111111111",
            balances={("ethereum", "STETH"): Decimal("1.5")},
        )
        out = detect_lst_already_deposited_blocker(
            protocol="lido", action="stake", asset_in="ETH",
            inventory=inv, chain="ethereum",
        )
        assert len(out) == 1
        assert out[0].code == "LST_ALREADY_DEPOSITED"
        assert "STETH" in out[0].title

    def test_lido_without_steth_does_not_emit(self):
        inv = WalletInventory(
            evm_address="0x1111111111111111111111111111111111111111",
            balances={("ethereum", "STETH"): Decimal("0")},
        )
        out = detect_lst_already_deposited_blocker(
            protocol="lido", action="stake", asset_in="ETH",
            inventory=inv, chain="ethereum",
        )
        assert out == []

    def test_marinade_with_msol(self):
        inv = WalletInventory(
            solana_address="So11111111111111111111111111111111111111111",
            balances={("solana", "MSOL"): Decimal("3.0")},
        )
        out = detect_lst_already_deposited_blocker(
            protocol="marinade", action="stake", asset_in="SOL",
            inventory=inv, chain="solana",
        )
        assert len(out) == 1
        assert out[0].code == "LST_ALREADY_DEPOSITED"

    def test_non_lst_protocol_does_not_emit(self):
        inv = WalletInventory(
            evm_address="0x1111111111111111111111111111111111111111",
            balances={("ethereum", "AUSDC"): Decimal("100")},
        )
        out = detect_lst_already_deposited_blocker(
            protocol="aave-v3", action="supply", asset_in="USDC",
            inventory=inv, chain="ethereum",
        )
        assert out == []


# ── H11 — NFT_LP_REFINANCE_INCOMPLETE ──────────────────────────────────────
class TestNftLpRefinance:
    def test_refinance_with_only_supply_step_emits(self):
        # Adapter returned only a single supply step — refinance contract broken.
        step = _make_step(action="supply", protocol="uniswap-v3")
        extra = {"refinance": True, "token_id": "12345", "pool_symbol": "USDC-WETH"}
        out = detect_nft_lp_refinance_blocker(extra=extra, steps=[step])
        assert len(out) == 1
        assert out[0].code == "NFT_LP_REFINANCE_INCOMPLETE"
        assert "12345" in out[0].title

    def test_refinance_with_full_multi_step_does_not_emit(self):
        steps = [
            _make_step(index=1, action="collect_fees"),
            _make_step(index=2, action="close_position"),
            _make_step(index=3, action="open_position"),
        ]
        extra = {"refinance": True, "token_id": "999"}
        out = detect_nft_lp_refinance_blocker(extra=extra, steps=steps)
        assert out == []

    def test_no_refinance_flag_no_emit(self):
        step = _make_step()
        out = detect_nft_lp_refinance_blocker(extra={}, steps=[step])
        assert out == []


# ── H12 — CLAIM_COMPOUND_INCOMPLETE ────────────────────────────────────────
class TestClaimCompound:
    def test_claim_compound_with_only_one_step_emits(self):
        step = _make_step(action="supply", asset_in="AAVE")
        extra = {"claim_compound": True, "reward_token": "AAVE",
                 "stake_target": "stkaave"}
        out = detect_claim_compound_blocker(extra=extra, steps=[step])
        assert len(out) == 1
        assert out[0].code == "CLAIM_COMPOUND_INCOMPLETE"
        assert "AAVE" in out[0].title

    def test_claim_compound_with_both_steps_does_not_emit(self):
        steps = [
            _make_step(index=1, action="claim"),
            _make_step(index=2, action="stake"),
        ]
        extra = {"claim_compound": True, "reward_token": "AAVE"}
        out = detect_claim_compound_blocker(extra=extra, steps=steps)
        assert out == []


# ── H14 — V2_TO_V3_MIGRATE_INCOMPLETE ──────────────────────────────────────
class TestV2ToV3Migrate:
    def test_migrate_with_single_supply_emits(self):
        step = _make_step(action="supply", asset_in="LP")
        extra = {"migrate_v2_to_v3": True, "v2_pool": "USDC-WETH",
                 "v3_protocol": "uniswap-v3"}
        out = detect_v2_to_v3_migrate_blocker(extra=extra, steps=[step])
        assert len(out) == 1
        assert out[0].code == "V2_TO_V3_MIGRATE_INCOMPLETE"

    def test_migrate_with_remove_and_add_does_not_emit(self):
        steps = [
            _make_step(index=1, action="remove_liquidity"),
            _make_step(index=2, action="add_liquidity"),
        ]
        extra = {"migrate_v2_to_v3": True}
        out = detect_v2_to_v3_migrate_blocker(extra=extra, steps=steps)
        assert out == []


# ── H15 — WALLET_CHAIN_MISMATCH ────────────────────────────────────────────
class TestWalletMismatch:
    def test_solana_wallet_on_evm_plan_emits(self):
        # Solana base58 address (32-44 chars no 0x)
        sol_addr = "So11111111111111111111111111111111111111112"
        out = detect_wallet_mismatch_blocker(
            user_address=sol_addr, chain="ethereum",
        )
        assert len(out) == 1
        assert out[0].code == "WALLET_CHAIN_MISMATCH"

    def test_evm_wallet_on_solana_plan_emits(self):
        evm_addr = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        out = detect_wallet_mismatch_blocker(
            user_address=evm_addr, chain="solana",
        )
        assert len(out) == 1
        assert out[0].code == "WALLET_CHAIN_MISMATCH"

    def test_evm_wallet_on_evm_plan_no_emit(self):
        evm_addr = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        out = detect_wallet_mismatch_blocker(
            user_address=evm_addr, chain="ethereum",
        )
        assert out == []

    def test_explicit_wallet_kind_hint_emits(self):
        # Caller stashed wallet_chain_kind explicitly
        evm_addr = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        out = detect_wallet_mismatch_blocker(
            user_address=evm_addr, chain="ethereum",
            wallet_chain_kind="solana",
        )
        assert len(out) == 1


# ── E15 — PRICE_IMPACT_TOO_HIGH ────────────────────────────────────────────
class TestPriceImpactTooHigh:
    def test_500_bps_emits_blocker(self):
        step = _make_step(snapshot={"price_impact_bps": 500})
        out = detect_price_impact_too_high_blocker(steps=[step])
        assert len(out) == 1
        assert out[0].code == "PRICE_IMPACT_TOO_HIGH"

    def test_10000_bps_emits_blocker(self):
        step = _make_step(snapshot={"price_impact_bps": 10000})
        out = detect_price_impact_too_high_blocker(steps=[step])
        assert len(out) == 1
        assert "10000" in out[0].title

    def test_499_bps_does_not_emit(self):
        step = _make_step(snapshot={"price_impact_bps": 499})
        out = detect_price_impact_too_high_blocker(steps=[step])
        assert out == []

    def test_alternative_field_names(self):
        # priceImpactBps (LI.FI camelCase)
        step1 = _make_step(snapshot={"priceImpactBps": 600})
        out1 = detect_price_impact_too_high_blocker(steps=[step1])
        assert len(out1) == 1
        # price_impact_pct (V3 quoter fractional)
        step2 = _make_step(snapshot={"price_impact_pct": 0.07})  # 700 bps
        out2 = detect_price_impact_too_high_blocker(steps=[step2])
        assert len(out2) == 1

    def test_no_field_no_emit(self):
        step = _make_step(snapshot={})
        out = detect_price_impact_too_high_blocker(steps=[step])
        assert out == []


# ── KNOWN_BLOCKER_CODES — every code registered ───────────────────────────
class TestBlockerCodesRegistered:
    def test_all_new_codes_in_known(self):
        for code in (
            "PARTIAL_ALLOWANCE_REMAINING",
            "LST_ALREADY_DEPOSITED",
            "NFT_LP_REFINANCE_INCOMPLETE",
            "CLAIM_COMPOUND_INCOMPLETE",
            "V2_TO_V3_MIGRATE_INCOMPLETE",
            "PRICE_IMPACT_TOO_HIGH",
            "COMPOSED_PLAN_INCOMPLETE_TX",
            "GAS_TOPUP_REQUIRED",
            "DUST_BELOW_THRESHOLD",
        ):
            assert code in KNOWN_BLOCKER_CODES, (
                f"{code} missing from KNOWN_BLOCKER_CODES — runtime will "
                f"silently drop the blocker."
            )


# ── Aggregator — scan_scenario_blockers ───────────────────────────────────
class TestScanAggregator:
    def test_aggregator_returns_union(self):
        # Step with sub-$1 USDC AND high price impact AND refinance flag.
        step = _make_step(
            asset_in="USDC", amount_in="0.5",
            snapshot={"price_impact_bps": 600},
        )
        out = scan_scenario_blockers(
            steps=[step], extra={"refinance": True, "token_id": "1"},
            protocol="uniswap-v3", action="supply", asset_in="USDC",
            chain="ethereum",
        )
        codes = {b.code for b in out}
        assert "DUST_BELOW_THRESHOLD" in codes
        assert "PRICE_IMPACT_TOO_HIGH" in codes
        assert "NFT_LP_REFINANCE_INCOMPLETE" in codes

    def test_aggregator_empty_when_nothing_triggers(self):
        step = _make_step(asset_in="USDC", amount_in="100")
        out = scan_scenario_blockers(
            steps=[step], extra={},
            protocol="aave-v3", action="supply", asset_in="USDC",
            chain="ethereum",
        )
        # Should be empty — single-chain Aave supply with $100 USDC and no
        # weird extras.
        codes = {b.code for b in out}
        assert "DUST_BELOW_THRESHOLD" not in codes
        assert "PRICE_IMPACT_TOO_HIGH" not in codes
        assert "NFT_LP_REFINANCE_INCOMPLETE" not in codes
        assert "CLAIM_COMPOUND_INCOMPLETE" not in codes
        assert "V2_TO_V3_MIGRATE_INCOMPLETE" not in codes
