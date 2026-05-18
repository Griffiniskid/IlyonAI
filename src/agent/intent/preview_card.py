"""V7 §1 gap — typed PreviewCard schema with 6 panels.

Spec §1 requires the LP planner emit a typed preview card carrying six
distinct panels (summary, route, risk, cost, freshness, audit) so the
frontend can render each one without re-parsing the LLM prose.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


__all__ = ["PreviewCard", "PREVIEW_PANEL_NAMES"]


PREVIEW_PANEL_NAMES: tuple[str, ...] = (
    "summary_panel",
    "route_panel",
    "risk_panel",
    "cost_panel",
    "freshness_panel",
    "audit_panel",
)


@dataclass
class PreviewCard:
    """Typed envelope rendered by the chat UI before user clicks Confirm."""

    kind: str = "preview"
    summary_panel: dict[str, Any] = field(default_factory=dict)
    route_panel: dict[str, Any] = field(default_factory=dict)
    risk_panel: dict[str, Any] = field(default_factory=dict)
    cost_panel: dict[str, Any] = field(default_factory=dict)
    freshness_panel: dict[str, Any] = field(default_factory=dict)
    audit_panel: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "summary_panel": dict(self.summary_panel),
            "route_panel": dict(self.route_panel),
            "risk_panel": dict(self.risk_panel),
            "cost_panel": dict(self.cost_panel),
            "freshness_panel": dict(self.freshness_panel),
            "audit_panel": dict(self.audit_panel),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PreviewCard":
        return cls(
            kind=payload.get("kind", "preview"),
            summary_panel=dict(payload.get("summary_panel") or {}),
            route_panel=dict(payload.get("route_panel") or {}),
            risk_panel=dict(payload.get("risk_panel") or {}),
            cost_panel=dict(payload.get("cost_panel") or {}),
            freshness_panel=dict(payload.get("freshness_panel") or {}),
            audit_panel=dict(payload.get("audit_panel") or {}),
        )
