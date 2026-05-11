"""Advanced 7-test tester walkthrough against staging.ilyonai.com.

Runs every turn from the chat-displayed walkthrough, simulates each
execution_plan_v3 step via wallet_simulator (eth_call for EVM, sigVerify=False
simulateTransaction for Solana), and reports any failures.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import aiohttp  # noqa: E402

from tests.adversarial.wallet_simulator import WalletSimulator  # noqa: E402

BASE = os.environ.get("ILYON_BASE", "https://staging.ilyonai.com")
EVM_WALLET = os.environ.get("ILYON_SIM_EVM", "0x4838B106FCe9647Bdf1E7877BF73cE8B0BAD5f97")
SOL_WALLET = os.environ.get("ILYON_SIM_SOL", "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM")
TIMEOUT = aiohttp.ClientTimeout(total=240)


@dataclass
class TurnExpect:
    prompt: str
    must_card: set[str] = field(default_factory=set)
    must_not_card: set[str] = field(default_factory=set)
    must_text: list[str] = field(default_factory=list)
    must_not_text: list[str] = field(default_factory=list)
    sim_required: bool = False


@dataclass
class TestCase:
    name: str
    wallet: str  # "evm" or "solana"
    turns: list[TurnExpect]


def build_walkthrough() -> list[TestCase]:
    tests: list[TestCase] = []

    # ===== TEST 1 — EVM Lending Switch Storm =====
    tests.append(TestCase("test1-lending-storm", "evm", [
        TurnExpect("Supply 100 USDC to Aave V3 on Ethereum",
                   must_card={"execution_plan_v3"},
                   must_text=["aave-v3"],
                   sim_required=True),
        TurnExpect("Try Base instead",
                   must_card={"execution_plan_v3"},
                   must_text=["base"]),
        TurnExpect("Actually use USDT instead",
                   must_card={"execution_plan_v3"},
                   must_text=["USDT"]),
        TurnExpect("Try Polygon",
                   must_card={"execution_plan_v3"},
                   must_text=["polygon"]),
        TurnExpect("Now switch to Compound V3",
                   must_card={"execution_plan_v3"},
                   must_text=["compound"]),
        TurnExpect("Make it $250",
                   must_card={"execution_plan_v3"}),
    ]))

    # ===== TEST 2 — V3 NFT Multi-Chain + Range Math =====
    tests.append(TestCase("test2-v3-nft-multichain", "evm", [
        TurnExpect("Add liquidity to Uniswap V3 USDC/WETH 0.05% on Ethereum with $100",
                   must_card={"execution_plan_v3"},
                   must_text=["uniswap-v3"],
                   sim_required=True),
        TurnExpect("Make it $50",
                   must_card={"execution_plan_v3"}),
        TurnExpect("Try Base instead",
                   must_card={"execution_plan_v3"},
                   must_text=["base"]),
        TurnExpect("Add liquidity to Aerodrome Slipstream USDC-WETH on Base $75",
                   must_card={"execution_plan_v3"},
                   must_text=["aerodrome"]),
        TurnExpect("What about a wider 25% range?",
                   must_card={"execution_plan_v3"}),
    ]))

    # ===== TEST 3 — Cross-Token Zap + Protocol Cascade =====
    tests.append(TestCase("test3-cross-token-zap", "evm", [
        TurnExpect("Deposit 100 USDT into Curve DAI-USDC on Ethereum",
                   must_card={"execution_plan_v3"},
                   must_text=["curve"]),
        TurnExpect("Actually use Yearn USDC vault instead",
                   must_card={"execution_plan_v3"},
                   must_text=["yearn"]),
        TurnExpect("Try Morpho on Base",
                   must_card={"execution_plan_v3"},
                   must_text=["morpho"]),
        TurnExpect("Make it 25 USDC",
                   must_card={"execution_plan_v3"}),
    ]))

    # ===== TEST 4 — Solana LST Cascade + Mixed LP =====
    tests.append(TestCase("test4-sol-lst-mixed", "solana", [
        TurnExpect("Stake 0.1 SOL with Marinade",
                   must_not_text=["0.1111111", "0.0999999"]),
        TurnExpect("Switch to Jito",
                   must_not_text=["0.1111111"]),
        TurnExpect("And Sanctum INF",
                   must_not_text=["0.1111111"]),
        TurnExpect("Add 5 USDC to Raydium AMM SPACEX-WSOL",
                   must_card={"execution_plan_v3"},
                   must_not_text=["0.1111111", "5.5555555"]),
        TurnExpect("Execute orca-dex USDC-SOL with 10 USDC",
                   must_card={"execution_plan_v3"},
                   must_not_text=["0.1111111"]),
    ]))

    # ===== TEST 5 — V2 → V3 Same Pair Promotion =====
    tests.append(TestCase("test5-v2-v3-promote", "evm", [
        TurnExpect("Add liquidity to Uniswap V2 USDC-WETH on Ethereum with 100 USDC and 0.05 WETH",
                   must_card={"execution_plan_v3"}),
        TurnExpect("Switch to Uniswap V3 same pair $200",
                   must_card={"execution_plan_v3"}),
        TurnExpect("Try 0.30% fee tier",
                   must_card={"execution_plan_v3"}),
        TurnExpect("Try Base instead",
                   must_card={"execution_plan_v3"}),
    ]))

    # ===== TEST 6 — Error Recovery =====
    tests.append(TestCase("test6-error-recovery", "evm", [
        TurnExpect("Supply 100 USDC to FakeBank on Ethereum",
                   must_card={"pool_link"}),
        TurnExpect("Try Aave V3 instead",
                   must_card={"execution_plan_v3"},
                   must_text=["aave"]),
        TurnExpect("Make it 999999999 USDC",
                   must_card={"execution_plan_v3"}),
        TurnExpect("Show me USDC balance on Ethereum",
                   must_not_card={"pool_link"}),
    ]))

    # ===== TEST 7 — Float Precision =====
    tests.append(TestCase("test7-float-precision", "evm", [
        TurnExpect("Supply 0.1 USDC to Aave V3 on Ethereum",
                   must_card={"execution_plan_v3"},
                   must_not_text=["0.0999999", "0.1111111"]),
        TurnExpect("Make it 12345.6789 USDC",
                   must_card={"execution_plan_v3"},
                   must_not_text=["1.2345678e", "12345.677"]),
        TurnExpect("Add liquidity to Curve DAI-USDC on Ethereum $3.14",
                   must_card={"execution_plan_v3"},
                   must_not_text=["3.1415926"]),
    ]))

    return tests


@dataclass
class Frame:
    event: str | None
    data: dict | None


async def stream(session: aiohttp.ClientSession, payload: dict) -> list[Frame]:
    frames: list[Frame] = []
    async with session.post(
        f"{BASE}/api/v1/agent",
        json=payload,
        headers={"Accept": "text/event-stream"},
    ) as resp:
        if resp.status != 200:
            frames.append(Frame(event="http_error", data={"status": resp.status}))
            return frames
        cur_event: str | None = None
        async for raw in resp.content:
            line = raw.decode("utf-8", "replace").rstrip("\n").rstrip("\r")
            if line.startswith("event:"):
                cur_event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                p = line.split(":", 1)[1].strip()
                if not p:
                    continue
                try:
                    data = json.loads(p)
                except Exception:
                    data = {"_raw": p}
                frames.append(Frame(event=cur_event, data=data))
            elif line == "":
                cur_event = None
    return frames


def collect_cards(frames: list[Frame]) -> list[dict]:
    cards: list[dict] = []
    for f in frames:
        if not f.data:
            continue
        if "card_type" in f.data:
            cards.append(f.data)
        for k in ("card", "card_payload", "payload"):
            sub = f.data.get(k) if isinstance(f.data, dict) else None
            if isinstance(sub, dict) and "card_type" in sub:
                cards.append(sub)
    return cards


def final_text(frames: list[Frame]) -> str:
    parts: list[str] = []
    for f in frames:
        if not f.data:
            continue
        for k in ("text", "message", "content", "summary", "narrative"):
            v = f.data.get(k) if isinstance(f.data, dict) else None
            if isinstance(v, str):
                parts.append(v)
    return "\n".join(parts)


async def run_test(session: aiohttp.ClientSession, t: TestCase, sim: WalletSimulator) -> list[str]:
    short = hashlib.sha1(f"{t.name}-{int(time.time())}".encode()).hexdigest()[:10]
    sid = f"tw-{short}"
    fails: list[str] = []
    print(f"\n========== {t.name} ==========")
    for i, turn in enumerate(t.turns, 1):
        body = {"message": turn.prompt, "session_id": sid}
        if t.wallet == "evm":
            body["evm_wallet"] = EVM_WALLET
            body["wallet"] = EVM_WALLET
        else:
            body["solana_wallet"] = SOL_WALLET
            body["wallet"] = SOL_WALLET
        print(f"  T{i}: {turn.prompt!r}")
        try:
            frames = await stream(session, body)
        except Exception as e:
            fails.append(f"{t.name}.T{i}: stream error {e}")
            print(f"     STREAM ERR: {e}")
            continue
        cards = collect_cards(frames)
        text = final_text(frames)
        card_types = {c.get("card_type") for c in cards if c.get("card_type")}
        print(f"     cards={sorted(card_types)} text_len={len(text)}")
        text_lc = text.lower()

        for needed in turn.must_card:
            if needed not in card_types:
                fails.append(f"{t.name}.T{i}: missing card {needed}; got {sorted(card_types)}")
        for forbidden in turn.must_not_card:
            if forbidden in card_types:
                fails.append(f"{t.name}.T{i}: forbidden card {forbidden} present")
        for sub in turn.must_text:
            if sub.lower() not in text_lc:
                fails.append(f"{t.name}.T{i}: text missing '{sub}'")
        for sub in turn.must_not_text:
            if sub.lower() in text_lc:
                fails.append(f"{t.name}.T{i}: text contains forbidden '{sub}'")

        # Simulate every signable step when sim_required.
        if turn.sim_required:
            plans = [c for c in cards if c.get("card_type") == "execution_plan_v3"]
            for plan in plans:
                steps = plan.get("steps") or (plan.get("payload") or {}).get("steps") or []
                for step in steps:
                    if not step.get("transaction"):
                        continue
                    r = sim.simulate_step(step)
                    if not r.overall_ok:
                        fails.append(f"{t.name}.T{i}: sim FAIL step={r.step_id} err={r.error!r}")

    if fails:
        print("  ** FAILS:")
        for f in fails:
            print(f"     - {f}")
    else:
        print(f"  ** all {len(t.turns)} turns PASS")
    return fails


async def main() -> int:
    sim = WalletSimulator()
    tests = build_walkthrough()
    print(f"Running {len(tests)} tester walkthrough cases against {BASE}")
    all_fails: list[str] = []
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        for t in tests:
            fails = await run_test(session, t, sim)
            all_fails.extend(fails)

    print("\n" + "=" * 60)
    print(f"SUMMARY: {len(tests)} tests, {len(all_fails)} total failures")
    if all_fails:
        print("FAILS:")
        for f in all_fails:
            print(f"  - {f}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
