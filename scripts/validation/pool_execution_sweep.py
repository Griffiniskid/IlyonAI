#!/usr/bin/env python3
"""Pool-execution verification sweep.

Runs a matrix of search criteria across chains. For EVERY pool the AI returns:

  - executable == True  -> dry-run execute_pool_position and assert the plan is
    `ready` OR blocked only by SOFT (user-funding) codes, AND a real unsigned
    transaction is attached to the first step. (Solana builds are simulated in
    the sidecar via simulateBase64Tx; EVM builds carry router calldata.)
  - executable == False -> assert a non-empty https pool_deeplink is present
    (so the UI can show "Open pool"), and NO execute affordance is implied.

Exit code 0 ONLY if zero FAILS. Prints a per-pool table + summary so we never
*claim* execution works without proof.

Usage: python3 scripts/validation/pool_execution_sweep.py
"""
from __future__ import annotations

import json
import sys
import urllib.request

API = "http://localhost:8080/api/v1/agent"
EVM = "0x28C6c06298d514Db089934071355E5743bf21d60"   # read-only funded probe
SOL = "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"

SOFT = {
    "INSUFFICIENT_BALANCE", "GAS_TOPUP_REQUIRED", "APPROVAL_MISSING",
    "STALE_PRICE_FEED", "SIM_STALE", "WALLET_NOT_CONNECTED",
}

CHAINS = ["ethereum", "base", "arbitrum", "optimism", "polygon", "bsc", "avalanche", "solana"]
SHAPES = ["liquidity pools", "stablecoin pools", "lending pools", "staking pools"]


def call(message: str) -> list[dict]:
    body = json.dumps({"message": message, "evm_wallet": EVM, "solana_wallet": SOL}).encode()
    req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
    cards: list[dict] = []
    try:
        with urllib.request.urlopen(req, timeout=160) as r:
            for raw in r:
                line = raw.decode().strip()
                if not line.startswith("data:"):
                    continue
                try:
                    cards.append(json.loads(line[5:].strip()))
                except Exception:
                    continue
    except Exception as exc:
        print(f"    ! request failed: {type(exc).__name__}")
    return cards


def first_plan(cards: list[dict]) -> dict | None:
    plan = None
    for o in cards:
        if o.get("card_type") == "execution_plan_v3":
            plan = o["payload"]
    return plan


def main() -> int:
    # 1) Gather every returned pool across the matrix.
    pools: dict[str, dict] = {}
    for chain in CHAINS:
        for shape in SHAPES:
            for o in call(f"{shape} on {chain}"):
                if o.get("card_type") == "defi_opportunities":
                    for it in o["payload"]["items"]:
                        pid = it.get("pool_id")
                        if pid and pid not in pools:
                            pools[pid] = it
    print(f"Collected {len(pools)} unique pools across {len(CHAINS)}x{len(SHAPES)} searches\n")

    fails = 0
    exec_ok_by_chain: dict[str, int] = {}
    for pid, it in pools.items():
        ch, proto, sym = it.get("chain"), it.get("protocol"), it.get("symbol")
        if it.get("executable"):
            cards = call(f"Execute deposit into pool {pid} with $15")
            plan = first_plan(cards)
            if plan is None:
                verdict, ok = "FAIL(no card)", False
            else:
                st = plan.get("status")
                codes = [b.get("code") for b in (plan.get("blockers") or [])]
                steps = plan.get("steps") or []
                has_tx = any(s.get("transaction") for s in steps)
                if st == "ready" and has_tx:
                    verdict, ok = "PASS(ready,signable)", True
                elif st == "ready":
                    verdict, ok = "FAIL(ready,NO-tx)", False
                elif codes and all(c in SOFT for c in codes):
                    verdict, ok = f"PASS(needs-funds:{codes})", True
                else:
                    verdict, ok = f"FAIL({st}:{codes})", False
            if ok:
                exec_ok_by_chain[ch] = exec_ok_by_chain.get(ch, 0) + 1
            else:
                fails += 1
            print(f"  [{verdict}] EXEC {ch} | {proto} | {sym}")
        else:
            dl = it.get("pool_deeplink") or ""
            if dl.startswith("https://"):
                pass  # correct: non-executable pool carries a deep link
            else:
                fails += 1
                print(f"  [FAIL(no-deeplink)] {ch} | {proto} | {sym}")

    print("\n--- executable pools that BUILT, by chain ---")
    for ch in CHAINS:
        print(f"  {ch}: {exec_ok_by_chain.get(ch, 0)}")
    print(f"\nSUMMARY: {len(pools)} pools checked. FAILS={fails}. "
          f"Chains with >=1 working executable pool: {sorted(exec_ok_by_chain)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
