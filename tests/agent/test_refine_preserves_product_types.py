"""Pin test for A19/T2 regression — refinement turn drops product_types
filter when prior card items[].product_type uses the TAXONOMY-style values
emitted by src/defi/opportunity_taxonomy.py ('single_asset_staking',
'lending_supply_like', etc.) rather than the friendly forms ('staking',
'lending').

Surfaced by matrix Pass A A19_marinade_sol turn 2: turn 1 asked for SOL
staking (product_types=['staking'] derived/applied), turn 2 said "show me
higher yield" and got HIGH-risk gmtrade SOL-USDC perp pools because the
product_types filter was lost.

Root cause: _last_defi_card_constraints._PRODUCT_TYPE_NORM only mapped the
friendly forms ('liquid staking' / 'staking' / 'lending' / 'vault' / ...)
but the actual items[].product_type values stored in defi_opportunities
card payloads are the taxonomy outputs ('single_asset_staking' /
'lending_supply_like' / 'single_asset_vault' / '*_lp' /
'single_asset_yield'). Lookup missed → no product_types in derived
constraints → refine setdefault to ['pool','farm','vault','lending']
(no 'staking').

Fix: extend _PRODUCT_TYPE_NORM with the taxonomy values. Pin tests here
make sure a future refactor can't silently regress.
"""
from __future__ import annotations

from src.agent.simple_runtime import (
    _last_defi_card_constraints,
    _synthesize_refine_search_args,
)


# --- A19/T2 root cause: taxonomy values must map to search vocabulary ---


def test_constraints_derive_staking_from_single_asset_staking_items() -> None:
    """Marinade + Jito + bSOL items carry product_type='single_asset_staking'
    (taxonomy output). Derivation must map to 'staking' so refine inherits."""
    history_cards = [
        {
            "card_type": "defi_opportunities",
            "payload": {
                "chains": ["solana"],
                "items": [
                    {"protocol": "marinade", "product_type": "single_asset_staking"},
                    {"protocol": "jito", "product_type": "single_asset_staking"},
                ],
            },
        }
    ]
    out = _last_defi_card_constraints(history_cards)
    assert out.get("product_types") == ["staking"], (
        f"expected ['staking'], got {out.get('product_types')!r}"
    )


def test_constraints_derive_lending_from_lending_supply_like() -> None:
    """Aave-v3 / Compound-v3 supply items carry
    product_type='lending_supply_like'."""
    history_cards = [
        {
            "card_type": "defi_opportunities",
            "payload": {
                "items": [
                    {"protocol": "aave-v3", "product_type": "lending_supply_like"},
                    {"protocol": "compound-v3", "product_type": "lending_supply_like"},
                ],
            },
        }
    ]
    out = _last_defi_card_constraints(history_cards)
    assert out.get("product_types") == ["lending"]


def test_constraints_derive_vault_from_single_asset_vault() -> None:
    history_cards = [
        {
            "card_type": "defi_opportunities",
            "payload": {
                "items": [
                    {"product_type": "single_asset_vault"},
                ],
            },
        }
    ]
    out = _last_defi_card_constraints(history_cards)
    assert out.get("product_types") == ["vault"]


def test_constraints_derive_pool_from_lp_taxonomy_variants() -> None:
    """All *_lp taxonomy variants map to 'pool' so an LP-heavy prior card
    keeps the user on LP-style products on refine."""
    for lp_kind in (
        "stable_lp",
        "incentivized_stable_lp",
        "crypto_stable_lp",
        "incentivized_crypto_stable_lp",
        "crypto_crypto_lp",
        "incentivized_crypto_crypto_lp",
    ):
        history_cards = [
            {
                "card_type": "defi_opportunities",
                "payload": {"items": [{"product_type": lp_kind}]},
            }
        ]
        out = _last_defi_card_constraints(history_cards)
        assert out.get("product_types") == ["pool"], (
            f"{lp_kind} should map to 'pool', got {out.get('product_types')!r}"
        )


# --- End-to-end: refine inherits product_types so silent message keeps it ---


def test_refine_preserves_staking_when_message_silent_on_type() -> None:
    """A19/T2 reproduction: turn 1 SOL staking → turn 2 'show me higher
    yield' must keep product_types=['staking'] (NOT default to
    ['pool','farm','vault','lending'] which would surface perp pools)."""
    history_cards = [
        {
            "card_type": "defi_opportunities",
            "payload": {
                "chains": ["solana"],
                "items": [
                    {"protocol": "marinade", "product_type": "single_asset_staking"},
                    {"protocol": "jito", "product_type": "single_asset_staking"},
                    {"protocol": "sanctum", "product_type": "single_asset_staking"},
                ],
            },
        }
    ]
    args = _synthesize_refine_search_args("show me higher yield", history_cards)
    assert args is not None
    assert args.get("product_types") == ["staking"], (
        "refine on silent-message turn MUST preserve prior staking filter; "
        f"got {args.get('product_types')!r}"
    )


def test_refine_preserves_lending_when_message_silent_on_type() -> None:
    history_cards = [
        {
            "card_type": "defi_opportunities",
            "payload": {
                "chains": ["base"],
                "items": [
                    {"protocol": "aave-v3", "product_type": "lending_supply_like"},
                    {"protocol": "compound-v3", "product_type": "lending_supply_like"},
                ],
            },
        }
    ]
    args = _synthesize_refine_search_args("higher yield only", history_cards)
    assert args is not None
    assert args.get("product_types") == ["lending"]


def test_refine_no_prior_returns_none() -> None:
    """Sanity: synth returns None when no prior defi card exists."""
    assert _synthesize_refine_search_args("show me higher yield", None) is None
    assert _synthesize_refine_search_args("show me higher yield", []) is None
