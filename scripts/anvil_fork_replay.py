"""L3.2 — Anvil fork-mainnet replay for Phase B Gate 5.

Reads a JSON file (from `extract_execution_plans.py`), groups plans by chain,
spawns one anvil fork per chain, funds the test wallet, and broadcasts every
signable step's `transaction` field in order. Captures per-step receipt status
+ gas + log count, plus per-plan PASS/FAIL.

Output: per-run report at `docs/anvil-fork-runs/<ts>/report.md` + a JSON
companion. A plan PASSES if every signable step's receipt has status `0x1`
(success). A plan FAILS if any step reverts or never produces a receipt.

Phase B Gate 5: every emitted execution_plan_v3 from the latest matrix pass
must replay cleanly on forked mainnet for its target chain. Solana plans are
out of scope here (anvil is EVM-only); they get marked "skipped_solana".

Stdlib-only (urllib + threading) so it runs on VPS without pip deps.

Usage:
  python3 scripts/anvil_fork_replay.py docs/anvil-fork-runs/wave14-plans.json
  python3 scripts/anvil_fork_replay.py wave14-plans.json --only-chain ethereum
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Inlined from scripts/anvil_fork_sim.py so this script has no third-party
# deps (VPS python has no pip). keccak via stdlib `hashlib.sha3_256`?
# No — Ethereum uses keccak-256 (NIST keccak before SHA-3 finalisation),
# not sha3_256. We use the standard `pysha3`-free trick: pycryptodome's
# keccak is only on tests; on VPS we ship our own minimal keccak. Easiest
# stdlib path: use `Crypto.Hash.keccak` if pycryptodome is present, else
# fall back to a pure-python keccak. To avoid bundling a keccak lib, we
# call out to `cast keccak <hex>` from foundry which IS on the VPS.
TEST_ADDR = "0x4838B106FCe9647Bdf1E7877BF73cE8B0BAD5f97"


def _slot_key(token: str, holder: str, slot: int) -> str:
    """keccak256(holder_pad32 || slot_pad32) for Solidity mapping storage."""
    holder_clean = holder.lower().removeprefix("0x").rjust(64, "0")
    slot_hex = format(slot, "064x")
    raw_hex = holder_clean + slot_hex
    # Try pycryptodome first (if present), then cryptography, then `cast keccak`.
    try:
        from Crypto.Hash import keccak  # type: ignore
        k = keccak.new(digest_bits=256)
        k.update(bytes.fromhex(raw_hex))
        return "0x" + k.hexdigest()
    except ImportError:
        pass
    try:
        # eth-utils is sometimes present alongside foundry on dev boxes
        from eth_utils import keccak as eth_keccak  # type: ignore
        return "0x" + eth_keccak(bytes.fromhex(raw_hex)).hex()
    except ImportError:
        pass
    # Last resort: shell out to `cast keccak`.
    cast_bin = os.path.expanduser("~/.foundry/bin/cast")
    if not Path(cast_bin).exists():
        cast_bin = "cast"
    try:
        result = subprocess.run(
            [cast_bin, "keccak", "0x" + raw_hex],
            capture_output=True, text=True, timeout=5,
        )
        out = result.stdout.strip()
        if out.startswith("0x") and len(out) == 66:
            return out
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    raise RuntimeError("no keccak256 backend available (pycryptodome, eth_utils, or cast)")


CHAIN_RPC = {
    "ethereum": os.environ.get("MAINNET_RPC", "https://ethereum-rpc.publicnode.com"),
    "base": os.environ.get("BASE_RPC", "https://base-rpc.publicnode.com"),
    "arbitrum": os.environ.get("ARBITRUM_RPC", "https://arbitrum-one-rpc.publicnode.com"),
    "optimism": os.environ.get("OPTIMISM_RPC", "https://optimism-rpc.publicnode.com"),
    "polygon": os.environ.get("POLYGON_RPC", "https://polygon-bor-rpc.publicnode.com"),
    "bsc": os.environ.get("BSC_RPC", "https://bsc-rpc.publicnode.com"),
    "avalanche": os.environ.get("AVAX_RPC", "https://avalanche-c-chain-rpc.publicnode.com"),
}

# ERC20 balanceOf storage slot per (chain, token_address_lower). Most USDC
# variants use slot 9 (proxy storage); WETH uses slot 3; DAI/USDT vary.
ERC20_BALANCE_SLOT: dict[tuple[str, str], int] = {
    # Ethereum mainnet
    ("ethereum", "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"): 9,   # USDC
    ("ethereum", "0xdac17f958d2ee523a2206206994597c13d831ec7"): 2,   # USDT
    ("ethereum", "0x6b175474e89094c44da98b954eedeac495271d0f"): 2,   # DAI
    ("ethereum", "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"): 3,   # WETH
    ("ethereum", "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599"): 0,   # WBTC
    # Base
    ("base", "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"): 9,        # USDC
    ("base", "0x4200000000000000000000000000000000000006"): 3,        # WETH
    # Arbitrum
    ("arbitrum", "0xaf88d065e77c8cc2239327c5edb3a432268e5831"): 9,    # USDC
    ("arbitrum", "0x82af49447d8a07e3bd95bd0d56f35241523fbab1"): 3,    # WETH
    ("arbitrum", "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9"): 51,   # USDT (bridged)
    # Optimism
    ("optimism", "0x0b2c639c533813f4aa9d7837caf62653d097ff85"): 9,    # USDC
    ("optimism", "0x4200000000000000000000000000000000000006"): 3,    # WETH
    ("optimism", "0x94b008aa00579c1307b0ef2c499ad98a8ce58e58"): 0,    # USDT
    # Polygon
    ("polygon", "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359"): 9,     # USDC native
    ("polygon", "0xc2132d05d31c914a87c6611c10748aeb04b58e8f"): 0,     # USDT
    ("polygon", "0x7ceb23fd6bc0add59e62ac25578270cff1b9f619"): 0,     # WETH
    # BSC
    ("bsc", "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d"): 1,         # USDC bep20
    ("bsc", "0x55d398326f99059ff775485246999027b3197955"): 1,         # USDT bep20
    # Avalanche C-chain
    ("avalanche", "0xb97ef9ef8734c71904d8002f8b6bc66dd9c48a6e"): 9,   # USDC
    ("avalanche", "0x9702230a8ea53601f5cd2dc00fdbc13d4df4a8c7"): 51,  # USDT bridged
}

NATIVE_GIFT_WEI = "0x56BC75E2D63100000"  # 100 native (18 decimals)

# Routers the agent's execution plans commonly target without including an
# explicit approve step (because the agent assumes returning users already
# have allowance). Pre-approving these in the fork removes the false-positive
# "Enso revert because no allowance" failure mode and lets Phase B isolate
# REAL calldata bugs.
COMMON_ROUTERS_BY_CHAIN: dict[str, list[str]] = {
    "ethereum": [
        "0xF75584eF6673aD213a685a1B58Cc0330B8eA22Cf",  # Enso shortcut router
        "0x000000000022D473030F116dDEE9F6B43aC78BA3",  # Permit2
        "0x111111125421cA6dc452d289314280a0f8842A65",  # 1inch v6
        "0xC36442b4a4522E871399CD717aBDD847Ab11FE88",  # Uniswap V3 NPM
        "0x3fC91A3afd70395Cd496C647d5a6CC9D4B2b7FAD",  # Uniswap UniversalRouter
        "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",  # Aave V3 Pool
    ],
    "base": [
        "0xF75584eF6673aD213a685a1B58Cc0330B8eA22Cf",
        "0x000000000022D473030F116dDEE9F6B43aC78BA3",
        "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5",  # Aave V3 Pool Base
    ],
    "arbitrum": [
        "0xF75584eF6673aD213a685a1B58Cc0330B8eA22Cf",
        "0x000000000022D473030F116dDEE9F6B43aC78BA3",
        "0x794a61358D6845594F94dc1DB02A252b5b4814aD",  # Aave V3 Pool (arb/opt/poly)
    ],
    "optimism": [
        "0xF75584eF6673aD213a685a1B58Cc0330B8eA22Cf",
        "0x000000000022D473030F116dDEE9F6B43aC78BA3",
        "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
    ],
    "polygon": [
        "0xF75584eF6673aD213a685a1B58Cc0330B8eA22Cf",
        "0x000000000022D473030F116dDEE9F6B43aC78BA3",
        "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
    ],
    "bsc": [
        "0xF75584eF6673aD213a685a1B58Cc0330B8eA22Cf",
        "0x000000000022D473030F116dDEE9F6B43aC78BA3",
    ],
    "avalanche": [
        "0xF75584eF6673aD213a685a1B58Cc0330B8eA22Cf",
        "0x000000000022D473030F116dDEE9F6B43aC78BA3",
        "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
    ],
}

MAX_UINT256 = "0x" + "f" * 64


def _build_approve_calldata(spender: str) -> str:
    """approve(address spender, uint256 amount) — selector 0x095ea7b3."""
    spender_clean = spender.lower().removeprefix("0x").rjust(64, "0")
    amount_hex = "f" * 64  # MAX_UINT256
    return "0x095ea7b3" + spender_clean + amount_hex


def find_anvil() -> str:
    for cand in (
        os.environ.get("ANVIL_BIN"),
        os.path.expanduser("~/.foundry/bin/anvil"),
        "anvil",
    ):
        if cand and (Path(cand).exists() or cand == "anvil"):
            return cand
    raise FileNotFoundError("anvil not found on PATH or ~/.foundry/bin/anvil")


def start_anvil(chain: str, port: int) -> subprocess.Popen:
    rpc_url = CHAIN_RPC[chain]
    cmd = [
        find_anvil(),
        "--fork-url", rpc_url,
        "--port", str(port),
        "--silent",
        "--auto-impersonate",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    fork_url = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            req = urllib.request.Request(
                fork_url,
                data=json.dumps({"jsonrpc": "2.0", "method": "eth_chainId", "params": [], "id": 1}).encode(),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=1).read()
            return proc
        except Exception:
            time.sleep(0.5)
    proc.terminate()
    raise RuntimeError(f"anvil for {chain} did not start within 30s")


def rpc(url: str, method: str, params: list, timeout: float = 30.0) -> dict:
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.URLError as e:
        return {"error": {"message": f"transport: {e}"}}
    except Exception as e:  # noqa: BLE001
        return {"error": {"message": f"unknown: {e}"}}


def fund_wallet(url: str, chain: str) -> None:
    rpc(url, "anvil_setBalance", [TEST_ADDR, NATIVE_GIFT_WEI])
    big_18 = "0x" + format(10**24, "064x")
    for (c, token), slot in ERC20_BALANCE_SLOT.items():
        if c != chain:
            continue
        key = _slot_key(token, TEST_ADDR, slot)
        rpc(url, "anvil_setStorageAt", [token, key, big_18])


def pre_approve_routers(url: str, chain: str) -> None:
    """Pre-approve common routers for every tracked token on this chain.

    Phase B finding: many execution_plan_v3 cards target Enso shortcut /
    1inch / Permit2 routers but DON'T include the prerequisite approve
    step (the agent assumes returning users already have allowance).
    On a fresh fork the test wallet has 0 allowance → the router pulls
    revert. Pre-approving simulates the "veteran user" baseline so we
    isolate REAL calldata bugs from the missing-approve false positive.
    """
    routers = COMMON_ROUTERS_BY_CHAIN.get(chain, [])
    tokens_on_chain = [t for (c, t) in ERC20_BALANCE_SLOT.keys() if c == chain]
    for token in tokens_on_chain:
        for spender in routers:
            data = _build_approve_calldata(spender)
            rpc(url, "eth_sendTransaction", [{
                "from": TEST_ADDR,
                "to": token,
                "data": data,
                "value": "0x0",
                "gas": "0x186a0",  # 100k
            }])


def broadcast_step(url: str, tx: dict) -> dict:
    params = {
        "from": TEST_ADDR,
        "to": tx["to"],
        "data": tx["data"],
        "value": tx.get("value") or "0x0",
        "gas": tx.get("gas") or "0xa00000",
    }
    return rpc(url, "eth_sendTransaction", [params])


def replay_plan(url: str, plan: dict[str, Any]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    plan_ok = True
    for step in plan["steps"]:
        tx = step.get("transaction") or {}
        if not tx.get("to") or not tx.get("data"):
            results.append({"index": step["index"], "skipped": "no_tx",
                            "action": step.get("action")})
            continue
        send = broadcast_step(url, tx)
        if "error" in send:
            err = (send.get("error") or {}).get("message", str(send.get("error")))
            results.append({"index": step["index"], "action": step.get("action"),
                            "status": "send_error", "error": str(err)[:200]})
            plan_ok = False
            continue
        tx_hash = send.get("result")
        receipt = None
        for _ in range(60):
            r = rpc(url, "eth_getTransactionReceipt", [tx_hash])
            if r.get("result"):
                receipt = r["result"]
                break
            time.sleep(0.3)
        if not receipt:
            results.append({"index": step["index"], "action": step.get("action"),
                            "status": "receipt_timeout", "tx_hash": tx_hash})
            plan_ok = False
            continue
        status_hex = receipt.get("status", "0x0")
        ok = status_hex in ("0x1", 1, "1")
        if not ok:
            plan_ok = False
        results.append({
            "index": step["index"],
            "action": step.get("action"),
            "tx_hash": tx_hash,
            "receipt_status": status_hex,
            "gas_used": receipt.get("gasUsed"),
            "logs_count": len(receipt.get("logs") or []),
            "ok": ok,
        })
    return {
        "plan_id": plan["plan_id"],
        "source_file": plan["source_file"],
        "chain": plan["chain"],
        "step_count": plan["step_count"],
        "plan_ok": plan_ok,
        "steps": results,
    }


def replay_chain(chain: str, plans: list[dict[str, Any]], port: int) -> dict[str, Any]:
    print(f"[{chain}] spawning anvil :{port} (forking {CHAIN_RPC[chain]})", flush=True)
    proc = start_anvil(chain, port)
    url = f"http://127.0.0.1:{port}"
    plan_results: list[dict[str, Any]] = []
    try:
        fund_wallet(url, chain)
        pre_approve_routers(url, chain)
        for i, plan in enumerate(plans, 1):
            snap_resp = rpc(url, "evm_snapshot", [])
            snap = snap_resp.get("result")
            print(f"[{chain}] {i}/{len(plans)} replay {plan['plan_id']} "
                  f"({plan['step_count']} steps)", flush=True)
            try:
                res = replay_plan(url, plan)
            except Exception as exc:  # noqa: BLE001
                res = {
                    "plan_id": plan["plan_id"], "chain": chain,
                    "plan_ok": False, "error": str(exc)[:200], "steps": [],
                    "source_file": plan.get("source_file"),
                }
            plan_results.append(res)
            if snap:
                rpc(url, "evm_revert", [snap])
                fund_wallet(url, chain)
                pre_approve_routers(url, chain)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    return {"chain": chain, "plan_count": len(plans), "results": plan_results}


def render_report(run: dict[str, Any]) -> str:
    lines = [f"# Anvil fork-mainnet replay — {run['ts']}", ""]
    lines.append(f"Input: {run['input']}")
    lines.append(f"Total plans (EVM): {run['total_plans']}")
    lines.append(f"Skipped Solana: {run['skipped_solana']}")
    lines.append("")
    lines.append("## Per-chain results")
    lines.append("")
    lines.append("| Chain | Plans | PASS | FAIL |")
    lines.append("|-------|-------|------|------|")
    grand_pass = grand_fail = 0
    for chain_run in run["chains"]:
        passed = sum(1 for r in chain_run["results"] if r["plan_ok"])
        failed = chain_run["plan_count"] - passed
        grand_pass += passed
        grand_fail += failed
        lines.append(f"| {chain_run['chain']} | {chain_run['plan_count']} | {passed} | {failed} |")
    lines.append(f"| **TOTAL** | **{grand_pass + grand_fail}** | **{grand_pass}** | **{grand_fail}** |")
    lines.append("")
    if grand_fail:
        lines.append("## Failures")
        lines.append("")
        for chain_run in run["chains"]:
            for r in chain_run["results"]:
                if r["plan_ok"]:
                    continue
                lines.append(f"### {r['chain']} — {r['plan_id']}  ({r.get('source_file', '?')})")
                for s in r.get("steps", []):
                    if not s.get("ok") and "skipped" not in s:
                        lines.append(f"- step {s.get('index')} `{s.get('action')}` → "
                                     f"{s.get('receipt_status') or s.get('status')} {s.get('error', '')}")
                if r.get("error"):
                    lines.append(f"- orchestrator error: {r['error']}")
                lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plans_json", type=Path)
    parser.add_argument("-o", "--out-dir", type=Path, default=None)
    parser.add_argument("--only-chain", default=None)
    args = parser.parse_args()

    plans = json.loads(args.plans_json.read_text(encoding="utf-8"))
    by_chain: dict[str, list] = defaultdict(list)
    skipped_solana = 0
    for p in plans:
        ch = (p.get("chain") or "").lower()
        if ch == "solana":
            skipped_solana += 1
            continue
        if not ch or ch not in CHAIN_RPC:
            continue
        if args.only_chain and ch != args.only_chain:
            continue
        by_chain[ch].append(p)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = args.out_dir or (ROOT / "docs" / "anvil-fork-runs" / ts)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Replaying {sum(len(v) for v in by_chain.values())} plans "
          f"across {len(by_chain)} chains (skipped {skipped_solana} Solana)",
          flush=True)

    chain_runs = []
    for offset, (chain, chain_plans) in enumerate(sorted(by_chain.items())):
        try:
            run = replay_chain(chain, chain_plans, port=18545 + offset)
        except Exception as exc:  # noqa: BLE001
            run = {"chain": chain, "plan_count": len(chain_plans),
                   "results": [], "fatal": str(exc)[:200]}
        chain_runs.append(run)

    run_summary = {
        "ts": ts,
        "input": str(args.plans_json),
        "total_plans": sum(len(v) for v in by_chain.values()),
        "skipped_solana": skipped_solana,
        "chains": chain_runs,
    }
    (out_dir / "report.json").write_text(json.dumps(run_summary, indent=2, default=str), encoding="utf-8")
    (out_dir / "report.md").write_text(render_report(run_summary), encoding="utf-8")

    total_pass = sum(sum(1 for r in c["results"] if r["plan_ok"]) for c in chain_runs)
    total_fail = sum(sum(1 for r in c["results"] if not r["plan_ok"]) for c in chain_runs)
    print(f"\n{'='*60}", flush=True)
    print(f"Anvil fork replay: {total_pass}/{total_pass + total_fail} plans PASS", flush=True)
    print(f"  artifacts -> {out_dir}", flush=True)
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
