"""Execute REAL harvested pools by pool-id, with varied amounts, across
protocols (PancakeSwap, Curve, Aave, Balancer, SushiSwap, Orca, Raydium,
Fluid). Uses the user's own EXECUTE format: "Execute deposit into pool <id>
with <amount> <token>". Drives the real endpoint, runs the exact wallet
sign-gates (freshness + hash-bind + shape), and eth_calls EVM signable txs.

Pool IDs are the app's canonical DefiLlama pool references (same value the
EXECUTE button sends) and each maps to a real on-chain pool on its protocol.
Stdlib only; host python.
"""
import json
import hashlib
import time
import urllib.request

ENDPOINT = "http://localhost:8080/api/v1/agent"
EVM = {"kind": "evm", "address": "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"}
SOL = {"kind": "solana", "address": "7Np41oeYqPefeNQEHSv1UDhYrehxin3NStpmzpaedWZ8"}
SIM_FRESHNESS = 180
RUNS = 2

CHAIN_RPC = {
    1: "https://eth.drpc.org", 42161: "https://arb1.arbitrum.io/rpc",
    8453: "https://base.drpc.org", 56: "https://bsc.drpc.org",
    137: "https://polygon.drpc.org", 10: "https://optimism.drpc.org",
    43114: "https://avalanche.drpc.org",
}
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# (protocol, chain, symbol, pool_id, amount, token, app_executable_flag, wallet)
POOLS = [
    ("pancakeswap-amm", "bsc", "USDT-WBNB", "a3878e88-0c9f-49ef-adbc-da5fe048192d", 20, "USDT", True, EVM),
    ("pancakeswap-amm", "bsc", "WBNB-BUSD", "1ba6ccca-7122-47ce-854e-06883f9b2897", 15, "BUSD", True, EVM),
    ("pancakeswap-amm", "bsc", "GMT-USDC", "2549281c-52e1-47ea-b97c-50024c62588a", 10, "USDC", False, EVM),
    ("curve-dex", "ethereum", "FRAX-USDC", "3f6aa14f-eb0c-4738-bf74-8bc666f7d2b1", 25, "USDC", True, EVM),
    ("curve-dex", "ethereum", "PYUSD-USDC", "14681aee-05c9-4733-acd0-7b2c84616209", 30, "USDC", True, EVM),
    ("aave-v3", "arbitrum", "USDC", "d9fa8e14-0447-4207-9ae8-7810199dfa1f", 25, "USDC", True, EVM),
    ("aave-v3", "arbitrum", "WETH", "e302de4d-952e-4e18-9749-0a9dc86e98bc", 0.02, "WETH", True, EVM),
    ("aave-v3", "base", "GHO", "35dbaee7-dc76-465c-b468-a09634833f7f", 10, "GHO", True, EVM),
    ("aave-v3", "base", "USDC", "7e0661bf-8cf3-45e6-9424-31916d4c7b84", 40, "USDC", True, EVM),
    ("balancer-v2", "ethereum", "DAI-USDC-USDT", "a4ab0282-3ced-4a9c-b994-5d554937da66", 20, "USDC", False, EVM),
    ("sushiswap", "ethereum", "USDC-WETH", "966e2c65-5c3a-4550-bbbd-d51f8e528b1a", 15, "USDC", False, EVM),
    ("fluid-lending", "polygon", "USDC", "b64ea0b3-befa-4333-be3d-91f0d19e3e6d", 10, "USDC", True, EVM),
    ("orca-dex", "solana", "SOL-USDC", "a5c85bc8-eb41-45c0-a520-d18d7529c0d8", 1, "SOL", False, SOL),
    ("raydium-amm", "solana", "WSOL-USDC", "62bb16e2-156b-4511-b875-41e6317dab1f", 1, "SOL", False, SOL),
    ("curve-dex", "polygon", "MAI-USDC.E", "91e77fb6-a859-4dad-af0b-4b07d513905a", 10, "USDC", False, EVM),
]


def frontend_hash(tx):
    p = {k: str(tx[k]) for k in ("data", "to", "value") if tx.get(k) is not None}
    return hashlib.sha256(json.dumps(p, separators=(",", ":"), sort_keys=True).encode()).hexdigest()


def eth_call(chain_id, tx, frm):
    rpc = CHAIN_RPC.get(chain_id)
    if not rpc:
        return None, "no-rpc(chain=%s)" % chain_id
    val = tx.get("value") or "0x0"
    if not str(val).startswith("0x"):
        val = "0x0"
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_call", "params": [
        {"from": frm, "to": tx.get("to"), "data": tx.get("data"), "value": val}, "latest"]}).encode()
    try:
        req = urllib.request.Request(rpc, data=body, headers={"Content-Type": "application/json", "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=12) as r:
            d = json.loads(r.read())
        if "result" in d:
            return True, "exec-ok"
        return False, ((d.get("error") or {}).get("message") or "err")[:70]
    except Exception as e:  # noqa: BLE001
        return None, "rpc:%s" % str(e)[:40]


def ask(message, wallet, session):
    body = json.dumps({"message": message, "session_id": session, "wallet": wallet,
                       "evm_wallet": EVM["address"], "solana_wallet": SOL["address"]}).encode()
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
                p = line[5:].strip()
                if not p or p == "[DONE]":
                    continue
                try:
                    evt = json.loads(p)
                except json.JSONDecodeError:
                    continue
                if evt.get("card_type") == "execution_plan_v3":
                    pl = evt.get("payload") or {}
                    status = pl.get("status")
                    blockers = [b.get("code") for b in (pl.get("blockers") or [])]
                    for s in (pl.get("steps") or []):
                        tx = s.get("transaction") or {}
                        if s.get("status") == "ready" and (tx.get("to") or tx.get("serialized")):
                            step1 = s
                            break
    except Exception as e:  # noqa: BLE001
        return {"status": "ERROR", "err": str(e)[:80], "blockers": [], "step1": None}
    return {"status": status, "blockers": blockers, "step1": step1}


def evaluate(res):
    if res["status"] != "ready" or not res["step1"]:
        return "BLOCKED", ",".join(sorted(set(res["blockers"]))) or (res["status"] or "no-card")
    tx = res["step1"]["transaction"]
    sa, sh = tx.get("simulated_at"), tx.get("simulated_calldata_hash")
    if not isinstance(sa, (int, float)) or sa <= 0:
        return "CANT-SIGN", "no simulated_at"
    if time.time() - sa > SIM_FRESHNESS:
        return "CANT-SIGN", "stale"
    if tx.get("chain_kind") == "evm":
        if not sh or sh != frontend_hash(tx):
            return "CANT-SIGN", "hash mismatch"
        if not (tx.get("to") and tx.get("data")):
            return "CANT-SIGN", "shape"
    else:
        if not tx.get("serialized"):
            return "CANT-SIGN", "no serialized"
    return "WOULD-SIGN", "chain=%s" % tx.get("chain_id")


def main():
    print("=" * 100)
    print("REAL-POOL EXECUTE TEST  | execute by pool-id, varied amounts | runs=%d" % RUNS)
    print("=" * 100)
    rows = []
    for i, (proto, chain, sym, pid, amt, tok, appexec, wallet) in enumerate(POOLS):
        msg = "Execute deposit into pool %s with %s %s" % (pid, amt, tok)
        verdicts, details = [], []
        onchain = None
        for r in range(RUNS):
            res = ask(msg, wallet, "rpx-%d-%d" % (i, r))
            v, d = evaluate(res)
            verdicts.append(v)
            details.append(d)
            if v == "WOULD-SIGN" and onchain is None and res["step1"]["transaction"].get("chain_kind") == "evm":
                ok, m = eth_call(res["step1"]["transaction"].get("chain_id"), res["step1"]["transaction"], EVM["address"])
                onchain = m
        final = verdicts[0] if len(set(verdicts)) == 1 else "FLAKY(%s)" % "/".join(verdicts)
        rows.append((proto, chain, sym, pid, amt, tok, appexec, final, onchain))
        flag = "exec✓" if appexec else "exec✗"
        print("\n[%2d] %-16s %-9s %-14s amt=%s %s  (app:%s)" % (i, proto, chain, sym, amt, tok, flag))
        print("     pool=%s" % pid)
        print("     verdict=%s  detail=%s%s" % (final, list(dict.fromkeys(details)),
                                                ("  on-chain=%s" % onchain) if onchain else ""))
    print("\n" + "=" * 100)
    ws = sum(1 for r in rows if r[7] == "WOULD-SIGN")
    cs = sum(1 for r in rows if r[7] == "CANT-SIGN")
    bl = sum(1 for r in rows if r[7] == "BLOCKED")
    fl = sum(1 for r in rows if r[7].startswith("FLAKY"))
    print("WOULD-SIGN: %d/%d  | CANT-SIGN: %d | BLOCKED: %d | FLAKY: %d" % (ws, len(rows), cs, bl, fl))


if __name__ == "__main__":
    main()
