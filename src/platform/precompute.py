"""Fast-lane precompute helpers for opportunity analysis payloads."""

from __future__ import annotations

from typing import Any, Dict


def normalize_lane_status(payload: Dict[str, Any]) -> str:
    status = str(payload.get("status") or "running").lower()
    if status in {"failed", "error", "cancelled", "canceled", "aborted", "timeout", "timed_out"}:
        return "failed"
    if status == "completed":
        return "completed"

    stage = str((payload.get("progress") or {}).get("stage") or "").lower()
    if stage in {"enrich", "enriching", "materialize", "synthesis"}:
        return "enriching"
    return "scanning"


def build_quick_view(payload: Dict[str, Any]) -> Dict[str, Any]:
    provisional = payload.get("provisional_shortlist") or []
    if not provisional:
        provisional = (payload.get("result") or {}).get("top_opportunities") or []
    top = provisional[0] if provisional else {}
    return {
        "candidate_count": len(provisional),
        "top_candidate": {
            "id": top.get("id"),
            "symbol": top.get("symbol"),
            "chain": top.get("chain"),
            "score": top.get("shortlist_score") or (top.get("summary") or {}).get("opportunity_score"),
        },
    }


def build_fast_lane_snapshot(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": normalize_lane_status(payload),
        "data": {
            "analysis_id": payload.get("analysis_id"),
            "quick_view": build_quick_view(payload),
        },
    }
