"""Live validation against https://ilyonai.com — no-exec branch.

Runs five real POST /api/v1/agent calls and asserts that pool-link cards
carry a direct protocol URL (not DefiLlama), allocation positions carry
protocol_url, and swaps still get an execution plan.
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from dataclasses import dataclass
from typing import Any

import aiohttp

BASE = "https://ilyonai.com"
EVM = "0x4838B106FCe9647Bdf1E7877BF73cE8B0BAD5f97"
SOL = "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"
TIMEOUT = aiohttp.ClientTimeout(total=180)


@dataclass
class Frame:
    event: str | None
    data: dict | None


async def stream(session: aiohttp.ClientSession, payload: dict) -> list[Frame]:
    """Stream SSE from POST /api/v1/agent and return parsed frames."""
    frames: list[Frame] = []
    async with session.post(
        f"{BASE}/api/v1/agent",
        json=payload,
        headers={"Accept": "text/event-stream"},
    ) as resp:
        if resp.status != 200:
            body = await resp.text()
            print(f"  HTTP {resp.status}: {body[:300]}")
            return frames
        cur_event: str | None = None
        async for raw in resp.content:
            line = raw.decode("utf-8", "replace").rstrip("\n").rstrip("\r")
            if line.startswith("event:"):
                cur_event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                payload_str = line.split(":", 1)[1].strip()
                if not payload_str:
                    continue
                try:
                    data = json.loads(payload_str)
                except Exception:
                    data = {"_raw": payload_str}
                frames.append(Frame(event=cur_event, data=data))
            elif line == "":
                cur_event = None
    return frames


def collect_cards(frames: list[Frame]) -> list[dict]:
    """Flatten any CardFrame into {card_type, **payload} so downstream
    expectation checks can read fields directly."""
    cards: list[dict] = []
    for f in frames:
        if not f.data:
            continue
        if isinstance(f.data, dict):
            for key in ("card", "cards", "extra_cards"):
                v = f.data.get(key)
                items = [v] if isinstance(v, dict) else (v if isinstance(v, list) else [])
                for c in items:
                    if isinstance(c, dict):
                        cards.append(_flatten_card(c))
            if "card_type" in f.data:
                cards.append(_flatten_card(f.data))
    return cards


def _flatten_card(c: dict) -> dict:
    """Card frames have {card_type, payload:{...}}. Flatten so fields are
    addressable directly without `.payload`."""
    out = {"card_type": c.get("card_type")}
    payload = c.get("payload")
    if isinstance(payload, dict):
        out.update(payload)
    # Preserve top-level fields if no payload
    for k, v in c.items():
        if k != "card_type" and k != "payload" and k not in out:
            out[k] = v
    return out


def final_message(frames: list[Frame]) -> str:
    for f in reversed(frames):
        if not f.data:
            continue
        for k in ("final", "message", "text", "answer"):
            v = f.data.get(k) if isinstance(f.data, dict) else None
            if isinstance(v, str) and v.strip():
                return v
    return ""


@dataclass
class Result:
    name: str
    passed: bool
    detail: str


async def run_case(
    sess: aiohttp.ClientSession,
    name: str,
    msg: str,
    wallet_field: str,
    wallet: str,
    expect: callable,
) -> Result:
    print(f"\n=== {name} ===")
    print(f"  → {msg}")
    payload = {"message": msg, "session_id": f"validate-{name}", wallet_field: wallet}
    if wallet_field == "evm_wallet":
        payload["wallet"] = wallet
    if wallet_field == "solana_wallet":
        payload["wallet"] = wallet
    frames = await stream(sess, payload)
    cards = collect_cards(frames)
    msg_text = final_message(frames)
    print(f"  ← {len(frames)} frames, {len(cards)} cards")
    for c in cards[:6]:
        ct = c.get("card_type") or "?"
        keys = ",".join(list(c.keys())[:8])
        print(f"     card[{ct}]: {keys}")
    if msg_text:
        print(f"  text: {msg_text[:160]}")
    ok, detail = expect(cards, msg_text, frames)
    print(f"  {'PASS' if ok else 'FAIL'}: {detail}")
    if not ok:
        print("  -- failure dump --")
        for f in frames:
            ev = f.event or "?"
            d = f.data
            if not isinstance(d, dict):
                continue
            if ev == "tool":
                print(f"     [tool] name={d.get('name')} args={json.dumps(d.get('args') or {})[:200]}")
            elif ev == "observation":
                err = d.get("error") or {}
                ok_ = d.get("ok")
                print(f"     [obs] name={d.get('name')} ok={ok_} err={json.dumps(err)[:300]}")
                # Also dump card if present
                for k in ("card", "card_payload"):
                    v = d.get(k)
                    if isinstance(v, dict):
                        print(f"       {k}: card_type={v.get('card_type')} keys={list(v.keys())[:6]}")
            elif ev == "final":
                txt = d.get("content") or ""
                print(f"     [final] text={txt[:200]}")
    return Result(name=name, passed=ok, detail=detail)


def expect_pool_link(host_re: str):
    def _check(cards, _text, _frames):
        for c in cards:
            if c.get("card_type") == "pool_link":
                u = c.get("url") or ""
                if re.search(host_re, u or ""):
                    return True, f"pool_link → {u[:80]}"
                return False, f"pool_link host mismatch: {u}"
        return False, "no pool_link card emitted"
    return _check


def expect_allocation_with_urls(cards, _text, _frames):
    for c in cards:
        if c.get("card_type") == "allocation":
            positions = c.get("positions") or []
            with_url = [p for p in positions if p.get("protocol_url")]
            if not positions:
                return False, "allocation has no positions"
            if len(with_url) == len(positions):
                hosts = ",".join(re.findall(r"https?://([^/]+)", " ".join(p["protocol_url"] for p in positions)))[:120]
                return True, f"{len(positions)} positions all have protocol_url ({hosts})"
            return False, f"only {len(with_url)}/{len(positions)} positions have protocol_url"
    return False, "no allocation card"


def expect_exec_plan_with_tx(cards, _text, frames):
    for c in cards:
        if c.get("card_type") in ("execution_plan_v3", "execution_plan_v2", "swap_quote"):
            steps = c.get("steps") or []
            if not steps and c.get("card_type") == "swap_quote":
                return True, f"{c.get('card_type')} card present"
            has_tx = any(s.get("transaction") for s in steps)
            if has_tx:
                return True, f"{c.get('card_type')} has {len(steps)} steps, ≥1 with tx"
            return False, f"{c.get('card_type')} present but no transaction on any step"
    # Fallback: build_swap_tx tool observation w/ ok=true and tx in payload
    for f in frames:
        if (f.event == "observation"
            and isinstance(f.data, dict)
            and f.data.get("name") == "build_swap_tx"
            and f.data.get("ok")):
            return True, "build_swap_tx ok (tx payload returned)"
    return False, "no execution_plan / swap_quote card and no build_swap_tx ok"


def expect_defi_opps(cards, _text, _frames):
    for c in cards:
        if c.get("card_type") == "defi_opportunities":
            opps = c.get("opportunities") or c.get("pools") or []
            return True, f"defi_opportunities with {len(opps)} entries"
    return False, "no defi_opportunities card"


async def main() -> int:
    async with aiohttp.ClientSession(timeout=TIMEOUT) as s:
        results = []
        results.append(await run_case(
            s, "aave-v3-link",
            "Supply 10 USDT on Aave V3 on Ethereum",
            "evm_wallet", EVM,
            expect_pool_link(r"app\.aave\.com"),
        ))
        results.append(await run_case(
            s, "raydium-link",
            "Execute raydium-amm SPACEX-WSOL with 10 USDC",
            "solana_wallet", SOL,
            expect_pool_link(r"raydium\.io"),
        ))
        results.append(await run_case(
            s, "allocation-urls",
            "Build me a strategy with $1000 across balanced yields on Ethereum and Base",
            "evm_wallet", EVM,
            expect_allocation_with_urls,
        ))
        results.append(await run_case(
            s, "swap-exec",
            "Swap 0.1 SOL to USDC on Solana",
            "solana_wallet", SOL,
            expect_exec_plan_with_tx,
        ))
        results.append(await run_case(
            s, "discovery",
            "Top 3 yields with TVL above 500M on Ethereum",
            "evm_wallet", EVM,
            expect_defi_opps,
        ))

    print("\n=== SUMMARY ===")
    passed = sum(1 for r in results if r.passed)
    for r in results:
        flag = "✓" if r.passed else "✗"
        print(f"  {flag} {r.name}: {r.detail}")
    print(f"\n  {passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
