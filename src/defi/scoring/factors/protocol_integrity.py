from __future__ import annotations

from typing import Any, Dict, Sequence

from src.defi.evidence import clamp


def score_protocol_integrity(context: Dict[str, Any]) -> Dict[str, Any]:
    protocol_safety = float(context.get("protocol_safety", 60))
    docs = context.get("docs") or {}
    dependencies: Sequence[Dict[str, Any]] = context.get("dependencies") or []
    docs_bonus = 6 if docs.get("available") and not docs.get("placeholder") else -8
    if docs.get("has_timelock_mentions"):
        docs_bonus += 4
    if docs.get("has_multisig_mentions"):
        docs_bonus += 3
    if docs.get("has_admin_mentions") and not docs.get("has_timelock_mentions"):
        docs_bonus -= 8
    dependency_penalty = sum(float(dep.get("risk_score", 45)) * 0.08 for dep in dependencies[:6])
    score = clamp(protocol_safety + docs_bonus - dependency_penalty)
    return {"score": score, "burden": clamp(100 - score), "notes": ["Protocol safety, docs posture, and dependency inheritance."]}
