from __future__ import annotations

from typing import Any, Dict

from src.defi.evidence import build_confidence_report


def score_confidence(kind: str, candidate: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    docs = context.get("docs") or {}
    history = context.get("history") or {}
    dependencies = context.get("dependencies") or []
    report = build_confidence_report(
        required_fields=["kind", "product_type", "apr", "tvl", "docs", "history", "dependencies"],
        present_fields=[
            "kind" if kind else "",
            "product_type" if candidate.get("product_type") else "",
            "apr" if (candidate.get("apy") is not None or candidate.get("apy_supply") is not None) else "",
            "tvl" if (candidate.get("tvl_usd") or candidate.get("tvlUsd")) else "",
            "docs" if docs.get("available") and not docs.get("placeholder") else "",
            "history" if history.get("available") else "",
            "dependencies" if dependencies else "",
        ],
        source_count=sum(1 for source in [candidate, docs, history, dependencies] if source),
        freshness_hours=docs.get("freshness_hours"),
        notes=[],
    )
    if not report["notes"]:
        report["notes"] = ["Confidence reflects evidence coverage, freshness, and dependency visibility."]
    return {"score": report["score"], "burden": 100 - report["score"], "report": report, "notes": report["notes"]}
