"""Pin _last_defi_card_constraints product_types derivation from items.

v4-A07 / v4-A19 / v4-A20 caught: refine paths ('Spark only', 'Marinade
only', 'Jito only') lost the product_types filter because the
defi_opportunities card payload doesn't store product_types directly.
Derive product_types from items[].product_type so refine searches keep
the filter the original turn established.
"""
from __future__ import annotations


def test_constraints_derive_liquid_staking_from_items():
    from src.agent.simple_runtime import _last_defi_card_constraints

    history_cards = [
        {
            "card_type": "defi_opportunities",
            "payload": {
                "chains": ["solana"],
                "items": [
                    {"protocol": "marinade", "product_type": "liquid staking"},
                    {"protocol": "jito", "product_type": "liquid staking"},
                ],
            },
        }
    ]
    out = _last_defi_card_constraints(history_cards)
    assert out["product_types"] == ["liquid_staking"]
    assert out["chains"] == ["solana"]


def test_constraints_derive_lending_from_items():
    from src.agent.simple_runtime import _last_defi_card_constraints

    history_cards = [
        {
            "card_type": "defi_opportunities",
            "payload": {
                "chains": ["base"],
                "items": [
                    {"protocol": "aave-v3", "product_type": "lending"},
                    {"protocol": "compound-v3", "product_type": "lending"},
                ],
            },
        }
    ]
    out = _last_defi_card_constraints(history_cards)
    assert out["product_types"] == ["lending"]


def test_constraints_derive_mixed_kinds():
    from src.agent.simple_runtime import _last_defi_card_constraints

    history_cards = [
        {
            "card_type": "defi_opportunities",
            "payload": {
                "items": [
                    {"product_type": "lending"},
                    {"product_type": "vault"},
                ],
            },
        }
    ]
    out = _last_defi_card_constraints(history_cards)
    assert set(out["product_types"]) == {"lending", "vault"}


def test_constraints_payload_product_types_wins_over_derived():
    from src.agent.simple_runtime import _last_defi_card_constraints

    history_cards = [
        {
            "card_type": "defi_opportunities",
            "payload": {
                "product_types": ["staking"],
                "items": [
                    {"product_type": "lending"},
                ],
            },
        }
    ]
    out = _last_defi_card_constraints(history_cards)
    assert out["product_types"] == ["staking"]


def test_constraints_no_card_returns_empty():
    from src.agent.simple_runtime import _last_defi_card_constraints

    assert _last_defi_card_constraints(None) == {}
    assert _last_defi_card_constraints([]) == {}
