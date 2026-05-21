"""Walk a matrix-runs wave directory and extract every execution_plan_v3 card.

Output: a single JSON file with one entry per (capture_file, plan) — used by
`scripts/anvil_fork_replay.py` to replay every plan on a forked mainnet for
Phase B (Gate 5 on-chain executability validation).

Per-plan entry:
{
  "source_file": "passA-wave14/A01_aave_base_usdc/turn_5.txt",
  "plan_id": "plan_xxx",
  "chain": "base",                  # derived from steps[].chain
  "chains_in_plan": ["base"],        # if multi-chain composed
  "step_count": 3,
  "signable_count": 1,
  "steps": [
    {"index": 0, "action": "approve", "chain": "base", "status": "ready",
     "transaction": {"to": "...", "data": "0x...", "value": "0x0"}},
    ...
  ],
  "totals": {...},
  "blockers": [...],
}

Usage:
  python scripts/extract_execution_plans.py docs/matrix-runs/passA-wave14 \\
      -o docs/anvil-fork-runs/wave14-plans.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SSE_BLOCK = re.compile(r"event:\s*card\s*\ndata:\s*(\{.*?\})\s*\n", re.DOTALL)


def extract_plans_from_file(path: Path) -> list[dict[str, Any]]:
    """Return one entry per execution_plan_v3 card in the file."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return []
    out: list[dict[str, Any]] = []
    # Parse the SSE stream block by block. Each `event: card` followed by
    # `data: {...}\n\n` is one card frame.
    for chunk in text.split("\n\n"):
        if "event: card" not in chunk:
            continue
        # Find the data: line, strip prefix
        data_lines = [
            ln[len("data:"):].lstrip()
            for ln in chunk.splitlines()
            if ln.startswith("data:")
        ]
        if not data_lines:
            continue
        try:
            frame = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            continue
        if frame.get("card_type") != "execution_plan_v3":
            continue
        payload = frame.get("payload") or {}
        steps = payload.get("steps") or []
        chains = sorted({(s.get("chain") or "").lower() for s in steps if s.get("chain")})
        signable = [s for s in steps if s.get("status") == "ready" and s.get("transaction")]
        entry = {
            "source_file": str(path.relative_to(path.parents[2])),
            "plan_id": payload.get("plan_id"),
            "card_id": frame.get("card_id"),
            "chain": chains[0] if chains else None,
            "chains_in_plan": chains,
            "step_count": len(steps),
            "signable_count": len(signable),
            "steps": [
                {
                    "index": s.get("index"),
                    "step_id": s.get("step_id"),
                    "action": s.get("action"),
                    "chain": s.get("chain"),
                    "protocol": s.get("protocol"),
                    "status": s.get("status"),
                    "asset_in": s.get("asset_in"),
                    "amount_in": s.get("amount_in"),
                    "transaction": s.get("transaction"),
                }
                for s in steps
            ],
            "totals": payload.get("totals"),
            "blocker_count": len(payload.get("blockers") or []),
        }
        out.append(entry)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wave_dir", type=Path)
    parser.add_argument("-o", "--out", type=Path, required=True)
    parser.add_argument("--signable-only", action="store_true",
                        help="Skip plans with zero signable steps")
    args = parser.parse_args()

    if not args.wave_dir.is_dir():
        print(f"not a dir: {args.wave_dir}", file=sys.stderr)
        return 2

    all_plans: list[dict[str, Any]] = []
    capture_files = sorted(args.wave_dir.rglob("turn_*.txt"))
    for cap in capture_files:
        for plan in extract_plans_from_file(cap):
            if args.signable_only and plan["signable_count"] == 0:
                continue
            all_plans.append(plan)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(all_plans, indent=2, default=str), encoding="utf-8")

    # Summary
    print(f"scanned: {len(capture_files)} capture files")
    print(f"plans extracted: {len(all_plans)}")
    from collections import Counter
    chain_count = Counter(p.get("chain") or "?" for p in all_plans)
    print(f"by chain: {dict(chain_count)}")
    sig_total = sum(p["signable_count"] for p in all_plans)
    step_total = sum(p["step_count"] for p in all_plans)
    print(f"steps: {step_total} total, {sig_total} signable")
    print(f"wrote: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
