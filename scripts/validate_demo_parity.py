"""End-to-end demo parity validator.

Hits POST /api/v1/agent with the canonical demo prompt against a running
server, parses the SSE stream, and asserts:

    * at least one `thought` frame
    * exactly one `tool` frame with name=allocate_plan
    * three `card` frames with types {allocation, sentinel_matrix, execution_plan}
    * a `final` frame whose content references the weighted Sentinel
    * a `done` frame

Every card is schema-validated via src.api.schemas.agent._CardAdapter to
guarantee field completeness. Exit 0 on success; non-zero on failure.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from typing import Any

# Local imports (PYTHONPATH must include repo root).
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.api.schemas.agent import AgentCard  # noqa: E402

DEFAULT_URL = os.environ.get("ILYON_AGENT_URL", "http://localhost:8080/api/v1/agent")
DEMO_PROMPT = (
    "I have $10,000 USDC. Allocate it across the best staking and yield "
    "opportunities, risk-weighted using Sentinel scores."
)


def _parse_sse(stream: bytes) -> list[tuple[str, dict]]:
    frames: list[tuple[str, dict]] = []
    event = None
    data_parts: list[str] = []
    for raw_line in stream.split(b"\n"):
        line = raw_line.decode("utf-8", errors="replace").rstrip("\r")
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data_parts.append(line[5:].strip())
        elif line == "":
            if event and data_parts:
                try:
                    frames.append((event, json.loads("".join(data_parts))))
                except json.JSONDecodeError:
                    frames.append((event, {"_raw": "".join(data_parts)}))
            event = None
            data_parts = []
    if event and data_parts:
        try:
            frames.append((event, json.loads("".join(data_parts))))
        except json.JSONDecodeError:
            frames.append((event, {"_raw": "".join(data_parts)}))
    return frames


def _post_sse(url: str, body: dict) -> bytes:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
        return resp.read()


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)


def _must_have_fields(obj: dict, fields: list[str], label: str) -> None:
    missing = [f for f in fields if f not in obj]
    _assert(not missing, f"{label} missing fields: {missing}")


def main() -> None:
    url = DEFAULT_URL
    print(f"→ POST {url}")
    stream = _post_sse(url, {"session_id": "demo-parity", "message": DEMO_PROMPT})
    frames = _parse_sse(stream)
    print(f"  received {len(frames)} SSE frames")

    events: dict[str, list[dict]] = {}
    for ev, data in frames:
        events.setdefault(ev, []).append(data)

    _assert("error" not in events, f"server returned error: {events.get('error')}")
    _assert("thought" in events and len(events["thought"]) >= 1,
            "at least one thought frame expected")
    tools = events.get("tool", [])
    _assert(len(tools) >= 1, "at least one tool frame expected")
    allocate_calls = [t for t in tools if t.get("name") == "allocate_plan"]
    _assert(len(allocate_calls) == 1,
            f"expected exactly one allocate_plan tool call, got {len(allocate_calls)}")

    cards = events.get("card", [])
    types_seen = {c.get("card_type") for c in cards}
    for req in ("allocation", "sentinel_matrix", "execution_plan"):
        _assert(req in types_seen, f"missing {req} card; got {sorted(types_seen)}")

    # Validate each card against its pydantic schema.
    for c in cards:
        try:
            AgentCard.model_validate({
                "card_id": c["card_id"],
                "card_type": c["card_type"],
                "payload": c["payload"],
            })
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL: card {c.get('card_type')} failed schema: {exc}")
            sys.exit(1)

    # Spot-check per-card field completeness (demo contract).
    allocation = next(c for c in cards if c["card_type"] == "allocation")["payload"]
    _must_have_fields(
        allocation,
        ["positions", "total_usd", "blended_apy", "chains", "weighted_sentinel",
         "risk_mix", "combined_tvl"],
        "allocation payload",
    )
    _assert(len(allocation["positions"]) == 5,
            f"expected 5 positions, got {len(allocation['positions'])}")
    for p in allocation["positions"]:
        _must_have_fields(
            p,
            ["rank", "protocol", "asset", "chain", "apy", "sentinel",
             "risk", "fit", "weight", "usd", "tvl", "router",
             "safety", "durability", "exit", "confidence", "flags"],
            f"allocation.positions[{p.get('rank')}]",
        )

    matrix = next(c for c in cards if c["card_type"] == "sentinel_matrix")["payload"]
    _must_have_fields(
        matrix,
        ["positions", "low_count", "medium_count", "high_count", "weighted_sentinel"],
        "sentinel_matrix payload",
    )
    _assert(len(matrix["positions"]) == 5, "sentinel_matrix must have 5 positions")

    plan = next(c for c in cards if c["card_type"] == "execution_plan")["payload"]
    _must_have_fields(
        plan,
        ["steps", "total_gas", "slippage_cap", "wallets", "tx_count", "requires_signature"],
        "execution_plan payload",
    )
    _assert(len(plan["steps"]) == 5,
            f"expected 5 execution steps, got {len(plan['steps'])}")
    for s in plan["steps"]:
        _must_have_fields(
            s,
            ["index", "verb", "amount", "asset", "target", "chain",
             "router", "wallet", "gas"],
            f"execution_plan.steps[{s.get('index')}]",
        )

    final = events.get("final", [])
    _assert(len(final) == 1, "expected exactly one final frame")
    content = final[0].get("content", "")
    _assert(
        any(
            keyword in content
            for keyword in ("weighted sentinel", "Sentinel", "Weighted Sentinel")
        ),
        f"final content should mention Sentinel; got: {content[:120]!r}",
    )
    # Card IDs in the final frame should cover all 3 cards.
    card_ids_final = set(final[0].get("card_ids", []))
    card_ids_stream = {c.get("card_id") for c in cards}
    missing_ids = card_ids_stream - card_ids_final
    _assert(
        not missing_ids,
        f"final.card_ids ({len(card_ids_final)}) missing: {missing_ids}",
    )

    _assert("done" in events and len(events["done"]) == 1,
            "expected exactly one done frame")

    print("PASS: demo parity validated")
    print(f"  - 3 cards: {sorted(types_seen & {'allocation', 'sentinel_matrix', 'execution_plan'})}")
    print(f"  - 5 positions, weighted Sentinel {allocation['weighted_sentinel']}, blended {allocation['blended_apy']}")
    print(f"  - execution plan: {plan['tx_count']} txs, total gas {plan['total_gas']}, wallets {plan['wallets']}")
    sys.exit(0)


if __name__ == "__main__":
    main()
