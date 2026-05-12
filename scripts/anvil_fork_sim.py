"""L3 — funded Anvil fork validator.

Spawns `anvil --fork-url <chain rpc> --port 8545`, funds the test wallet via
`anvil_setBalance` (ETH) + `anvil_setStorageAt` (ERC20 balanceOf slots), then
broadcasts each scenario's execution_plan_v3 steps from the impersonated
account and asserts receipts.

What this catches that L2 misses:
  - Mint params semantically wrong but selectors valid → real EVM revert
    (Anvil rejects `amount0=0 amount1=0`, harness wouldn't because eth_call
    benign-reverts when wallet has 0 balance).
  - Approve insufficient for downstream pull.
  - Slippage tighter than reality.

Per chain:
  ethereum    fork rpc.ankr.com/eth or alchemy
  base        fork mainnet.base.org
  arbitrum    fork arb1.arbitrum.io
"""
from __future__ import annotations

import asyncio
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import aiohttp  # noqa: E402

# Test wallet (deterministic, never holds real funds)
TEST_ADDR = "0x4838B106FCe9647Bdf1E7877BF73cE8B0BAD5f97"

# Mainnet ERC20 + balance storage slot (verified empirically for top tokens).
ERC20_BALANCE_SLOT: dict[tuple[str, str], int] = {
    ("ethereum", "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"): 9,   # USDC
    ("ethereum", "0xdac17f958d2ee523a2206206994597c13d831ec7"): 2,   # USDT
    ("ethereum", "0x6b175474e89094c44da98b954eedeac495271d0f"): 2,   # DAI
    ("ethereum", "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"): 3,   # WETH
    ("ethereum", "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599"): 0,   # WBTC
    ("base", "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"): 9,        # USDC base
    ("base", "0x4200000000000000000000000000000000000006"): 3,        # WETH base
    ("arbitrum", "0xaf88d065e77c8cc2239327c5edb3a432268e5831"): 9,     # USDC arb
    ("arbitrum", "0x82af49447d8a07e3bd95bd0d56f35241523fbab1"): 3,     # WETH arb
}

CHAIN_RPC = {
    "ethereum": os.environ.get("MAINNET_RPC", "https://ethereum-rpc.publicnode.com"),
    "base": os.environ.get("BASE_RPC", "https://base-rpc.publicnode.com"),
    "arbitrum": os.environ.get("ARBITRUM_RPC", "https://arbitrum-one-rpc.publicnode.com"),
}


def _slot_key(token: str, holder: str, slot: int) -> str:
    """keccak256(holder_pad32 || slot_pad32) for Solidity mapping storage."""
    from eth_utils import keccak

    holder_clean = holder.lower().removeprefix("0x").rjust(64, "0")
    slot_hex = format(slot, "064x")
    return "0x" + keccak(bytes.fromhex(holder_clean + slot_hex)).hex()


def _start_anvil(chain: str, port: int = 8545) -> subprocess.Popen:
    rpc = CHAIN_RPC[chain]
    cmd = [
        os.path.expanduser("~/.foundry/bin/anvil"),
        "--fork-url", rpc,
        "--port", str(port),
        "--silent",
        "--auto-impersonate",
    ]
    proc = subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )
    # Wait for anvil to be ready (poll JSON-RPC).
    import urllib.request

    fork_url = f"http://127.0.0.1:{port}"
    for _ in range(30):
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
    raise RuntimeError("anvil did not start within 15s")


async def _rpc(session: aiohttp.ClientSession, fork_url: str, method: str, params: list) -> dict:
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    async with session.post(fork_url, json=payload) as r:
        return await r.json()


async def _fund_wallet(session: aiohttp.ClientSession, fork_url: str, chain: str) -> None:
    # 1) Give 10 ETH (or native gas) for fees.
    await _rpc(session, fork_url, "anvil_setBalance", [
        TEST_ADDR, "0x8AC7230489E80000",  # 10e18 wei = 10 ETH
    ])
    # 2) Give 1,000,000 of each tracked ERC20.
    big = "0x" + format(1_000_000 * 10**6, "064x")  # 1M USDC-style (6 decimals)
    big_18 = "0x" + format(1_000_000 * 10**18, "064x")  # 1M WETH-style
    big_8 = "0x" + format(10 * 10**8, "064x")  # 10 WBTC
    for (c, token), slot in ERC20_BALANCE_SLOT.items():
        if c != chain:
            continue
        key = _slot_key(token, TEST_ADDR, slot)
        # Heuristic: USDC/USDT/USDC.E/WBTC use 6 or 8 decimals; WETH/DAI use 18.
        amt = big_18 if token in {
            "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
            "0x6b175474e89094c44da98b954eedeac495271d0f",
            "0x4200000000000000000000000000000000000006",
            "0x82af49447d8a07e3bd95bd0d56f35241523fbab1",
        } else (big_8 if token.endswith("c599") else big)
        await _rpc(session, fork_url, "anvil_setStorageAt", [token, key, amt])


async def broadcast_step(
    session: aiohttp.ClientSession,
    fork_url: str,
    tx: dict,
) -> dict:
    """Broadcast one step via eth_sendTransaction from impersonated account."""
    params = {
        "from": TEST_ADDR,
        "to": tx["to"],
        "data": tx["data"],
        "value": tx.get("value", "0x0"),
        "gas": tx.get("gas") or "0xa00000",
    }
    return await _rpc(session, fork_url, "eth_sendTransaction", [params])


async def sim_plan_on_fork(chain: str, steps: list[dict]) -> list[dict]:
    """Spin a fresh anvil fork, fund test wallet, broadcast each step in
    sequence, return result envelopes."""
    proc = _start_anvil(chain)
    try:
        fork_url = "http://127.0.0.1:8545"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
            await _fund_wallet(session, fork_url, chain)
            results = []
            for step in steps:
                tx = step.get("transaction") or {}
                if not tx.get("to") or not tx.get("data"):
                    results.append({"step": step.get("index"), "skipped": "no tx"})
                    continue
                send = await broadcast_step(session, fork_url, tx)
                if "error" in send:
                    results.append({"step": step.get("index"), "error": send["error"].get("message", str(send["error"]))})
                    continue
                tx_hash = send.get("result")
                # Poll receipt
                for _ in range(30):
                    rec = await _rpc(session, fork_url, "eth_getTransactionReceipt", [tx_hash])
                    if rec.get("result"):
                        results.append({
                            "step": step.get("index"),
                            "tx_hash": tx_hash,
                            "status": rec["result"].get("status"),
                            "gas_used": rec["result"].get("gasUsed"),
                            "logs_count": len(rec["result"].get("logs") or []),
                        })
                        break
                    await asyncio.sleep(0.5)
                else:
                    results.append({"step": step.get("index"), "error": "receipt timeout"})
            return results
    finally:
        proc.terminate()
        proc.wait(timeout=5)


async def main():
    """Demo: fetch a V3 mint plan from staging then run it on anvil fork."""
    base = os.environ.get("ILYON_BASE", "https://staging.ilyonai.com")
    prompt = "Add liquidity to Uniswap V3 USDC/WETH 0.05% on Ethereum with $100"
    body = {
        "message": prompt,
        "session_id": "anvil-demo",
        "evm_wallet": TEST_ADDR,
        "wallet": TEST_ADDR,
    }
    print(f"Fetching plan from {base} ...")
    plan = None
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
        async with session.post(f"{base}/api/v1/agent", json=body, headers={"Accept": "text/event-stream"}) as resp:
            async for raw in resp.content:
                line = raw.decode("utf-8", "replace").rstrip("\n").rstrip("\r")
                if not line.startswith("data:"):
                    continue
                payload_str = line.split(":", 1)[1].strip()
                if not payload_str:
                    continue
                try:
                    data = json.loads(payload_str)
                except json.JSONDecodeError:
                    continue
                for k in ("card_payload", "payload", None):
                    cp = data if k is None else data.get(k)
                    if isinstance(cp, dict) and cp.get("card_type") == "execution_plan_v3":
                        plan = cp
                        break
                if plan:
                    break
    if not plan:
        print("No execution_plan_v3 card returned.")
        return
    steps = plan.get("steps") or (plan.get("payload") or {}).get("steps") or []
    print(f"Plan with {len(steps)} steps — broadcasting on anvil ...")
    results = await sim_plan_on_fork("ethereum", steps)
    for r in results:
        print(f"  step {r.get('step')}: status={r.get('status')} gas={r.get('gas_used')} logs={r.get('logs_count')} err={r.get('error')}")


if __name__ == "__main__":
    asyncio.run(main())
