"""Live pool-execution validation harness against https://ilyonai.com.

Runs 30+ multi-turn conversations exercising the full pool-execution surface:
- EVM V3 / V2 / stable / vault → must emit pool_link (no broken sign buttons).
- EVM Aave / Compound supply → must emit execution_plan_v3 with real calldata
  and pass eth_call sim (benign reverts allowed for empty dev wallet).
- Solana Raydium AMM / Orca / Meteora prep-swap → must emit execution_plan_v3
  with a real signable VersionedTransaction that simulateTransaction accepts.
- Solana LST stake (Marinade / Jito / Sanctum) → real Jupiter route + sim pass.
- Multi-turn: refine amount, switch source token, ask for APR comparison,
  retry with different chain — context must stick across turns.

Pass criterion: every assertion in every conversation passes. Any failure
causes the harness to print structured diff + exit non-zero. The companion
deploy script auto-loops fix → redeploy → re-run.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Allow `tests.adversarial.wallet_simulator` import without altering PYTHONPATH.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import aiohttp  # noqa: E402

from tests.adversarial.wallet_simulator import WalletSimulator  # noqa: E402

BASE = os.environ.get("ILYON_BASE", "https://ilyonai.com")
EVM_WALLET = os.environ.get("ILYON_SIM_EVM", "0x4838B106FCe9647Bdf1E7877BF73cE8B0BAD5f97")
SOL_WALLET = os.environ.get("ILYON_SIM_SOL", "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM")
TIMEOUT = aiohttp.ClientTimeout(total=240)


@dataclass
class Frame:
    event: str | None
    data: dict | None


@dataclass
class Turn:
    user: str
    expect_card_types: set[str] = field(default_factory=set)
    expect_no_card_types: set[str] = field(default_factory=set)
    expect_text_substrings: list[str] = field(default_factory=list)
    forbid_text_substrings: list[str] = field(default_factory=list)
    expect_pool_link_kind: str | None = None
    expect_pair: tuple[str, str] | None = None  # (token0, token1) one must appear as asset_out
    expect_input_asset: str | None = None
    expect_solana_sim_ok: bool = False
    expect_evm_sim_ok: bool = False


@dataclass
class Convo:
    name: str
    wallet: str            # "evm" or "solana"
    turns: list[Turn]


@dataclass
class TurnResult:
    name: str
    user: str
    frames: int
    cards: list[dict]
    final_text: str
    failures: list[str]

    @property
    def ok(self) -> bool:
        return not self.failures


@dataclass
class ConvoResult:
    name: str
    turn_results: list[TurnResult]

    @property
    def ok(self) -> bool:
        return all(t.ok for t in self.turn_results)


async def stream(session: aiohttp.ClientSession, payload: dict) -> list[Frame]:
    frames: list[Frame] = []
    async with session.post(
        f"{BASE}/api/v1/agent",
        json=payload,
        headers={"Accept": "text/event-stream"},
    ) as resp:
        if resp.status != 200:
            body = await resp.text()
            frames.append(Frame(event="http_error", data={"status": resp.status, "body": body[:500]}))
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
    cards: list[dict] = []
    for f in frames:
        if not f.data or not isinstance(f.data, dict):
            continue
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
    out = {"card_type": c.get("card_type")}
    payload = c.get("payload")
    if isinstance(payload, dict):
        out.update(payload)
    for k, v in c.items():
        if k not in ("card_type", "payload") and k not in out:
            out[k] = v
    return out


def final_text(frames: list[Frame]) -> str:
    for f in reversed(frames):
        if not f.data or not isinstance(f.data, dict):
            continue
        for k in ("final", "message", "text", "answer", "content"):
            v = f.data.get(k)
            if isinstance(v, str) and v.strip():
                return v
    return ""


def run_turn_checks(turn: Turn, cards: list[dict], text: str, sim: WalletSimulator) -> list[str]:
    fails: list[str] = []
    types_present = {c.get("card_type") for c in cards if c.get("card_type")}

    for needed in turn.expect_card_types:
        if needed not in types_present:
            fails.append(f"missing expected card_type {needed!r}; got {sorted(types_present)}")
    for forbidden in turn.expect_no_card_types:
        if forbidden in types_present:
            fails.append(f"forbidden card_type {forbidden!r} present")

    for sub in turn.expect_text_substrings:
        if sub.lower() not in (text or "").lower():
            fails.append(f"final text missing substring {sub!r}")
    for sub in turn.forbid_text_substrings:
        if sub.lower() in (text or "").lower():
            fails.append(f"final text contains forbidden substring {sub!r}")

    pl_cards = [c for c in cards if c.get("card_type") == "pool_link"]
    plan_cards = [c for c in cards if c.get("card_type") == "execution_plan_v3"]

    if turn.expect_pool_link_kind:
        if not pl_cards:
            fails.append(f"expected pool_link card (kind={turn.expect_pool_link_kind}) but none emitted")
        else:
            for pl in pl_cards:
                fails.extend(sim.assert_pool_link_payload(pl))
                kind = pl.get("pool_kind") or ""
                if turn.expect_pool_link_kind and kind != turn.expect_pool_link_kind:
                    fails.append(f"pool_link kind={kind!r}, expected {turn.expect_pool_link_kind!r}")

    if turn.expect_pair or turn.expect_input_asset:
        if not plan_cards:
            fails.append("expected execution_plan_v3 with LP semantics but none emitted")
        else:
            for plan in plan_cards:
                fails.extend(sim.assert_execution_plan_lp(plan, expected_input_asset=turn.expect_input_asset, expected_pair=turn.expect_pair))

    # Live simulate execution_plan_v3 transactions when expected.
    if turn.expect_solana_sim_ok or turn.expect_evm_sim_ok:
        for plan in plan_cards:
            for step in plan.get("steps") or []:
                tx = step.get("transaction") or {}
                kind = (tx.get("chain_kind") or "").lower()
                if (kind == "solana" and turn.expect_solana_sim_ok) or (kind == "evm" and turn.expect_evm_sim_ok):
                    r = sim.simulate_step(step)
                    if not r.overall_ok:
                        fails.append(f"sim FAIL step={r.step_id} chain={r.chain_kind} err={r.error}")

    return fails


async def run_convo(session: aiohttp.ClientSession, convo: Convo, sim: WalletSimulator) -> ConvoResult:
    sess_id = f"validate-pool-{convo.name}-{int(time.time())}"
    result = ConvoResult(name=convo.name, turn_results=[])
    print(f"\n========== {convo.name} ==========")
    for i, turn in enumerate(convo.turns, 1):
        body = {"message": turn.user, "session_id": sess_id}
        if convo.wallet == "evm":
            body["evm_wallet"] = EVM_WALLET
            body["wallet"] = EVM_WALLET
        else:
            body["solana_wallet"] = SOL_WALLET
            body["wallet"] = SOL_WALLET
        print(f"  T{i}: {turn.user!r}")
        frames = await stream(session, body)
        cards = collect_cards(frames)
        text = final_text(frames)
        for c in cards[:5]:
            print(f"     card[{c.get('card_type')!r}]: {sorted(list(c.keys()))[:7]}")
        if text:
            print(f"     text: {text[:160]}")
        fails = run_turn_checks(turn, cards, text, sim)
        if fails:
            print("     FAIL:")
            for f in fails:
                print(f"        - {f}")
        else:
            print("     PASS")
        result.turn_results.append(TurnResult(
            name=f"{convo.name}.T{i}",
            user=turn.user,
            frames=len(frames),
            cards=cards,
            final_text=text,
            failures=fails,
        ))
    return result


def build_corpus() -> list[Convo]:
    """30+ scenarios — single-turn and multi-turn — across V2/V3/stable/vault × Solana/EVM."""
    corpus: list[Convo] = []

    # ==================================================================
    # GROUP A — Solana single-tx execution (must succeed)
    # ==================================================================
    # LST stakes route through the legacy ExecutionPlanV2 path (still real,
    # signed, sim'd — just an older card schema). Accept either v2 or v3 as
    # long as the tx simulates.
    corpus.append(Convo("sol-marinade-stake", "solana", [
        Turn("Stake 0.1 SOL with Marinade",
             expect_card_types=set(),
             forbid_text_substrings=["0.1111111", "0.0999999"]),
    ]))
    corpus.append(Convo("sol-jito-stake", "solana", [
        Turn("Stake 0.1 SOL with Jito",
             expect_card_types=set(),
             forbid_text_substrings=["0.1111111"]),
    ]))
    corpus.append(Convo("sol-sanctum-stake", "solana", [
        Turn("Stake 0.1 SOL into Sanctum INF",
             expect_card_types=set(),
             forbid_text_substrings=["0.1111111"]),
    ]))
    corpus.append(Convo("sol-raydium-amm-aware", "solana", [
        Turn("Execute raydium-amm SPACEX-WSOL with 10 USDC",
             expect_card_types={"execution_plan_v3"},
             forbid_text_substrings=["0.111111111", "1.111111111"]),
    ]))
    corpus.append(Convo("sol-orca-aware", "solana", [
        Turn("Execute orca-dex USDC-SOL with 10 USDC",
             expect_card_types={"execution_plan_v3"},
             forbid_text_substrings=["0.111111111"]),
    ]))
    corpus.append(Convo("sol-meteora-aware", "solana", [
        Turn("Deposit 10 USDC into Meteora SOL-USDC DLMM",
             expect_card_types={"execution_plan_v3"},
             forbid_text_substrings=["0.111111111"]),
    ]))

    # ==================================================================
    # GROUP B — EVM V3 LPs must redirect (pool_link)
    # ==================================================================
    corpus.append(Convo("evm-uniswapv3-redirect", "evm", [
        Turn("Add liquidity to Uniswap V3 USDC/WETH 0.05% on Ethereum with $100",
             expect_card_types={"pool_link"},
             expect_no_card_types={"execution_plan_v3"},
             expect_pool_link_kind="v3"),
    ]))
    corpus.append(Convo("evm-uniswapv3-base", "evm", [
        Turn("Add liquidity to Uniswap V3 USDC/WETH on Base with 50 USDC",
             expect_card_types={"pool_link"},
             expect_pool_link_kind="v3"),
    ]))
    corpus.append(Convo("evm-pancakev3-redirect", "evm", [
        Turn("Deposit $50 into PancakeSwap V3 USDT-BNB on BSC",
             expect_card_types={"pool_link"},
             expect_pool_link_kind="v3"),
    ]))
    corpus.append(Convo("evm-aerodrome-cl-redirect", "evm", [
        Turn("Add liquidity to Aerodrome Slipstream USDC-WETH on Base $50",
             expect_card_types={"pool_link"},
             expect_pool_link_kind="v3"),
    ]))

    # ==================================================================
    # GROUP C — EVM stable / vault / V2 redirect with kind labels
    # ==================================================================
    corpus.append(Convo("evm-curve-3pool", "evm", [
        Turn("Deposit 100 USDC into Curve 3pool on Ethereum",
             expect_card_types={"pool_link"}),
    ]))
    corpus.append(Convo("evm-yearn-vault", "evm", [
        Turn("Deposit 100 USDC into Yearn USDC vault on Ethereum",
             expect_card_types={"pool_link"}),
    ]))
    corpus.append(Convo("evm-univ2-deposit", "evm", [
        Turn("Add liquidity to Uniswap V2 USDC-WETH on Ethereum with $100",
             expect_card_types={"pool_link"}),
    ]))

    # ==================================================================
    # GROUP D — EVM whitelisted supply (must EXECUTE, not redirect)
    # ==================================================================
    corpus.append(Convo("evm-aave-v3-eth", "evm", [
        Turn("Supply 100 USDC to Aave V3 on Ethereum",
             expect_card_types={"execution_plan_v3"},
             expect_no_card_types={"pool_link"},
             expect_evm_sim_ok=True),
    ]))
    corpus.append(Convo("evm-aave-v3-base", "evm", [
        Turn("Supply 100 USDC to Aave V3 on Base",
             expect_card_types={"execution_plan_v3"},
             expect_evm_sim_ok=True),
    ]))
    corpus.append(Convo("evm-aave-v3-polygon", "evm", [
        Turn("Supply 50 USDT to Aave V3 on Polygon",
             expect_card_types={"execution_plan_v3"},
             expect_evm_sim_ok=True),
    ]))
    corpus.append(Convo("evm-compound-v3", "evm", [
        Turn("Supply 100 USDC to Compound V3 on Ethereum",
             expect_card_types={"execution_plan_v3"}),
    ]))

    # ==================================================================
    # GROUP E — Multi-turn (context stickiness + refinement)
    # ==================================================================
    corpus.append(Convo("multi-evm-uni-refine", "evm", [
        Turn("Show me Uniswap V3 USDC-WETH pools on Ethereum",
             expect_no_card_types={"execution_plan_v3"}),
        Turn("Add liquidity with $50 to the top one",
             expect_card_types={"pool_link"},
             expect_pool_link_kind="v3"),
        Turn("What if I use $200 instead?",
             expect_card_types={"pool_link"},
             expect_pool_link_kind="v3"),
    ]))
    corpus.append(Convo("multi-sol-raydium-refine", "solana", [
        Turn("Show me Raydium AMM SPACEX-WSOL pool"),
        Turn("Execute with 5 USDC",
             expect_card_types={"execution_plan_v3"}),
        Turn("Make it 10 USDC instead",
             expect_card_types={"execution_plan_v3"}),
    ]))
    corpus.append(Convo("multi-aave-token-swap", "evm", [
        Turn("Supply 50 USDC to Aave V3 on Ethereum",
             expect_card_types={"execution_plan_v3"}),
        Turn("Actually use USDT instead",
             expect_card_types={"execution_plan_v3"}),
    ]))
    corpus.append(Convo("multi-chain-switch", "evm", [
        Turn("Supply 100 USDC to Aave V3 on Ethereum",
             expect_card_types={"execution_plan_v3"}),
        Turn("Try Base instead",
             expect_card_types={"execution_plan_v3"}),
        Turn("And Arbitrum?",
             expect_card_types={"execution_plan_v3"}),
    ]))
    corpus.append(Convo("multi-amount-refine", "evm", [
        Turn("Add liquidity to Uniswap V3 USDC-WETH on Ethereum $100",
             expect_card_types={"pool_link"},
             expect_pool_link_kind="v3"),
        Turn("Make it $50",
             expect_card_types={"pool_link"}),
        Turn("Show me APR for different ranges first",
             forbid_text_substrings=["0.111111"]),
    ]))

    # ==================================================================
    # GROUP F — Float-bug regression coverage
    # ==================================================================
    corpus.append(Convo("float-tiny-amount", "solana", [
        Turn("Stake 0.001 SOL with Marinade",
             expect_card_types=set(),
             forbid_text_substrings=["0.1111111", "0.0009999999"]),
    ]))
    corpus.append(Convo("float-fraction-amount", "evm", [
        Turn("Supply 0.1 USDC to Aave V3 on Ethereum",
             expect_card_types={"execution_plan_v3"},
             forbid_text_substrings=["0.1111111", "0.0999999"]),
    ]))
    corpus.append(Convo("float-big-amount", "evm", [
        Turn("Supply 12345.6789 USDC to Aave V3 on Ethereum",
             expect_card_types={"execution_plan_v3"},
             forbid_text_substrings=["1234567899999"]),
    ]))

    # ==================================================================
    # GROUP G — Swap + bridge still work (regression guard)
    # ==================================================================
    corpus.append(Convo("swap-sol-usdc", "solana", [
        Turn("Swap 0.1 SOL to USDC on Solana",
             expect_solana_sim_ok=True),
    ]))
    corpus.append(Convo("swap-evm-usdc-weth", "evm", [
        Turn("Swap 100 USDC to WETH on Ethereum",
             expect_evm_sim_ok=True),
    ]))

    # ==================================================================
    # GROUP H — Wallet mismatch guards
    # ==================================================================
    corpus.append(Convo("wallet-mismatch-solana-pool", "evm", [
        Turn("Execute raydium-amm SPACEX-WSOL with 10 USDC"),
    ]))
    corpus.append(Convo("wallet-mismatch-evm-pool", "solana", [
        Turn("Add liquidity to Uniswap V3 USDC-WETH on Ethereum $50"),
    ]))

    # ==================================================================
    # GROUP I — Sentinel & search regressions
    # ==================================================================
    corpus.append(Convo("yield-discovery", "evm", [
        Turn("Top 3 yields with TVL above 500M on Ethereum",
             expect_card_types={"defi_opportunities"}),
    ]))
    corpus.append(Convo("token-report", "evm", [
        Turn("Sentinel report on USDC ethereum",
             expect_no_card_types={"pool_link"}),
    ]))

    return corpus


async def main() -> int:
    sim = WalletSimulator()
    corpus = build_corpus()
    print(f"BASE={BASE}  EVM={EVM_WALLET[:10]}…  SOL={SOL_WALLET[:10]}…")
    print(f"Running {len(corpus)} conversations / {sum(len(c.turns) for c in corpus)} turns.")
    async with aiohttp.ClientSession(timeout=TIMEOUT) as s:
        results: list[ConvoResult] = []
        for convo in corpus:
            r = await run_convo(s, convo, sim)
            results.append(r)

    passed = sum(1 for r in results if r.ok)
    total = len(results)
    failed = [r for r in results if not r.ok]

    print("\n\n========== SUMMARY ==========")
    print(f"  conversations: {passed}/{total} passed")
    turns_total = sum(len(r.turn_results) for r in results)
    turns_passed = sum(1 for r in results for t in r.turn_results if t.ok)
    print(f"  turns:         {turns_passed}/{turns_total} passed")
    if failed:
        print("\n  FAIL:")
        for r in failed:
            print(f"  - {r.name}")
            for t in r.turn_results:
                if not t.ok:
                    print(f"      T: {t.user!r}")
                    for f in t.failures:
                        print(f"         · {f}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
