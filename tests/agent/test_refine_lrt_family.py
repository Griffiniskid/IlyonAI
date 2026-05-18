"""Pin tests for LRT/LST family refinement, protocol+asset co-occurrence
preservation, drill-into-top-pool no-amount handler, and amount override on
refinement turns.

Bug surfaces (v6 hand-read continuation):
  1. "switch to LRT" / "filter to liquid staking" never matched any refine
     regex — synth fell through and the LLM contextual fallback fabricated.
  2. "Spark DAI" lost asset_hint=DAI because protocol_filter handler nulled
     it, surfacing Uniswap/Balancer instead of Spark sDAI vault.
  3. "drill into top pool" without amount fell to LLM mode.
  4. "Use 150 USDC" on a refine turn kept emitting the prior $1000 split
     because the synth read base_amount from the prior card and never
     re-parsed the new message for an explicit override.

This module pins the runtime fix at the regex / synth boundary so a future
refactor can't silently regress.
"""
from __future__ import annotations

from src.agent.simple_runtime import (
    _LRT_FAMILY,
    _LRT_LST_REFINE_RE,
    _LST_FAMILY,
    _SINGLE_POOL_PICK_RE,
    _synthesize_refine_execution_args,
    _synthesize_refine_search_args,
)


def _prior_execution_card(
    *,
    chain: str = "ethereum",
    protocol: str = "aave-v3",
    asset: str = "USDC",
    amount: float = 1000.0,
) -> dict:
    return {
        "card_type": "pool_deposit_v3",
        "payload": {
            "chain": chain,
            "protocol": protocol,
            "action": "supply",
            "asset_in": asset,
            "amount": amount,
        },
    }


def _prior_defi_card(items: list[dict]) -> dict:
    return {
        "card_type": "defi_opportunities",
        "payload": {
            "items": items,
            "chains": ["ethereum"],
            "risk_levels": ["LOW"],
            "product_types": ["lending"],
        },
    }


# --- BUG 1 part 1: LRT/LST family regex matches family-switch phrasing -----


def test_switch_to_lrt_expands_family() -> None:
    """'switch to LRT' must match _LRT_LST_REFINE_RE so synth fires."""
    m = _LRT_LST_REFINE_RE.search("switch to LRT")
    assert m is not None
    assert m.group("fam").lower() == "lrt"


def test_filter_to_liquid_staking_matches() -> None:
    m = _LRT_LST_REFINE_RE.search("filter to liquid staking")
    assert m is not None


def test_only_lst_matches() -> None:
    m = _LRT_LST_REFINE_RE.search("only LST")
    assert m is not None


def test_lrt_family_constants_present() -> None:
    """Family sets must include the canonical names listed in the spec."""
    assert "renzo" in _LRT_FAMILY
    assert "kelp" in _LRT_FAMILY
    assert "swell" in _LRT_FAMILY
    assert "puffer" in _LRT_FAMILY
    assert "etherfi" in _LRT_FAMILY
    assert "eigenlayer" in _LRT_FAMILY
    assert "lido" in _LST_FAMILY
    assert "rocket-pool" in _LST_FAMILY
    assert "stader" in _LST_FAMILY


# --- BUG 1 part 4: execution-arg synth carries family allowlist -----------


def test_switch_to_lrt_sets_protocol_family_on_execution_args() -> None:
    prior = _prior_execution_card(protocol="lido", asset="ETH", amount=1.0)
    result = _synthesize_refine_execution_args("switch to LRT", [prior])
    assert result is not None, "synth must fire on LRT family refine"
    _, args = result
    extra = args.get("extra") or {}
    assert extra.get("protocol_family") == "lrt"
    assert "renzo" in (extra.get("protocol_allowlist") or [])


def test_switch_to_lst_sets_protocol_family_on_execution_args() -> None:
    prior = _prior_execution_card(protocol="aave-v3", asset="ETH", amount=1.0)
    result = _synthesize_refine_execution_args("filter to liquid staking", [prior])
    assert result is not None
    _, args = result
    extra = args.get("extra") or {}
    assert extra.get("protocol_family") == "lst"
    assert "lido" in (extra.get("protocol_allowlist") or [])


# --- BUG 1 part 3: protocol + asset co-occurrence preserves BOTH ----------


def test_spark_dai_preserves_asset_and_protocol() -> None:
    """Message 'Spark DAI' on a search-refine yields both protocol=spark
    AND asset_hint=DAI so the search hits the Spark sDAI vault, not a
    generic DAI pool ranked by sentinel score across all protocols.
    """
    prior = _prior_defi_card([
        {"pool_id": "p1", "product_type": "lending"},
    ])
    args = _synthesize_refine_search_args("Spark DAI", [prior])
    assert args is not None
    assert args.get("asset_hint") == "DAI"
    assert args.get("protocol_filter") == "spark"


def test_aave_usdc_preserves_asset_and_protocol() -> None:
    prior = _prior_defi_card([
        {"pool_id": "p1", "product_type": "lending"},
    ])
    args = _synthesize_refine_search_args("Aave USDC", [prior])
    assert args is not None
    assert args.get("asset_hint") == "USDC"
    assert (args.get("protocol_filter") or "").startswith("aave")


# --- BUG 1 part 5: drill-into-top-pool without amount ---------------------


def test_drill_into_top_pool_no_amount() -> None:
    """'drill into top pool' on a refine turn picks the prior top pool by
    pool_id and does NOT require an amount to fire synth.
    """
    assert _SINGLE_POOL_PICK_RE.search("drill into top pool") is not None
    assert _SINGLE_POOL_PICK_RE.search("the first one") is not None
    assert _SINGLE_POOL_PICK_RE.search("the top one") is not None
    prior_search = _prior_defi_card([
        {"pool_id": "top-pool-abc", "product_type": "lending"},
    ])
    prior_exec = _prior_execution_card(amount=500.0)
    result = _synthesize_refine_execution_args(
        "drill into top pool",
        [prior_search, prior_exec],
    )
    assert result is not None, "drill-into-top-pool must fire synth"
    _, args = result
    extra = args.get("extra") or {}
    assert extra.get("pool_id") == "top-pool-abc"
    assert extra.get("pick_top_pool") is True


# --- BUG 2: amount override on a refinement turn --------------------------


def test_use_150_usdc_overrides_prior_amount() -> None:
    """User saying 'Use 150 USDC' on a refinement turn after a $1000 prior
    plan must override base_amount=1000 → 150.
    """
    prior = _prior_execution_card(
        protocol="aave-v3", asset="USDC", amount=1000.0,
    )
    result = _synthesize_refine_execution_args("Use 150 USDC", [prior])
    assert result is not None
    _, args = result
    assert args.get("amount_in") == 150.0
    assert args.get("asset_in") == "USDC"


def test_allocate_2k_overrides_with_suffix() -> None:
    prior = _prior_execution_card(
        protocol="aave-v3", asset="USDC", amount=100.0,
    )
    result = _synthesize_refine_execution_args("allocate 2k USDC", [prior])
    assert result is not None
    _, args = result
    assert args.get("amount_in") == 2000.0
    assert args.get("asset_in") == "USDC"


def test_deploy_with_explicit_amount_overrides() -> None:
    prior = _prior_execution_card(
        protocol="lido", asset="ETH", amount=1.0,
    )
    result = _synthesize_refine_execution_args("deploy 0.5 ETH", [prior])
    assert result is not None
    _, args = result
    assert args.get("amount_in") == 0.5
    assert args.get("asset_in") == "ETH"
