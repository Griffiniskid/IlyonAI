"""§13 spec-scenario blocker emitters.

Pass C 58517bf hand-read found nine §13 spec scenarios (H07/H08/H09/H10/H11/
H12/H14/H15 + E15 price-impact) where the detector already extracted the
intent (or the inventory already carried the signal) but the build path
silently emitted a signable plan instead of a structured blocker. Each
emitter here returns a list of `ExecutionBlocker` instances; the
build_yield_execution_plan composed-plan branch calls them in sequence
BEFORE running `assert_signable_composed_plan` so an incomplete-scenario
plan never reaches the user.
"""
from __future__ import annotations

from src.defi.execution.scenarios.scenario_blockers import (
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

__all__ = [
    "detect_claim_compound_blocker",
    "detect_dust_below_threshold_blocker",
    "detect_gas_missing_dst_blocker",
    "detect_lst_already_deposited_blocker",
    "detect_nft_lp_refinance_blocker",
    "detect_partial_allowance_blocker",
    "detect_price_impact_too_high_blocker",
    "detect_v2_to_v3_migrate_blocker",
    "detect_wallet_mismatch_blocker",
    "scan_scenario_blockers",
]
