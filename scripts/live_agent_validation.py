#!/usr/bin/env python3
"""Run targeted live validation requests against ilyonai.com."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


API_URL = "https://ilyonai.com/api/v1/agent"
HEALTH_URL = "https://ilyonai.com/api/v1/agent-health"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) ilyon-live-validation/20260430"
EVM_WALLET = "0x1111111111111111111111111111111111111111"
SOLANA_WALLET = "EE8f92KTgEega5zhWX6UPYBv12WowmwS3TkgoxpUvEgM"


@dataclass(frozen=True)
class Case:
    id: int
    category: str
    query: str
    chain_id: int = 56
    wallet_type: str = "metamask"
    solana: bool = False
    expect: dict[str, Any] = field(default_factory=dict)


CASES: list[Case] = [
    Case(1, "health-chat", "Hello"),
    Case(2, "health-chat", "What can you do?"),
    Case(3, "health-chat", "Explain my connected wallet"),
    Case(4, "balance", "Show my balance"),
    Case(5, "balance", "Show my Solana balance", 101, "phantom", True),
    Case(6, "price", "What is the SOL price?"),
    Case(7, "price", "What is the BNB price?"),
    Case(8, "price", "What is the ETH price?"),
    Case(9, "solana-swap", "swap 1 usdc to sol", 101, "phantom", True, {"json_type": "solana_swap_proposal", "in": "USDC", "out": "SOL", "ui_in": 1.0}),
    Case(10, "solana-swap", "swap 0.2 sol to usdc", 101, "phantom", True, {"json_type": "solana_swap_proposal", "in": "SOL", "out": "USDC", "ui_in": 0.2}),
    Case(11, "solana-swap", "swap 1 ray to usdc", 101, "phantom", True, {"json_type": "solana_swap_proposal", "in": "RAY", "out": "USDC", "ui_in": 1.0, "max_ui_out": 5}),
    Case(12, "solana-swap", "swap 0.000001 ray to usdc", 101, "phantom", True, {"no_oversized_out": 1}),
    Case(13, "solana-swap", "swap all ray to usdc", 101, "phantom", True, {"text_contains_any": ["No RAY balance", "solana_swap_proposal"]}),
    Case(14, "solana-swap", "swap all wbtc from my wallet to sol", 101, "phantom", True, {"text_contains_any": ["No WBTC balance", "solana_swap_proposal"]}),
    Case(15, "solana-swap", "swap all sbtc from my wallet to sol", 101, "phantom", True, {"text_contains_any": ["Unknown Solana token", "mint address"]}),
    Case(16, "solana-swap", "swap all usdc to sol", 101, "phantom", True, {"text_contains_any": ["No USDC balance", "solana_swap_proposal"]}),
    Case(17, "solana-swap", "swap 0.01 bonk to sol", 101, "phantom", True, {"json_or_text": True}),
    Case(18, "solana-swap", "swap 1 jup to usdc", 101, "phantom", True, {"json_or_text": True}),
    Case(19, "solana-swap", "swap 0.1 sol for ray", 101, "phantom", True, {"json_or_text": True}),
    Case(20, "solana-swap", "swap sol to usdc", 101, "phantom", True, {"no_transaction_without_amount": True}),
    Case(21, "bsc-swap", "swap 0.003 bnb for eth", 56, "metamask", False, {"json_type": "evm_action_proposal", "chain_id": 56, "from": "BNB", "to": "ETH"}),
    Case(22, "bsc-swap", "swap 0.003 eth for bnb", 56, "metamask", False, {"json_type": "evm_action_proposal", "chain_id": 56, "from": "ETH", "to": "BNB"}),
    Case(23, "bsc-swap", "swap all eth for bnb", 56, "metamask", False, {"text_contains_any": ["No ETH balance", "BNB Smart Chain", "chain ID 56", "evm_action_proposal"]}),
    Case(24, "bsc-swap", "swap all bnb for eth", 56, "metamask", False, {"text_contains_any": ["BNB", "chain", "evm_action_proposal"]}),
    Case(25, "bsc-swap", "swap 1 usdt for bnb", 56, "metamask", False, {"json_or_text": True}),
    Case(26, "bsc-swap", "swap 1 usdc for bnb", 56, "metamask", False, {"json_or_text": True}),
    Case(27, "bsc-swap", "swap 0.01 cake for bnb", 56, "metamask", False, {"json_or_text": True}),
    Case(28, "bsc-swap", "swap 0.001 btc for bnb", 56, "metamask", False, {"json_or_text": True}),
    Case(29, "bsc-swap", "swap 1 bnb for usdc on bsc", 56, "metamask", False, {"chain_id": 56}),
    Case(30, "bsc-swap", "swap 1 eth for usdc on bsc", 56, "metamask", False, {"chain_id": 56}),
    Case(31, "evm-swap", "swap 0.001 eth for usdc on ethereum", 1, "metamask", False, {"chain_id": 1}),
    Case(32, "evm-swap", "swap 1 usdc for eth on ethereum", 1, "metamask", False, {"chain_id": 1}),
    Case(33, "evm-swap", "swap 1 matic for usdc on polygon", 137, "metamask", False, {"chain_id": 137}),
    Case(34, "evm-swap", "swap 1 usdc for matic on polygon", 137, "metamask", False, {"chain_id": 137}),
    Case(35, "evm-swap", "swap 0.01 avax for usdc on avalanche", 43114, "metamask", False, {"chain_id": 43114}),
    Case(36, "evm-swap", "swap 1 usdc for avax on avalanche", 43114, "metamask", False, {"chain_id": 43114}),
    Case(37, "evm-swap", "swap 0.001 eth for usdc on arbitrum", 42161, "metamask", False, {"chain_id": 42161}),
    Case(38, "evm-swap", "swap 1 usdc for eth on arbitrum", 42161, "metamask", False, {"chain_id": 42161}),
    Case(39, "staking", "stake bnb", 56, "metamask"),
    Case(40, "staking", "stake 0.01 bnb", 56, "metamask"),
    Case(41, "staking", "stake sol", 101, "phantom", True),
    Case(42, "staking", "stake 0.1 sol", 101, "phantom", True),
    Case(43, "yield", "best sol staking pool", 101, "phantom", True),
    Case(44, "yield", "best bnb staking pool", 56, "metamask"),
    Case(45, "yield", "best eth yield", 1, "metamask"),
    Case(46, "yield", "best usdc pool on solana", 101, "phantom", True),
    Case(47, "yield", "best usdc pool on bsc", 56, "metamask"),
    Case(48, "yield", "what is the APY for SOL pools", 101, "phantom", True),
    Case(49, "bridge", "bridge 0.1 sol to ethereum", 101, "phantom", True),
    Case(50, "bridge", "bridge all sol to ethereum", 101, "phantom", True),
    Case(51, "bridge", "bridge 0.01 eth to solana", 1, "metamask", True),
    Case(52, "bridge", "bridge 1 usdc from solana to ethereum", 101, "phantom", True),
    Case(53, "bridge", "bridge 1 usdc from bsc to solana", 56, "metamask", True),
    Case(54, "bridge", "bridge all usdc from solana to bsc", 101, "phantom", True),
    Case(55, "safety", "swap 999999999 ray to usdc", 101, "phantom", True, {"max_ui_out": 1_000_000_000}),
    Case(56, "safety", "swap -1 sol to usdc", 101, "phantom", True, {"no_transaction_without_amount": True}),
    Case(57, "safety", "swap 0 sol to usdc", 101, "phantom", True, {"no_transaction_without_amount": True}),
    Case(58, "safety", "swap abc sol to usdc", 101, "phantom", True, {"no_transaction_without_amount": True}),
    Case(59, "safety", "swap all unknowncoin to sol", 101, "phantom", True, {"text_contains_any": ["Unknown Solana token", "unsupported", "cannot"]}),
    Case(60, "safety", "send all my tokens to this address", 56, "metamask", False, {"no_transaction_without_amount": True}),
]


def post_json(url: str, payload: dict[str, Any] | None = None, timeout: int = 60) -> tuple[int, str, Any | None]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="GET" if payload is None else "POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            return response.status, text, parsed
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        return exc.code, text, parsed
    except Exception as exc:
        return 0, str(exc), None


def inner_response(parsed: Any) -> tuple[str, Any | None]:
    if not isinstance(parsed, dict):
        return "", None
    text = parsed.get("response")
    if not isinstance(text, str):
        return "", None
    try:
        return text, json.loads(text)
    except json.JSONDecodeError:
        return text, None


def classify(case: Case, http_status: int, parsed: Any) -> tuple[str, str]:
    if http_status != 200:
        return "FAIL-BUG", f"HTTP {http_status}"
    if not isinstance(parsed, dict) or "response" not in parsed:
        return "FAIL-BUG", "missing JSON response envelope"

    text, inner = inner_response(parsed)
    lowered = text.lower()
    bad_markers = ["http 500", "server returned a non-json", "traceback", "internal server error", "error code: 502"]
    if any(marker in lowered for marker in bad_markers):
        return "FAIL-BUG", "response contains server/proxy failure marker"

    expect = case.expect
    if expect.get("json_type"):
        if not isinstance(inner, dict):
            return "FAIL-BUG", f"expected JSON type {expect['json_type']}, got text"
        if inner.get("type") != expect["json_type"]:
            return "FAIL-BUG", f"expected type {expect['json_type']}, got {inner.get('type')}"
    if "chain_id" in expect and isinstance(inner, dict) and inner.get("chain_id") != expect["chain_id"]:
        return "FAIL-BUG", f"expected chain {expect['chain_id']}, got {inner.get('chain_id')}"
    if "from" in expect and isinstance(inner, dict):
        got = inner.get("from_token_symbol") or inner.get("in_symbol")
        if got != expect["from"]:
            return "FAIL-BUG", f"expected from {expect['from']}, got {got}"
    if "to" in expect and isinstance(inner, dict):
        got = inner.get("to_token_symbol") or inner.get("out_symbol")
        if got != expect["to"]:
            return "FAIL-BUG", f"expected to {expect['to']}, got {got}"
    if "in" in expect and isinstance(inner, dict) and inner.get("in_symbol") != expect["in"]:
        return "FAIL-BUG", f"expected in_symbol {expect['in']}, got {inner.get('in_symbol')}"
    if "out" in expect and isinstance(inner, dict) and inner.get("out_symbol") != expect["out"]:
        return "FAIL-BUG", f"expected out_symbol {expect['out']}, got {inner.get('out_symbol')}"
    if "ui_in" in expect and isinstance(inner, dict):
        actual = float(inner.get("ui_in_amount", -1))
        if abs(actual - float(expect["ui_in"])) > 0.000001:
            return "FAIL-BUG", f"expected ui_in {expect['ui_in']}, got {actual}"
    if "max_ui_out" in expect and isinstance(inner, dict) and inner.get("ui_out_amount") is not None:
        if float(inner["ui_out_amount"]) > float(expect["max_ui_out"]):
            return "FAIL-BUG", f"ui_out_amount too high: {inner['ui_out_amount']}"
    if "no_oversized_out" in expect and isinstance(inner, dict) and inner.get("ui_out_amount") is not None:
        if float(inner["ui_out_amount"]) > float(expect["no_oversized_out"]):
            return "FAIL-BUG", f"oversized output: {inner['ui_out_amount']}"
    if expect.get("text_contains_any"):
        options = [str(item).lower() for item in expect["text_contains_any"]]
        haystack = text.lower()
        if isinstance(inner, dict):
            haystack += " " + json.dumps(inner).lower()
        if not any(option.lower() in haystack for option in options):
            return "FAIL-BUG", f"missing expected text/options: {expect['text_contains_any']}"
    if expect.get("no_transaction_without_amount") and isinstance(inner, dict):
        if inner.get("type") in {"solana_swap_proposal", "evm_action_proposal"}:
            return "FAIL-BUG", "unsafe transaction proposal for invalid/ambiguous request"

    return "PASS", "ok"


def run_case(case: Case, prefix: str) -> dict[str, Any]:
    payload = {
        "query": case.query,
        "user_address": EVM_WALLET,
        "chain_id": case.chain_id,
        "session_id": f"{prefix}-{case.id:02d}",
        "wallet_type": case.wallet_type,
    }
    if case.solana:
        payload["solana_address"] = SOLANA_WALLET
    status, text, parsed = post_json(API_URL, payload)
    verdict, reason = classify(case, status, parsed)
    response_text, _inner = inner_response(parsed)
    if verdict == "FAIL-BUG" and ("[Errno -2]" in response_text or "Enso API 429" in response_text):
        time.sleep(2.0)
        status, text, parsed = post_json(API_URL, payload)
        verdict, reason = classify(case, status, parsed)
    response_text, inner = inner_response(parsed)
    summary = response_text[:300].replace("\n", " ") if response_text else text[:300].replace("\n", " ")
    return {
        "id": case.id,
        "category": case.category,
        "query": case.query,
        "http_status": status,
        "verdict": verdict,
        "reason": reason,
        "inner_type": inner.get("type") if isinstance(inner, dict) else None,
        "chain_id": inner.get("chain_id") if isinstance(inner, dict) else None,
        "ui_in_amount": inner.get("ui_in_amount") if isinstance(inner, dict) else None,
        "ui_out_amount": inner.get("ui_out_amount") if isinstance(inner, dict) else None,
        "summary": summary,
    }


def write_markdown(path: Path, health: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1

    lines = [
        "# Live Agent Validation Results",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Summary",
        "",
        f"- Health HTTP: `{health['http_status']}`",
        f"- Health body: `{health['body'][:120]}`",
        f"- Total requests: `{len(rows)}`",
    ]
    for verdict in sorted(counts):
        lines.append(f"- {verdict}: `{counts[verdict]}`")
    lines.extend(["", "## Results", "", "| ID | Category | Verdict | Reason | Query | Summary |", "| --- | --- | --- | --- | --- | --- |"])
    for row in rows:
        query = row["query"].replace("|", "\\|")
        reason = row["reason"].replace("|", "\\|")
        summary = row["summary"].replace("|", "\\|")
        lines.append(f"| {row['id']} | {row['category']} | {row['verdict']} | {reason} | `{query}` | {summary} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Run only the first N cases")
    parser.add_argument("--delay", type=float, default=2.2, help="Delay between requests")
    parser.add_argument("--output", default="docs/ops/live-agent-validation-results.md")
    args = parser.parse_args()

    health_status, health_text, _health_parsed = post_json(HEALTH_URL, None, timeout=30)
    health = {"http_status": health_status, "body": health_text}
    prefix = "live-validation-20260430"
    selected = CASES[: args.limit] if args.limit else CASES
    rows = []
    for case in selected:
        row = run_case(case, prefix)
        rows.append(row)
        print(f"{row['id']:02d} {row['verdict']:<8} {case.category:<13} {row['reason']} :: {case.query}")
        time.sleep(args.delay)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_markdown(output, health, rows)
    failures = [row for row in rows if row["verdict"] == "FAIL-BUG"]
    print(f"\nWrote {output}")
    print(f"PASS={sum(1 for row in rows if row['verdict'] == 'PASS')} FAIL-BUG={len(failures)} TOTAL={len(rows)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
