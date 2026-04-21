"""Verifies web/types/agent.ts is in lockstep with src/api/schemas/agent.py.

Checks that every exported schema class in the Python module has a
corresponding interface/type declaration in agent.ts. Failing this check
means someone added a schema on one side without the other.

Usage:
    python scripts/gen_agent_types.py           # verify only (non-zero if drift)
    python scripts/gen_agent_types.py --check   # same, intended for CI
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "web" / "types" / "agent.ts"

# Ensure project root is importable when run as a standalone script
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REQUIRED_SYMBOLS = [
    "SentinelBlock", "ShieldBlock",
    "AllocationPosition", "AllocationPayload", "SwapQuotePayload",
    "PoolPayload", "TokenPayload", "PositionPayload", "PlanStep",
    "PlanPayload", "BalancePayload", "BridgePayload", "StakePayload",
    "MarketOverviewPayload", "PairListPayload",
    "AllocationCard", "SwapQuoteCard", "PoolCard", "TokenCard",
    "PositionCard", "PlanCard", "BalanceCard", "BridgeCard",
    "StakeCard", "MarketOverviewCard", "PairListCard",
    "CardType", "AgentCard", "ToolError", "ToolEnvelope",
    "ThoughtFrame", "ToolFrame", "ObservationFrame", "CardFrame",
    "FinalFrame", "DoneFrame", "SSEFrame",
]


def verify() -> list[str]:
    errs: list[str] = []
    if not TARGET.exists():
        return [f"missing file: {TARGET}"]
    content = TARGET.read_text()
    for sym in REQUIRED_SYMBOLS:
        if sym not in content:
            errs.append(f"agent.ts missing symbol: {sym}")

    try:
        from src.api.schemas import agent as mod
    except Exception as exc:
        errs.append(f"cannot import schemas: {exc}")
        return errs

    py_classes = {
        name for name in dir(mod)
        if name[0].isupper() and hasattr(getattr(mod, name), "model_fields")
    }
    ts_missing = py_classes - set(REQUIRED_SYMBOLS)
    # Exclude private helpers and non-exported wrappers
    ts_missing = {c for c in ts_missing if not c.startswith("_") and c not in ("AgentCard", "BaseModel")}
    if ts_missing:
        errs.append(
            f"pydantic classes not tracked in REQUIRED_SYMBOLS: {sorted(ts_missing)}"
        )
    return errs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="verify only (no-op write); non-zero exit on drift")
    parser.parse_args()
    errs = verify()
    if errs:
        print("agent.ts verification failed:", file=sys.stderr)
        for e in errs:
            print(f"  {e}", file=sys.stderr)
        return 1
    print("agent.ts: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
