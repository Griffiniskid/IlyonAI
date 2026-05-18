"""V7 §1 — pin tests for PreviewCard 6-panel schema."""
from __future__ import annotations

from src.agent.intent.preview_card import PreviewCard, PREVIEW_PANEL_NAMES


def test_six_panel_names():
    assert PREVIEW_PANEL_NAMES == (
        "summary_panel",
        "route_panel",
        "risk_panel",
        "cost_panel",
        "freshness_panel",
        "audit_panel",
    )


def test_default_card_has_all_panels():
    card = PreviewCard()
    assert card.kind == "preview"
    for panel in PREVIEW_PANEL_NAMES:
        assert hasattr(card, panel)
        assert getattr(card, panel) == {}


def test_to_dict_round_trip():
    card = PreviewCard(
        summary_panel={"action": "supply"},
        route_panel={"hops": 1},
        risk_panel={"il_pct": 0.5},
        cost_panel={"gas_usd": 2.34},
        freshness_panel={"sim_at": 1234567890},
        audit_panel={"chain_id": "0xabc"},
    )
    payload = card.to_dict()
    rt = PreviewCard.from_dict(payload)
    assert rt == card


def test_partial_payload_fills_defaults():
    rt = PreviewCard.from_dict({"summary_panel": {"k": "v"}})
    assert rt.summary_panel == {"k": "v"}
    assert rt.route_panel == {}
    assert rt.kind == "preview"
