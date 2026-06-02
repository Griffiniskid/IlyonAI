"""Does the agent THINK or just pattern-match?

Part A: LP-execution questions in varied human formats (slang, typos, terse,
verbose, missing prepositions) using REAL pool IDs. "Understood" = resolved to
the pool's true protocol+chain (never a fabricated default). "Executable" =
reached a ready/signable plan.

Part B: logic/reasoning questions with no execution — judged by reading the
answer text (must reason, e.g. cross-chain impossibility, risk tradeoffs).
Stdlib only; host python.
"""
import json
import urllib.request

ENDPOINT = "http://localhost:8080/api/v1/agent"
EVM = {"kind": "evm", "address": "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"}
SOL_ADDR = "7Np41oeYqPefeNQEHSv1UDhYrehxin3NStpmzpaedWZ8"

# (question, expected_protocol_substr, expected_chain)  expected=None => Solana AMM/no-build ok
LP = [
    ("yo deposit 3 bucks into a3878e88-0c9f-49ef-adbc-da5fe048192d", "pancakeswap", "bsc"),
    ("i wanna add 10 usdc to pool 1ba6ccca-7122-47ce-854e-06883f9b2897", "pancakeswap", "bsc"),
    ("put $5 in 3f6aa14f-eb0c-4738-bf74-8bc666f7d2b1", "curve", "ethereum"),
    ("can you deposit 20 usdc into the aave usdc pool on arbitrum d9fa8e14-0447-4207-9ae8-7810199dfa1f", "aave", "arbitrum"),
    ("ape 0.01 eth into e302de4d-952e-4e18-9749-0a9dc86e98bc", "aave", "arbitrum"),
    ("I'd like to provide liquidity, 15 usdc, to pool a4ab0282-3ced-4a9c-b994-5d554937da66 please", "balancer", "ethereum"),
    ("deposit 1 sol pool a5c85bc8-eb41-45c0-a520-d18d7529c0d8", "orca", "solana"),
    ("execute 62bb16e2-156b-4511-b875-41e6317dab1f with 2 sol", "raydium", "solana"),
    ("add 10 USDC to fluid pool b64ea0b3-befa-4333-be3d-91f0d19e3e6d on polygon", "fluid", "polygon"),
    ("throw 25 usdc at 7e0661bf-8cf3-45e6-9424-31916d4c7b84", "aave", "base"),
    ("depsoit 5 usdc to pool 14681aee-05c9-4733-acd0-7b2c84616209", "curve", "ethereum"),
    ("I have 30 usdc, invest it in d9fa8e14-0447-4207-9ae8-7810199dfa1f", "aave", "arbitrum"),
]

LOGIC = [
    "Pool a3878e88-0c9f-49ef-adbc-da5fe048192d is on PancakeSwap BSC. I only have USDC on Ethereum. Can I deposit into it directly? Explain.",
    "Which is safer: a pool with $2M TVL at 5% APY, or one with $40k TVL at 90% APY? Why?",
    "I have 0.005 BNB and want to deposit into a pool on Ethereum. Can I pay the gas? Why or why not?",
    "If I deposit only USDC into a USDT-WBNB liquidity pool, what happens to my USDC?",
    "A brand new pool shows 80% APY. Is that a good deal? What should I check first?",
]


def ask(message, wallet, session):
    body = json.dumps({"message": message, "session_id": session, "wallet": wallet,
                       "evm_wallet": EVM["address"], "solana_wallet": SOL_ADDR}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, headers={"Content-Type": "application/json"})
    out = {"status": None, "protocol": None, "chain": None, "blockers": [], "text": "", "tool": None}
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                p = line[5:].strip()
                if not p or p == "[DONE]":
                    continue
                try:
                    e = json.loads(p)
                except json.JSONDecodeError:
                    continue
                if e.get("card_type") == "execution_plan_v3":
                    pl = e.get("payload") or {}
                    out["status"] = pl.get("status")
                    out["blockers"] = [b.get("code") for b in (pl.get("blockers") or [])]
                    for s in (pl.get("steps") or []):
                        out["protocol"] = s.get("protocol")
                        out["chain"] = s.get("chain")
                        break
                    if not out["protocol"]:
                        t = (pl.get("title") or "")
                        out["protocol"] = t
                c = e.get("content")
                if c:
                    out["text"] += c
                rc = e.get("tool") or (e.get("payload") or {}).get("tool")
                if rc:
                    out["tool"] = rc
    except Exception as ex:  # noqa: BLE001
        out["text"] = "ERROR %s" % str(ex)[:80]
    return out


def main():
    print("=" * 96)
    print("PART A — LP EXECUTION (varied human formats, real pool IDs)")
    print("=" * 96)
    understood = execable = 0
    for i, (q, proto, chain) in enumerate(LP):
        r = ask(q, SOL_ADDR and (SOL if "sol" in q.lower() and proto in ("orca", "raydium") else EVM), "tA-%d" % i)
        got_p = (r["protocol"] or "").lower()
        got_c = (r["chain"] or "").lower()
        ok_understood = (proto in got_p) and (chain in got_c if chain else True)
        if ok_understood:
            understood += 1
        if r["status"] == "ready":
            execable += 1
        print("\n[%2d] %s" % (i, q[:70]))
        print("     expected=%s/%s  got=%s/%s  status=%s  understood=%s%s" % (
            proto, chain, got_p[:18], got_c, r["status"], ok_understood,
            ("  blockers=%s" % r["blockers"]) if r["blockers"] else ""))
    print("\nUNDERSTOOD (right pool/chain): %d/%d   |   EXECUTABLE (ready): %d/%d" % (
        understood, len(LP), execable, len(LP)))

    print("\n" + "=" * 96)
    print("PART B — LOGIC / REASONING (no execution; read the answers)")
    print("=" * 96)
    for i, q in enumerate(LOGIC):
        r = ask(q, EVM, "tB-%d" % i)
        ans = (r["text"] or "").strip().replace("\n", " ")
        print("\n[L%d] %s" % (i, q))
        print("     ANSWER: %s" % ans[:600])


# wallet helper imported late so the SOL ref above resolves
SOL = {"kind": "solana", "address": SOL_ADDR}

if __name__ == "__main__":
    main()
