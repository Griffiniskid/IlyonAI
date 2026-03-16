"""Evidence, dependency, and confidence helpers for DeFi intelligence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

from src.defi.entities import ConfidenceReport, DependencyEdge

BRIDGED_SYMBOL_MARKERS = ("USDBC", "AXL", "WORMHOLE", "BRIDGED", "EZETH", "WEETH", "WSTETH", "CBBTC", "WBTC")


def clamp(value: float, lower: float = 0, upper: float = 100) -> int:
    return int(max(lower, min(upper, round(value))))


def risk_level_from_score(score: int) -> str:
    if score >= 55:
        return "HIGH"
    if score >= 30:
        return "MEDIUM"
    return "LOW"


def parse_age_hours(date_str: Optional[str]) -> Optional[float]:
    if not date_str:
        return None
    text = date_str.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return max(0.0, (now - dt).total_seconds() / 3600)


def build_dependency_edges(
    kind: str,
    chain: str,
    protocol_name: str,
    assets: Sequence[Dict[str, Any]],
    docs_profile: Optional[Dict[str, Any]] = None,
    incidents: Optional[Sequence[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    docs_profile = docs_profile or {}
    incidents = incidents or []
    dependencies: List[DependencyEdge] = [
        DependencyEdge(
            key="protocol-core",
            name=protocol_name,
            dependency_type="protocol",
            risk_score=clamp(40 + (len(incidents) * 12)),
            confidence_score=78 if docs_profile.get("available") else 58,
            source="internal",
            freshness_hours=docs_profile.get("freshness_hours"),
            notes="Core protocol dependency for the capital path.",
        )
    ]

    for asset in assets:
        symbol = str(asset.get("symbol") or "Unknown")
        quality = clamp(asset.get("quality_score") or 50)
        role = str(asset.get("role") or "asset")
        dependencies.append(
            DependencyEdge(
                key=f"asset-{role}-{symbol.lower()}",
                name=symbol,
                dependency_type=role,
                risk_score=100 - quality,
                confidence_score=clamp(asset.get("confidence_score") or 50),
                source=asset.get("source") or "heuristic",
                notes=asset.get("thesis") or f"Inherited {role} risk from asset quality.",
            )
        )
        upper = symbol.upper()
        if any(marker in upper for marker in BRIDGED_SYMBOL_MARKERS):
            dependencies.append(
                DependencyEdge(
                    key=f"bridge-{symbol.lower()}",
                    name=f"{symbol} bridge wrapper",
                    dependency_type="bridge",
                    risk_score=58 if "USDB" in upper else 48,
                    confidence_score=54,
                    source="heuristic",
                    notes="Wrapper or bridged-asset dependency introduces settlement and redemption risk.",
                )
            )

    if kind == "lending" or docs_profile.get("has_oracle_mentions"):
        dependencies.append(
            DependencyEdge(
                key="oracle-layer",
                name="Oracle layer",
                dependency_type="oracle",
                risk_score=36 if docs_profile.get("has_oracle_mentions") else 48,
                confidence_score=66,
                source="docs+heuristic" if docs_profile.get("has_oracle_mentions") else "heuristic",
                notes="Lending and structured positions inherit oracle freshness and pricing risk.",
            )
        )

    if docs_profile.get("has_bridge_mentions"):
        dependencies.append(
            DependencyEdge(
                key="cross-chain-surface",
                name="Cross-chain surface",
                dependency_type="bridge",
                risk_score=52,
                confidence_score=68,
                source="docs",
                notes="Protocol docs reference cross-chain or bridge dependencies.",
            )
        )

    unique: Dict[str, Dict[str, Any]] = {}
    for dependency in dependencies:
        unique[dependency.key] = dependency.to_dict()
    return list(unique.values())[:10]


def build_confidence_report(
    required_fields: Iterable[str],
    present_fields: Iterable[str],
    source_count: int,
    freshness_hours: Optional[float],
    notes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    required = [field for field in required_fields if field]
    present = {field for field in present_fields if field}
    missing = [field for field in required if field not in present]
    coverage_ratio = (len(required) - len(missing)) / max(len(required), 1)

    score = 10 + (coverage_ratio * 70) + min(source_count, 6) * 3
    if freshness_hours is not None:
        if freshness_hours <= 6:
            score += 10
        elif freshness_hours <= 24:
            score += 7
        elif freshness_hours <= 168:
            score += 3
        else:
            score -= 12
    else:
        score -= 6

    partial = bool(missing or coverage_ratio < 0.7)

    if coverage_ratio < 0.35:
        score = min(score, 25)
        label = "LOW"
    elif partial:
        score = min(score, 50)
        label = "PARTIAL"
    elif coverage_ratio < 0.9:
        score = min(max(score, 52), 75)
        label = "STANDARD"
    else:
        score = max(score, 76)
        label = "HIGH"

    report = ConfidenceReport(
        score=clamp(score),
        label=label,
        coverage_ratio=round(coverage_ratio, 3),
        source_count=source_count,
        freshness_hours=round(freshness_hours, 2) if freshness_hours is not None else None,
        partial_analysis=partial,
        missing_critical_fields=missing,
        notes=notes or ([] if not partial else ["Partial analysis due to missing critical fields."]),
    )
    return report.to_dict()
