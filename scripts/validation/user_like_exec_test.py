"""User-fidelity execution test.

Hits the SAME endpoint the UI hits (POST /api/v1/agent, SSE), with the SAME
wallet KIND a user would have connected per chain, runs each question N times
to expose live-Enso flakiness, and reports the execution_plan_v3 card status +
blocker codes. Stdlib only so it runs on the host python.
"""
import json
import re
import sys
import urllib.request

ENDPOINT = "http://localhost:8080/api/v1/agent"
EVM = {"kind": "evm", "address": "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"}
SOL = {"kind": "solana", "address": "7Np41oeYqPefeNQEHSv1UDhYrehxin3NStpmzpaedWZ8"}
RUNS = 5

# (difficulty, question, wallet) — natural language a user would type.
QUESTIONS = [
    ("easy",   "Deposit 10 USDC into Aave on Base",                 EVM),
    ("easy",   "Lend 25 USDC on Aave Arbitrum",                     EVM),
    ("easy",   "Supply 0.05 WETH to Aave on Ethereum",              EVM),
    ("easy",   "Deposit 10 USDC into Aave on Avalanche",            EVM),
    ("medium", "Add 20 USDC to PancakeSwap on BSC",                 EVM),
    ("medium", "Provide 15 USDC liquidity on Uniswap v2 Ethereum",  EVM),
    ("medium", "Deposit 30 USDC into Compound on Base",             EVM),
    ("hard",   "Add 10 USDC to Curve 3pool on Ethereum",            EVM),
    ("hard",   "Stake 0.1 ETH with Lido",                           EVM),
    ("hard",   "Deposit 10 USDC into a Fluid pool on Arbitrum",     EVM),
    ("easy",   "Stake 1 SOL with Marinade",                         SOL),
    ("medium", "Stake 0.5 SOL with Jito",                           SOL),
    ("hard",   "Add liquidity to a Raydium SOL-USDC pool with 1 SOL", SOL),
]


def ask(message, wallet, session):
    # Match the real UI: user has BOTH wallets connected. Send both addresses
    # plus a primary `wallet` hint for the pool's chain kind.
    payload = json.dumps({
        "message": message,
        "session_id": session,
        "wallet": wallet,
        "evm_wallet": EVM["address"],
        "solana_wallet": SOL["address"],
    }).encode()
    req = urllib.request.Request(ENDPOINT, data=payload, headers={"Content-Type": "application/json"})
    last_status = None
    blocker_codes = []
    title = None
    saw_card = False
    saw_open_pool = False
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if not body or body == "[DONE]":
                    continue
                try:
                    evt = json.loads(body)
                except json.JSONDecodeError:
                    continue
                ct = evt.get("card_type")
                pl = evt.get("payload") or {}
                if ct == "execution_plan_v3":
                    saw_card = True
                    last_status = pl.get("status")
                    title = pl.get("title")
                    blocker_codes = [b.get("code") for b in (pl.get("blockers") or [])]
                # opportunity / deeplink fallback signal
                content = evt.get("content") or ""
                if "Open pool" in content or "open_pool" in body or "pool_deeplink" in body:
                    saw_open_pool = True
    except Exception as e:  # noqa: BLE001
        return {"status": "ERROR", "err": "{}: {}".format(type(e).__name__, str(e)[:100]),
                "blockers": [], "title": None, "saw_card": False, "deeplink": False}
    return {"status": last_status, "blockers": blocker_codes, "title": title,
            "saw_card": saw_card, "deeplink": saw_open_pool, "err": None}


def classify(results):
    statuses = [r["status"] for r in results]
    n_ready = sum(1 for s in statuses if s == "ready")
    n = len(statuses)
    if n_ready == n:
        return "EXECUTABLE"
    if n_ready == 0:
        return "NOT-EXEC"
    return "FLAKY"


def main():
    print("=" * 90)
    print("USER-FIDELITY EXEC TEST  |  endpoint={}  runs/question={}".format(ENDPOINT, RUNS))
    print("=" * 90)
    rows = []
    for idx, (diff, q, wallet) in enumerate(QUESTIONS):
        results = [ask(q, wallet, "ulx-{}-{}".format(idx, r)) for r in range(RUNS)]
        verdict = classify(results)
        # collect distinct blocker codes + any error
        blk = sorted({c for r in results for c in (r["blockers"] or []) if c})
        errs = sorted({r["err"] for r in results if r["err"]})
        ready_n = sum(1 for r in results if r["status"] == "ready")
        rows.append((diff, wallet["kind"], q, verdict, ready_n, RUNS, blk, errs))
        print("\n[{}] {:6s} {:4s} | {}".format(idx, diff, wallet["kind"], q))
        print("     verdict={} ready={}/{} statuses={}".format(
            verdict, ready_n, RUNS, [r["status"] for r in results]))
        if blk:
            print("     blockers={}".format(blk))
        if errs:
            print("     errors={}".format(errs))
    # summary
    print("\n" + "=" * 90)
    print("SUMMARY")
    print("=" * 90)
    ex = [r for r in rows if r[3] == "EXECUTABLE"]
    fl = [r for r in rows if r[3] == "FLAKY"]
    ne = [r for r in rows if r[3] == "NOT-EXEC"]
    print("EXECUTABLE (ready {}/{} every run): {}".format(RUNS, RUNS, len(ex)))
    print("FLAKY (ready some runs, not all):   {}".format(len(fl)))
    print("NOT-EXEC (never ready):             {}".format(len(ne)))
    print("TOTAL:                              {}".format(len(rows)))


if __name__ == "__main__":
    main()
