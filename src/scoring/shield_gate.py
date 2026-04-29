from __future__ import annotations

from typing import Any

from src.api.schemas.agent import ShieldBlock


MALICIOUS_ADDRESSES = {"0x000000000000000000000000000000000000dead"}
ALLOWED_SPENDERS = {
    "enso",
    "jupiter",
    "uniswap",
    "pancakeswap",
    "debridge",
    "stargate",
    "layerzero",
}


def shield_for_transaction(tx: dict[str, Any]) -> ShieldBlock:
    reasons: list[str] = []
    severity = 0

    to_address = str(tx.get("to") or tx.get("recipient") or "").lower()
    if to_address in MALICIOUS_ADDRESSES:
        reasons.append("Known malicious destination")
        severity = max(severity, 4)

    slippage_bps = int(tx.get("slippage_bps") or tx.get("slippageBps") or 0)
    if slippage_bps > 1500:
        reasons.append("Critical slippage")
        severity = max(severity, 4)
    elif slippage_bps > 500:
        reasons.append("High slippage")
        severity = max(severity, 3)
    elif slippage_bps > 100:
        reasons.append("Elevated slippage")
        severity = max(severity, 1)

    spender = str(tx.get("spender") or tx.get("router") or "").lower()
    if spender and not any(allowed in spender for allowed in ALLOWED_SPENDERS):
        reasons.append("Unrecognized spender")
        severity = max(severity, 2)

    if tx.get("approval_amount") in {"max", "MAX_UINT256"}:
        reasons.append("Infinite approval")
        severity = max(severity, 1)

    verdicts = {
        0: ("SAFE", "A"),
        1: ("CAUTION", "B"),
        2: ("RISKY", "C"),
        3: ("RISKY", "D"),
        4: ("SCAM", "F"),
    }
    verdict, grade = verdicts[severity]
    return ShieldBlock(verdict=verdict, grade=grade, reasons=reasons)
