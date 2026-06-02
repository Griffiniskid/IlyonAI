"""Liquidity-pool sign simulation test (no staking).

For each LP deposit question, drives the REAL agent endpoint, then for any
`ready` plan runs the EXACT gates the web wallet hook enforces before the
MetaMask/Phantom popup opens:

  1. Freshness gate  — simulated_at present, finite, age < SIM_FRESHNESS (180s)
                       (mirrors useWalletSigning.ts assertFresh)
  2. Hash-bind gate  — simulated_calldata_hash present AND equals the hash the
                       frontend recomputes over {to,data,value}
                       (mirrors computeCalldataHash / assertCalldataMatch)
  3. Calldata shape  — chain_kind/chain_id present, to+data (evm) present
  4. On-chain sim    — eth_call the signable step against the chain RPC from
                       the user address; a non-revert proves the calldata
                       reaches the contract (real, well-formed tx).

A plan that clears 1-3 is WOULD-SIGN (the wallet popup opens with valid
calldata the user can sign). #4 is reported separately — an unfunded test
wallet can revert on balance/allowance, which is expected, but a malformed/
garbage tx reverts differently (e.g. no method) and is flagged.
Stdlib only; runs on host python.
"""
import json
import hashlib
import time
import urllib.request

ENDPOINT = "http://localhost:8080/api/v1/agent"
EVM = {"kind": "evm", "address": "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"}
SOL_ADDR = "7Np41oeYqPefeNQEHSv1UDhYrehxin3NStpmzpaedWZ8"
SIM_FRESHNESS = 180
RUNS = 3

CHAIN_RPC = {
    1:     "https://eth.drpc.org",
    42161: "https://arb1.arbitrum.io/rpc",
    8453:  "https://mainnet.base.org",
    56:    "https://bsc-dataseed.binance.org",
    137:   "https://polygon-bor-rpc.publicnode.com",
    10:    "https://mainnet.optimism.io",
    43114: "https://api.avax.network/ext/bc/C/rpc",
}

# 15 liquidity-pool / lending deposit questions — NO staking.
QUESTIONS = [
    ("easy",   "Add 25 USDC to Aave on Arbitrum"),
    ("easy",   "Supply 0.02 WETH to Aave on Ethereum"),
    ("medium", "Add 10 USDC to Curve 3pool on Ethereum"),
    ("easy",   "Deposit 30 USDC into Aave on Base"),
    ("medium", "Add 20 USDC to PancakeSwap on BSC"),
    ("medium", "Provide 15 USDC to Uniswap v2 on Ethereum"),
    ("easy",   "Supply 25 USDC to Compound on Base"),
    ("easy",   "Add 10 USDC to Aave on Polygon"),
    ("easy",   "Add 10 USDC to Aave on Optimism"),
    ("easy",   "Supply 10 USDC to Aave on Avalanche"),
    ("medium", "Add 50 USDT to Curve on Ethereum"),
    ("hard",   "Deposit 20 USDC into Fluid on Arbitrum"),
    ("medium", "Add 15 USDC to Morpho on Base"),
    ("hard",   "Supply 0.01 WBTC to Aave on Arbitrum"),
    ("easy",   "Add 20 DAI to Aave on Ethereum"),
]


def frontend_hash(tx):
    payload = {k: str(tx[k]) for k in ("data", "to", "value") if tx.get(k) is not None}
    blob = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def eth_call(chain_id, tx, frm):
    rpc = CHAIN_RPC.get(chain_id)
    if not rpc:
        return None, "no-rpc"
    body = json.dumps({"jsonrpc": "2.0", "method": "eth_call", "params": [
        {"from": frm, "to": tx.get("to"), "data": tx.get("data"), "value": tx.get("value") or "0x0"},
        "latest"]}).encode()
    try:
        req = urllib.request.Request(rpc, data=body, headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=12) as r:
            d = json.loads(r.read())
        if "result" in d:
            return True, d["result"][:20]
        return False, (d.get("error") or {}).get("message", "err")[:90]
    except Exception as e:  # noqa: BLE001
        return None, "{}:{}".format(type(e).__name__, str(e)[:50])


def ask(message, session):
    body = json.dumps({"message": message, "session_id": session, "wallet": EVM,
                       "evm_wallet": EVM["address"], "solana_wallet": SOL_ADDR}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, headers={"Content-Type": "application/json"})
    status = None
    blockers = []
    step1 = None
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    evt = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if evt.get("card_type") == "execution_plan_v3":
                    pl = evt.get("payload") or {}
                    status = pl.get("status")
                    blockers = [b.get("code") for b in (pl.get("blockers") or [])]
                    steps = pl.get("steps") or []
                    for s in steps:
                        if s.get("status") == "ready" and (s.get("transaction") or {}).get("to"):
                            step1 = s
                            break
    except Exception as e:  # noqa: BLE001
        return {"status": "ERROR", "err": str(e)[:80], "blockers": [], "step1": None}
    return {"status": status, "blockers": blockers, "step1": step1, "err": None}


def evaluate(res):
    """Return (verdict, detail). WOULD-SIGN only if all wallet gates pass."""
    if res["status"] != "ready" or not res["step1"]:
        codes = ",".join(sorted(set(res["blockers"]))) or (res["status"] or "no-card")
        return "BLOCKED", codes
    tx = res["step1"]["transaction"]
    sa = tx.get("simulated_at")
    sh = tx.get("simulated_calldata_hash")
    # gate 1: freshness
    if not isinstance(sa, (int, float)) or sa <= 0:
        return "CANT-SIGN", "no simulated_at (SIM_STALE)"
    age = time.time() - sa
    if age > SIM_FRESHNESS:
        return "CANT-SIGN", "stale {:.0f}s".format(age)
    # gate 2: hash bind
    if not sh or sh != frontend_hash(tx):
        return "CANT-SIGN", "hash mismatch/missing"
    # gate 3: shape
    if not (tx.get("chain_kind") and tx.get("to") and tx.get("data")):
        return "CANT-SIGN", "calldata shape"
    return "WOULD-SIGN", "age={:.0f}s chain={}".format(age, tx.get("chain_id"))


def main():
    print("=" * 96)
    print("LP SIGN-SIMULATION TEST  (no staking)  | endpoint={} | runs={}".format(ENDPOINT, RUNS))
    print("=" * 96)
    rows = []
    for idx, (diff, q) in enumerate(QUESTIONS):
        verdicts = []
        details = []
        onchain = None
        for r in range(RUNS):
            res = ask(q, "lpsim-{}-{}".format(idx, r))
            v, d = evaluate(res)
            verdicts.append(v)
            details.append(d)
            if v == "WOULD-SIGN" and onchain is None:
                tx = res["step1"]["transaction"]
                ok, msg = eth_call(tx.get("chain_id"), tx, EVM["address"])
                onchain = ("exec-ok" if ok else ("revert:" + msg if ok is False else "rpc:" + msg))
        # stable verdict = all-runs WOULD-SIGN; else flag
        if all(v == "WOULD-SIGN" for v in verdicts):
            final = "WOULD-SIGN"
        elif all(v == "BLOCKED" for v in verdicts):
            final = "BLOCKED"
        elif any(v == "CANT-SIGN" for v in verdicts):
            final = "CANT-SIGN"
        else:
            final = "FLAKY"
        rows.append((idx, diff, q, final, verdicts, details, onchain))
        print("\n[{}] {:6s} {}".format(idx, diff, q))
        print("    verdict={} runs={}".format(final, verdicts))
        print("    detail={}".format(list(dict.fromkeys(details))))
        if onchain:
            print("    on-chain eth_call: {}".format(onchain))
    print("\n" + "=" * 96)
    ws = [r for r in rows if r[3] == "WOULD-SIGN"]
    cs = [r for r in rows if r[3] == "CANT-SIGN"]
    bl = [r for r in rows if r[3] == "BLOCKED"]
    fl = [r for r in rows if r[3] == "FLAKY"]
    print("WOULD-SIGN (wallet popup opens, gates pass): {}/{}".format(len(ws), len(rows)))
    print("CANT-SIGN  (ready but a sign gate fails):    {}".format(len(cs)))
    print("BLOCKED    (never ready):                    {}".format(len(bl)))
    print("FLAKY      (inconsistent across runs):       {}".format(len(fl)))


if __name__ == "__main__":
    main()
