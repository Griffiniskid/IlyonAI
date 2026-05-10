"""Run all 40 adversarial conversations against a live agent endpoint.

Usage:
  AGENT_BASE_URL=http://173.249.5.167:8080 \
  python tests/adversarial/run_harness.py [--out /tmp/adv_traces.json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib import request as urlreq, error as urlerr

from tests.adversarial.conversations import CONVERSATIONS, total_turns
from tests.adversarial.wallet_simulator import WalletSimulator


SCRATCHPAD_RE = re.compile(r"<\s*(plan|final|scratchpad)\s*/?>|^\s*Step\s+\d+\s*:", re.MULTILINE | re.IGNORECASE)


@dataclass
class TurnResult:
    conv_id: str
    turn_id: str
    message: str
    final_text: str = ""
    cards: list[dict] = field(default_factory=list)
    tools: list[dict] = field(default_factory=list)
    observations: list[dict] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    sim_results: list[dict] = field(default_factory=list)
    elapsed_ms: int = 0
    http_error: str | None = None

    @property
    def card_types(self) -> list[str]:
        return [c.get("card_type", "") for c in self.cards]

    @property
    def passed(self) -> bool:
        return not self.failures and not self.http_error


def post_sse(url: str, payload: dict, *, timeout: int = 90) -> tuple[list[dict], str | None]:
    body = json.dumps(payload).encode()
    req = urlreq.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "Origin": "http://173.249.5.167",
            "Referer": "http://173.249.5.167/",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; AdversarialHarness/1)",
        },
    )
    events: list[dict] = []
    try:
        with urlreq.urlopen(req, timeout=timeout) as resp:
            buf = b""
            for chunk in resp:
                buf += chunk
                while b"\n\n" in buf:
                    raw, buf = buf.split(b"\n\n", 1)
                    text = raw.decode("utf-8", errors="replace")
                    ev_name = ""
                    data_lines = []
                    for line in text.splitlines():
                        if line.startswith("event:"):
                            ev_name = line[6:].strip()
                        elif line.startswith("data:"):
                            data_lines.append(line[5:].strip())
                    if not data_lines:
                        continue
                    raw_data = "\n".join(data_lines)
                    try:
                        events.append({"event": ev_name, "data": json.loads(raw_data)})
                    except Exception:
                        events.append({"event": ev_name, "data": raw_data})
    except urlerr.URLError as e:
        return events, f"URLError: {e}"
    except Exception as e:
        return events, f"{type(e).__name__}: {e}"
    return events, None


def collect(events: list[dict]) -> dict:
    final = ""
    cards = []
    tools = []
    observations = []
    for ev in events:
        name = ev.get("event")
        data = ev.get("data")
        if not isinstance(data, dict):
            continue
        if name == "final":
            final = data.get("content") or final
        elif name == "card":
            cards.append(data)
        elif name == "tool":
            tools.append(data)
        elif name == "observation":
            observations.append(data)
    return {"final": final, "cards": cards, "tools": tools, "observations": observations}


def evaluate(turn: TurnResult, expected: dict, sim: WalletSimulator | None) -> None:
    if turn.http_error:
        turn.failures.append(f"http_error: {turn.http_error}")
        return
    if not turn.final_text:
        turn.failures.append("no final text emitted")

    forbidden = expected.get("text_must_not_contain") or []
    for needle in forbidden:
        if needle.lower() in turn.final_text.lower():
            turn.failures.append(f"forbidden text present: {needle!r}")

    required = expected.get("text_must_contain") or []
    for needle in required:
        if needle.lower() not in turn.final_text.lower():
            turn.failures.append(f"missing required text: {needle!r}")

    if expected.get("forbid_scratchpad") and SCRATCHPAD_RE.search(turn.final_text):
        turn.failures.append("scratchpad leak detected")

    types_set = set(turn.card_types)
    if expected.get("must_emit_plan_v3") and not (types_set & {"execution_plan", "execution_plan_v2", "execution_plan_v3"}):
        turn.failures.append(f"missing execution_plan card (got {sorted(types_set)})")
    if expected.get("must_emit_alloc") and "allocation" not in types_set:
        turn.failures.append(f"missing allocation card (got {sorted(types_set)})")
    # Allocation card implies pool universe was queried — counts as proof
    # of "yield surface" emission for must_emit_opps semantics.
    if expected.get("must_emit_opps") and not (types_set & {"defi_opportunities", "stake", "allocation"}):
        turn.failures.append(f"missing yield-surface card (got {sorted(types_set)})")
    any_of = expected.get("card_types_any_of")
    if any_of and not (set(any_of) & types_set):
        turn.failures.append(f"none of {any_of} present (got {sorted(types_set)})")

    min_pools = expected.get("min_pools_in_card")
    if min_pools:
        for c in turn.cards:
            ct = c.get("card_type")
            if ct in {"defi_opportunities", "stake"}:
                payload = c.get("payload") or {}
                items = payload.get("items") or payload.get("staking_options") or []
                if len(items) < min_pools:
                    turn.failures.append(f"{ct} only {len(items)} items (need {min_pools})")
                break

    if expected.get("weights_sum_100"):
        for c in turn.cards:
            if c.get("card_type") == "allocation":
                pos = (c.get("payload") or {}).get("positions") or []
                total = sum(float(p.get("weight") or p.get("weight_pct") or 0) for p in pos)
                if abs(total - 100.0) > 0.5:
                    turn.failures.append(f"allocation weights sum {total:.2f} not ~100")
                break

    if expected.get("asset_chain_match"):
        for c in turn.cards:
            if c.get("card_type") == "execution_plan_v3":
                steps = (c.get("payload") or {}).get("steps") or []
                for s in steps:
                    tx = s.get("transaction") or {}
                    kind = tx.get("chain_kind")
                    chain = (s.get("chain") or "").lower()
                    if not kind:
                        continue
                    if kind == "evm" and chain in {"solana", "sol"}:
                        turn.failures.append(f"step {s.get('step_id')} chain_kind=evm but chain={chain}")
                    if kind == "solana" and chain not in {"solana", "sol"}:
                        turn.failures.append(f"step {s.get('step_id')} chain_kind=solana but chain={chain}")

    # Wallet simulation against any execution_plan_v3 cards
    if sim is not None:
        for c in turn.cards:
            if c.get("card_type") == "execution_plan_v3":
                plan = c.get("payload") or {}
                pr = sim.simulate_plan(plan)
                turn.sim_results.append({
                    "plan_id": pr.plan_id,
                    "title": pr.title,
                    "blockers": pr.plan_blockers,
                    "all_ok": pr.all_ok,
                    "step_results": [
                        {
                            "step_id": s.step_id,
                            "kind": s.chain_kind,
                            "structural_ok": s.structural_ok,
                            "live_simulated": s.live_simulated,
                            "sim_ok": s.sim_ok,
                            "benign_revert": s.benign_revert,
                            "overall_ok": s.overall_ok,
                            "notes": s.notes,
                            "error": s.error,
                        }
                        for s in pr.step_results
                    ],
                })
                if pr.step_results and not pr.all_ok:
                    bad = [s.step_id for s in pr.step_results if not s.overall_ok]
                    turn.failures.append(f"plan sim failed for steps: {bad}")


def run(base_url: str, out_path: str, *, conv_filter: str | None = None) -> int:
    sim = WalletSimulator()
    print(f"[harness] EVM={sim.evm_address} SOL={sim.solana_pubkey}")
    print(f"[harness] base={base_url} total_convs={len(CONVERSATIONS)} total_turns={total_turns()}")
    results: list[dict] = []
    fail_count = 0
    pass_count = 0
    for cidx, (conv_id, turns) in enumerate(CONVERSATIONS, start=1):
        if conv_filter and conv_filter not in conv_id:
            continue
        session_id = f"adv-{conv_id}-{uuid.uuid4().hex[:8]}"
        print(f"\n=== [{cidx}/{len(CONVERSATIONS)}] {conv_id} ({len(turns)} turns) sid={session_id} ===")
        for tidx, (tid, msg, expected) in enumerate(turns, start=1):
            payload = {
                "message": msg,
                "session_id": session_id,
                "solana_wallet": sim.solana_pubkey,
                "evm_wallet": sim.evm_address,
                "wallet": sim.evm_address,
            }
            t0 = time.monotonic()
            events, err = post_sse(f"{base_url}/api/v1/agent", payload, timeout=120)
            elapsed = int((time.monotonic() - t0) * 1000)
            collected = collect(events)
            tr = TurnResult(
                conv_id=conv_id,
                turn_id=tid,
                message=msg,
                final_text=collected["final"],
                cards=collected["cards"],
                tools=collected["tools"],
                observations=collected["observations"],
                http_error=err,
                elapsed_ms=elapsed,
            )
            evaluate(tr, expected, sim)
            verdict = "PASS" if tr.passed else "FAIL"
            print(f"  [{tidx}/{len(turns)}] {tid:>3} {verdict} ({elapsed}ms) {msg[:70]}")
            for f in tr.failures:
                print(f"      - {f}")
            if tr.passed:
                pass_count += 1
            else:
                fail_count += 1
            results.append({
                "conv_id": conv_id,
                "turn_id": tid,
                "message": msg,
                "passed": tr.passed,
                "failures": tr.failures,
                "elapsed_ms": elapsed,
                "card_types": tr.card_types,
                "final_text": tr.final_text,
                "sim_results": tr.sim_results,
                "http_error": tr.http_error,
                "tool_count": len(tr.tools),
                "observation_count": len(tr.observations),
            })
    summary = {
        "base_url": base_url,
        "evm": sim.evm_address,
        "solana": sim.solana_pubkey,
        "total_turns": pass_count + fail_count,
        "pass": pass_count,
        "fail": fail_count,
        "results": results,
    }
    with open(out_path, "w") as fh:
        json.dump(summary, fh, indent=2)
    print(f"\n[harness] {pass_count}/{pass_count + fail_count} passed. trace={out_path}")
    return 1 if fail_count else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("AGENT_BASE_URL", "http://173.249.5.167:8080"))
    ap.add_argument("--out", default="/tmp/adv_traces.json")
    ap.add_argument("--filter", default=None, help="substring match against conv_id")
    args = ap.parse_args()
    return run(args.base, args.out, conv_filter=args.filter)


if __name__ == "__main__":
    sys.exit(main())
